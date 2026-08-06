"""Tests for jpeg_dct_scrubber module.

Uses pydicom test data with JPEG Baseline transfer syntax to verify
DCT-domain blanking produces the expected pixel-level results.
"""

import io
import math
import struct

import numpy as np
import pytest
from PIL import Image
from pydicom import dcmread
from pydicom.data import get_testdata_file
from pydicom.encaps import get_frame

from dicom_dre import jpeg_dct_scrubber
from dicom_dre.jpeg_dct_scrubber import _block_overlaps_any_region
from dicom_dre.jpeg_dct_scrubber import _parse_sof
from dicom_dre.jpeg_dct_scrubber import _size_and_amplitude
from dicom_dre.jpeg_dct_scrubber import jpeg_dct_accelerator_available
from dicom_dre.jpeg_dct_scrubber import jpeg_dct_accelerator_info
from dicom_dre.jpeg_dct_scrubber import scrub_jpeg
from dicom_dre.jpeg_dct_scrubber import scrub_jpeg_bytes
from dicom_dre.scrub_region import ScrubRegion


# JPEG Baseline transfer syntax UID
JPEG_BASELINE_TS = "1.2.840.10008.1.2.4.50"

# DCT zeroing produces mid-gray (128) for 8-bit images due to the JPEG level shift
DCT_ZERO_VALUE = 128


def _get_sof_from_jpeg(jpeg_bytes: bytes):
    """Extract SOFInfo from raw JPEG bytes."""
    stream = io.BytesIO(jpeg_bytes)
    stream.read(2)  # skip SOI
    while True:
        b = stream.read(1)
        if not b:
            break
        if b[0] != 0xFF:
            continue
        marker_byte = stream.read(1)
        if not marker_byte:
            break
        marker = 0xFF00 | marker_byte[0]
        if marker == 0xFFC0:
            length = struct.unpack(">H", stream.read(2))[0]
            data = stream.read(length - 2)
            return _parse_sof(data)
        if 0xFFC0 <= marker <= 0xFFEF and marker != 0xFFDA:
            length = struct.unpack(">H", stream.read(2))[0]
            stream.read(length - 2)
    raise ValueError("No SOF0 marker found in JPEG data")


def _compute_blanked_block_bounds(region_x: int, region_y: int, region_w: int, region_h: int, block_size: int) -> tuple:
    """Compute the pixel bounds of all blocks that overlap a region.

    Returns (x_start, y_start, x_end, y_end) aligned to block boundaries.
    """
    x_start = (region_x // block_size) * block_size
    y_start = (region_y // block_size) * block_size
    x_end = math.ceil((region_x + region_w) / block_size) * block_size
    y_end = math.ceil((region_y + region_h) / block_size) * block_size
    return x_start, y_start, x_end, y_end


def _decode_jpeg_to_array(jpeg_bytes: bytes) -> np.ndarray:
    """Decode JPEG bytes to a numpy array using PIL."""
    return np.array(Image.open(io.BytesIO(jpeg_bytes)))


@pytest.fixture()
def jpeg_1_1_1_frame():
    """Return a JPEG Baseline frame with 1:1:1 sampling (8x8 MCU).

    Uses SC_jpeg_no_color_transform.dcm: 256x256, 3-component RGB, no
    chroma subsampling. Each block is exactly 8x8 pixels for all components.
    """
    path = get_testdata_file("SC_jpeg_no_color_transform.dcm")
    assert isinstance(path, str), f"get_testdata_file should return a str path, got {type(path).__name__}"
    ds = dcmread(path, force=True)
    if str(ds.file_meta.TransferSyntaxUID) != JPEG_BASELINE_TS:
        pytest.skip("Test file is not JPEG Baseline")
    return get_frame(ds.PixelData, 0, number_of_frames=1)


@pytest.fixture()
def jpeg_4_2_0_frame():
    """Return a JPEG Baseline frame with 4:2:0 sampling (16x16 MCU).

    Uses SC_rgb_jpeg_lossy_gdcm.dcm: 100x100, 3-component YBR_FULL,
    H=2/V=2 luma subsampling. Chroma blocks span 16x16 pixel areas.
    """
    path = get_testdata_file("SC_rgb_jpeg_lossy_gdcm.dcm")
    assert isinstance(path, str), f"get_testdata_file should return a str path, got {type(path).__name__}"
    ds = dcmread(path, force=True)
    if str(ds.file_meta.TransferSyntaxUID) != JPEG_BASELINE_TS:
        pytest.skip("Test file is not JPEG Baseline")
    return get_frame(ds.PixelData, 0, number_of_frames=1)


class TestSizeAndAmplitude:
    """Tests for the _size_and_amplitude helper."""

    @pytest.mark.parametrize(
        "value, expected_size, expected_amp",
        [
            (0, 0, 0),
            (1, 1, 1),
            (-1, 1, 0),
            (5, 3, 5),
            (-5, 3, 2),
            (127, 7, 127),
            (-127, 7, 0),
        ],
    )
    def test_size_and_amplitude(self, value, expected_size, expected_amp):
        """Verify SSSS category and amplitude encoding."""
        size, amp = _size_and_amplitude(value)
        assert size == expected_size, f"Size for value {value} should be {expected_size}, got {size}"
        assert amp == expected_amp, f"Amplitude for value {value} should be {expected_amp}, got {amp}"


class TestBlockOverlap:
    """Tests for _block_overlaps_any_region."""

    def test_overlap_exact(self):
        """Block exactly matches region."""
        assert _block_overlaps_any_region(0, 0, 8, 8, [(0, 0, 8, 8)]) is True, (
            "Block matching the region exactly should overlap"
        )

    def test_overlap_partial(self):
        """Block partially overlaps region."""
        assert _block_overlaps_any_region(4, 4, 8, 8, [(0, 0, 8, 8)]) is True, (
            "Block partially overlapping the region should overlap"
        )

    def test_no_overlap_adjacent(self):
        """Block is adjacent but does not overlap."""
        assert _block_overlaps_any_region(8, 0, 8, 8, [(0, 0, 8, 8)]) is False, (
            "Block adjacent to the region should not overlap"
        )

    def test_no_overlap_distant(self):
        """Block is far from region."""
        assert _block_overlaps_any_region(100, 100, 8, 8, [(0, 0, 8, 8)]) is False, (
            "Block far from the region should not overlap"
        )

    def test_multiple_regions(self):
        """Block overlaps one of multiple regions."""
        regions = [(0, 0, 8, 8), (50, 50, 10, 10)]
        assert _block_overlaps_any_region(52, 52, 8, 8, regions) is True, (
            "Block overlapping one of multiple regions should overlap"
        )

    def test_no_regions(self):
        """Empty region list never matches."""
        assert _block_overlaps_any_region(0, 0, 8, 8, []) is False, (
            "Block should not overlap when the region list is empty"
        )


class TestScrubJpegBytes1x1:
    """DCT-domain blanking tests using 1:1:1 sampled JPEG (8x8 MCU blocks)."""

    def test_blanked_blocks_become_mid_gray(self, jpeg_1_1_1_frame):
        """Blocks overlapping the blank region should decode to 128 (mid-gray)."""
        region = (10, 10, 30, 20)
        result = scrub_jpeg_bytes(jpeg_1_1_1_frame, [ScrubRegion(*region)])

        anon_pixels = _decode_jpeg_to_array(result)
        bx0, by0, bx1, by1 = _compute_blanked_block_bounds(*region, block_size=8)

        blanked_area = anon_pixels[by0:by1, bx0:bx1]
        assert (blanked_area == DCT_ZERO_VALUE).all(), (
            f"All pixels in blanked blocks [{bx0}:{bx1}, {by0}:{by1}] should be {DCT_ZERO_VALUE}"
        )

    def test_distant_blocks_unchanged(self, jpeg_1_1_1_frame):
        """Blocks far from the blank region should be bit-identical."""
        region = (0, 0, 16, 16)
        result = scrub_jpeg_bytes(jpeg_1_1_1_frame, [ScrubRegion(*region)])

        orig_pixels = _decode_jpeg_to_array(jpeg_1_1_1_frame)
        anon_pixels = _decode_jpeg_to_array(result)

        # Check a block well outside the blanked region
        far_region = anon_pixels[200:208, 200:208]
        far_orig = orig_pixels[200:208, 200:208]
        assert np.array_equal(far_region, far_orig), "Blocks far from the blanked region should be unchanged"

    def test_block_aligned_region(self, jpeg_1_1_1_frame):
        """A block-aligned region blanks exactly those blocks and no more."""
        region = (16, 16, 32, 32)
        result = scrub_jpeg_bytes(jpeg_1_1_1_frame, [ScrubRegion(*region)])

        orig_pixels = _decode_jpeg_to_array(jpeg_1_1_1_frame)
        anon_pixels = _decode_jpeg_to_array(result)

        # Blanked area: exactly [16:48, 16:48]
        blanked = anon_pixels[16:48, 16:48]
        assert (blanked == DCT_ZERO_VALUE).all(), (
            f"All pixels in blanked area [16:48, 16:48] should be {DCT_ZERO_VALUE}"
        )

        # Adjacent block just outside: [16:48, 48:56] should be unchanged
        adjacent = anon_pixels[16:48, 48:56]
        adjacent_orig = orig_pixels[16:48, 48:56]
        assert np.array_equal(adjacent, adjacent_orig), "Adjacent blocks outside the region should be unchanged"

    def test_non_aligned_region_expands_to_blocks(self, jpeg_1_1_1_frame):
        """A non-aligned region blanks all overlapping blocks."""
        # Region at (5, 3, 10, 6) overlaps blocks [0:16, 0:16] for 8x8 grid
        region = (5, 3, 10, 6)
        result = scrub_jpeg_bytes(jpeg_1_1_1_frame, [ScrubRegion(*region)])

        anon_pixels = _decode_jpeg_to_array(result)
        bx0, by0, bx1, by1 = _compute_blanked_block_bounds(*region, block_size=8)

        blanked = anon_pixels[by0:by1, bx0:bx1]
        assert (blanked == DCT_ZERO_VALUE).all(), (
            f"Non-aligned region should blank all overlapping blocks [{bx0}:{bx1}, {by0}:{by1}]"
        )

    def test_multiple_regions(self, jpeg_1_1_1_frame):
        """Multiple blanking regions blank independently."""
        regions = [ScrubRegion(0, 0, 8, 8), ScrubRegion(64, 64, 16, 16)]
        result = scrub_jpeg_bytes(jpeg_1_1_1_frame, regions)

        anon_pixels = _decode_jpeg_to_array(result)

        assert (anon_pixels[0:8, 0:8] == DCT_ZERO_VALUE).all(), (
            f"First blanked region [0:8, 0:8] should be {DCT_ZERO_VALUE}"
        )
        assert (anon_pixels[64:80, 64:80] == DCT_ZERO_VALUE).all(), (
            f"Second blanked region [64:80, 64:80] should be {DCT_ZERO_VALUE}"
        )

    def test_empty_regions_preserves_image(self, jpeg_1_1_1_frame):
        """An empty region list produces output identical to input."""
        result = scrub_jpeg_bytes(jpeg_1_1_1_frame, [])

        orig_pixels = _decode_jpeg_to_array(jpeg_1_1_1_frame)
        anon_pixels = _decode_jpeg_to_array(result)
        assert np.array_equal(orig_pixels, anon_pixels), "Empty region list should produce output identical to input"

    def test_output_is_valid_jpeg(self, jpeg_1_1_1_frame):
        """Output starts with SOI and ends with EOI."""
        result = scrub_jpeg_bytes(jpeg_1_1_1_frame, [ScrubRegion(0, 0, 16, 16)])
        assert result[:2] == b"\xff\xd8", "Output should start with JPEG SOI marker"
        assert result[-2:] == b"\xff\xd9", "Output should end with JPEG EOI marker"


class TestScrubJpegBytes420:
    """DCT-domain blanking tests using 4:2:0 sampled JPEG (16x16 MCU blocks).

    With H=2/V=2 luma subsampling, each MCU spans 16x16 pixels. Luma blocks
    are 8x8, but chroma blocks cover 16x16 pixel areas. A blanking region
    affects all component blocks whose pixel-coordinate footprint overlaps
    the region, so the effective blanked area depends on the component.

    At MCU boundaries, the JPEG decoder's chroma upsampling filter may
    interpolate between blanked and non-blanked chroma samples, producing
    boundary pixels that are not exactly mid-gray. Tests check the MCU
    interior to avoid decoder-dependent boundary artifacts.
    """

    def test_mcu_aligned_blank_interior(self, jpeg_4_2_0_frame):
        """Interior pixels of a blanked MCU should decode to 128 (mid-gray)."""
        region = (0, 0, 16, 16)
        result = scrub_jpeg_bytes(jpeg_4_2_0_frame, [ScrubRegion(*region)])

        anon_pixels = _decode_jpeg_to_array(result)
        # Check interior, excluding the boundary row/column where chroma
        # upsampling may blend with adjacent non-blanked MCU chroma
        interior = anon_pixels[0:14, 0:14]
        assert (interior == DCT_ZERO_VALUE).all(), "Interior of blanked MCU should be mid-gray"

    def test_sub_mcu_region_blanks_overlapping_blocks(self, jpeg_4_2_0_frame):
        """A small region inside an MCU still blanks all overlapping blocks.

        For luma (8x8 blocks), a region at (2,2,4,4) overlaps the [0:8,0:8]
        luma block. For chroma (16x16 effective), it overlaps the entire
        first chroma block. The blanked pixels cover the union: [0:16,0:16].
        """
        region = (2, 2, 4, 4)
        result = scrub_jpeg_bytes(jpeg_4_2_0_frame, [ScrubRegion(*region)])

        anon_pixels = _decode_jpeg_to_array(result)
        # Check the luma block interior (well within a single luma block)
        blanked = anon_pixels[0:7, 0:7]
        assert (blanked == DCT_ZERO_VALUE).all(), "Luma block overlapping small region should be blanked"


class TestScrubJpegFilePaths:
    """Tests for file-path-based scrub_jpeg function."""

    def test_file_round_trip(self, jpeg_1_1_1_frame, tmp_path):
        """Write frame to file, scrub, verify output file is valid JPEG."""
        input_path = tmp_path / "input.jpg"
        output_path = tmp_path / "output.jpg"
        input_path.write_bytes(jpeg_1_1_1_frame)

        scrub_jpeg(str(input_path), str(output_path), [(0, 0, 16, 16)])

        assert output_path.exists(), f"Output file {output_path} should exist after scrubbing"
        result_bytes = output_path.read_bytes()
        assert result_bytes[:2] == b"\xff\xd8", "Output file should start with JPEG SOI marker"
        anon_pixels = _decode_jpeg_to_array(result_bytes)
        assert (anon_pixels[0:16, 0:16] == DCT_ZERO_VALUE).all(), (
            f"Blanked region [0:16, 0:16] should be {DCT_ZERO_VALUE}"
        )


class TestUnsupportedJpeg:
    """Tests for rejection of non-baseline JPEG."""

    def test_rejects_progressive_sof(self, jpeg_1_1_1_frame):
        """A JPEG with SOF2 (progressive) marker should raise ValueError."""
        # Replace SOF0 (0xFFC0) with SOF2 (0xFFC2) in the JPEG data
        modified = jpeg_1_1_1_frame.replace(b"\xff\xc0", b"\xff\xc2", 1)
        with pytest.raises(ValueError, match="Unsupported JPEG process marker"):
            scrub_jpeg_bytes(modified, [ScrubRegion(0, 0, 8, 8)])

    def test_rejects_non_jpeg_data(self):
        """Data not beginning with the SOI marker raises ValueError."""
        with pytest.raises(ValueError, match="Not a JPEG file"):
            scrub_jpeg_bytes(b"\x00\x01not-a-jpeg", [ScrubRegion(0, 0, 8, 8)])


def _make_gradient_jpeg(
    mode: str,
    width: int,
    height: int,
    subsampling: int,
    restart_rows: int | None = None,
    quality: int = 90,
) -> bytes:
    """Build an in-memory JPEG Baseline stream with gradient content.

    Args:
        mode: PIL image mode ("L" for grayscale, "RGB" for color).
        width: Image width in pixels.
        height: Image height in pixels.
        subsampling: PIL JPEG subsampling (0 = 4:4:4, 2 = 4:2:0).
        restart_rows: If set, emit restart markers every this many MCU rows.
        quality: JPEG quality factor, chosen to retain non-zero AC coefficients.

    Returns:
        Encoded JPEG bytes.
    """
    if mode == "L":
        arr = np.tile((np.arange(width, dtype=np.uint16) % 256).astype(np.uint8), (height, 1))
        image = Image.fromarray(arr, "L")
    else:
        arr = np.zeros((height, width, 3), dtype=np.uint8)
        arr[..., 0] = (np.arange(width, dtype=np.uint16) % 256).astype(np.uint8)
        arr[..., 1] = (np.arange(height, dtype=np.uint16) % 256).astype(np.uint8)[:, None]
        arr[..., 2] = 128
        image = Image.fromarray(arr, "RGB")
    buffer = io.BytesIO()
    save_kwargs: dict = {"subsampling": subsampling, "quality": quality}
    if restart_rows is not None:
        save_kwargs["restart_marker_rows"] = restart_rows
    image.save(buffer, "JPEG", **save_kwargs)
    return buffer.getvalue()


# (id, mode, width, height, subsampling, restart_rows, region)
_FALLBACK_VARIANTS = [
    ("grayscale_8x8", "L", 64, 48, 0, None, ScrubRegion(8, 8, 20, 16)),
    ("grayscale_restart", "L", 80, 64, 0, 2, ScrubRegion(10, 10, 30, 20)),
    ("rgb_1_1_1", "RGB", 64, 48, 0, None, ScrubRegion(8, 8, 20, 16)),
    ("rgb_4_2_0", "RGB", 64, 48, 2, None, ScrubRegion(8, 8, 20, 16)),
    ("rgb_4_2_0_restart", "RGB", 96, 64, 2, 2, ScrubRegion(16, 16, 32, 24)),
]


class TestAcceleratorReporting:
    """Tests for the accelerator introspection helpers."""

    def test_available_matches_module_state(self):
        """jpeg_dct_accelerator_available reflects the module _HAS_C_ACCEL flag."""
        assert jpeg_dct_accelerator_available() is jpeg_dct_scrubber._HAS_C_ACCEL, (
            "Reported availability should match the module-level _HAS_C_ACCEL flag"
        )

    def test_info_reports_availability(self):
        """jpeg_dct_accelerator_info exposes the availability boolean."""
        info = jpeg_dct_accelerator_info()
        assert info["available"] is jpeg_dct_scrubber._HAS_C_ACCEL, (
            f"info['available'] should equal _HAS_C_ACCEL, got {info['available']!r}"
        )
        if jpeg_dct_scrubber._HAS_C_ACCEL:
            assert "path" in info, f"Loaded accelerator should report a module path, got {info!r}"


class TestPureFallback:
    """Tests exercising the pure-Python entropy codec fallback.

    The fallback path (_process_entropy_segment without the C extension) is
    selected when _HAS_C_ACCEL is False. These tests force that path and verify
    it produces output identical to the accelerated path on the same inputs.
    """

    @pytest.mark.parametrize(
        "mode, width, height, subsampling, restart_rows, region",
        [pytest.param(*v[1:], id=v[0]) for v in _FALLBACK_VARIANTS],
    )
    def test_fallback_matches_accelerated(self, mode, width, height, subsampling, restart_rows, region, monkeypatch):
        """The Python fallback yields byte-identical output to the C path."""
        data = _make_gradient_jpeg(mode, width, height, subsampling, restart_rows)
        regions = [region]

        accelerated = None
        if jpeg_dct_scrubber._HAS_C_ACCEL:
            accelerated = scrub_jpeg_bytes(data, regions)

        monkeypatch.setattr(jpeg_dct_scrubber, "_HAS_C_ACCEL", False)
        fallback = scrub_jpeg_bytes(data, regions)

        assert fallback[:2] == b"\xff\xd8", "Fallback output should start with the JPEG SOI marker"
        assert fallback[-2:] == b"\xff\xd9", "Fallback output should end with the JPEG EOI marker"

        if accelerated is not None:
            assert fallback == accelerated, (
                f"Fallback output ({len(fallback)} bytes) should equal the accelerated "
                f"output ({len(accelerated)} bytes) for variant {mode} sub={subsampling}"
            )

    def test_fallback_blanks_grayscale_region(self, monkeypatch):
        """The fallback blanks a grayscale region to a single mid-gray value."""
        data = _make_gradient_jpeg("L", 64, 48, 0)
        monkeypatch.setattr(jpeg_dct_scrubber, "_HAS_C_ACCEL", False)

        result = scrub_jpeg_bytes(data, [ScrubRegion(16, 16, 16, 16)])
        pixels = _decode_jpeg_to_array(result)

        blanked = pixels[16:32, 16:32]
        assert (blanked == DCT_ZERO_VALUE).all(), (
            f"Fallback-blanked block [16:32, 16:32] should all equal {DCT_ZERO_VALUE}, "
            f"got unique values {np.unique(blanked)}"
        )

    def test_fallback_preserves_distant_blocks(self, monkeypatch):
        """The fallback leaves blocks outside the region bit-identical."""
        data = _make_gradient_jpeg("L", 64, 48, 0)

        monkeypatch.setattr(jpeg_dct_scrubber, "_HAS_C_ACCEL", False)
        result = scrub_jpeg_bytes(data, [ScrubRegion(0, 0, 16, 16)])

        orig_pixels = _decode_jpeg_to_array(data)
        anon_pixels = _decode_jpeg_to_array(result)
        assert np.array_equal(orig_pixels[40:48, 48:64], anon_pixels[40:48, 48:64]), (
            "Blocks far from the blanked region should be unchanged by the fallback"
        )

    def test_fallback_empty_regions_roundtrip(self, monkeypatch):
        """The fallback with no regions reproduces the input image."""
        data = _make_gradient_jpeg("RGB", 64, 48, 0)

        monkeypatch.setattr(jpeg_dct_scrubber, "_HAS_C_ACCEL", False)
        result = scrub_jpeg_bytes(data, [])

        orig_pixels = _decode_jpeg_to_array(data)
        anon_pixels = _decode_jpeg_to_array(result)
        assert np.array_equal(orig_pixels, anon_pixels), (
            "Fallback with an empty region list should reproduce the input image"
        )
