"""Tests for pixel_blanker module.

Uses pydicom test data to verify pixel blanking for both JPEG Baseline
(DCT-domain) and general (numpy) code paths.
"""

import io
from pathlib import Path

import numpy as np
import pydicom
import pytest
from PIL import Image
from pydicom.data import get_testdata_file
from pydicom.dataset import FileMetaDataset
from pydicom.encaps import generate_frames
from pydicom.uid import UID
from pydicom.uid import ExplicitVRLittleEndian
from pydicom.uid import generate_uid

from dicom_dre.pixel_blanker import blank_regions
from dicom_dre.scrub_region import ScrubRegion


# JPEG Baseline transfer syntax UID
JPEG_BASELINE_TS = "1.2.840.10008.1.2.4.50"


def _testdata_path(name: str) -> Path:
    """Return the filesystem path to a pydicom test data file."""
    path = get_testdata_file(name)
    if not isinstance(path, str):
        raise ValueError(f"get_testdata_file did not return a string path for {name}")
    return Path(path)


@pytest.fixture()
def jpeg_baseline_rgb(tmp_path):
    """JPEG Baseline RGB DICOM (256x256, 3-channel, 1 frame)."""
    return _testdata_path("SC_jpeg_no_color_transform.dcm"), tmp_path / "out_jpeg_rgb.dcm"


@pytest.fixture()
def jpeg_baseline_ybr_multiframe(tmp_path):
    """JPEG Baseline YBR_FULL_422 multi-frame DICOM (640x480, 120 frames)."""
    return _testdata_path("color3d_jpeg_baseline.dcm"), tmp_path / "out_jpeg_ybr.dcm"


@pytest.fixture()
def uncompressed_mono2(tmp_path):
    """Uncompressed MONOCHROME2 DICOM (128x128, 16-bit)."""
    return _testdata_path("CT_small.dcm"), tmp_path / "out_mono2.dcm"


@pytest.fixture()
def uncompressed_rgb(tmp_path):
    """Uncompressed RGB DICOM (100x100, 8-bit)."""
    return _testdata_path("SC_rgb.dcm"), tmp_path / "out_rgb.dcm"


@pytest.fixture()
def uncompressed_multiframe(tmp_path):
    """Uncompressed MONOCHROME2 multi-frame DICOM (64x64, 10 frames, 12-bit)."""
    return _testdata_path("emri_small.dcm"), tmp_path / "out_multiframe.dcm"


@pytest.fixture()
def jpeg2000_mono(tmp_path):
    """JPEG 2000 lossless MONOCHROME2 DICOM (1024x256, 16-bit)."""
    return _testdata_path("JPEG2000.dcm"), tmp_path / "out_j2k.dcm"


def _make_monochrome1_dicom(tmp_path):
    """Create a synthetic MONOCHROME1 DICOM for testing."""
    ds = pydicom.Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.1")
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.Rows = 64
    ds.Columns = 64
    ds.BitsAllocated = 16
    ds.BitsStored = 12
    ds.HighBit = 11
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME1"
    # Fill with mid-range values
    arr = np.full((64, 64), 2048, dtype=np.uint16)
    ds.PixelData = arr.tobytes()
    path = tmp_path / "mono1.dcm"
    pydicom.dcmwrite(path, ds, enforce_file_format=True)
    return path


class TestBlankRegionsNoOp:
    """Cases where blank_regions returns without modifying pixels."""

    def test_no_pixel_data(self, tmp_path):
        """DICOM without PixelData returns was_scrubbed=False."""
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.1")
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.PatientName = "Test"
        path = tmp_path / "no_pixels.dcm"
        pydicom.dcmwrite(path, ds, enforce_file_format=True)
        out = tmp_path / "out.dcm"

        result = blank_regions(path, out, [ScrubRegion(0, 0, 10, 10)])

        assert result.was_scrubbed is False
        assert result.output_path == path

    def test_empty_regions(self, uncompressed_mono2):
        """Empty regions list returns was_scrubbed=False."""
        in_path, out_path = uncompressed_mono2

        result = blank_regions(in_path, out_path, [])

        assert result.was_scrubbed is False
        assert result.output_path == in_path


class TestJpegBaselinePath:
    """JPEG Baseline DCT-domain blanking."""

    def test_single_region(self, jpeg_baseline_rgb):
        """Single region is blanked in JPEG Baseline DICOM."""
        in_path, out_path = jpeg_baseline_rgb
        regions = [ScrubRegion(10, 10, 50, 50)]

        result = blank_regions(in_path, out_path, regions)

        assert result.was_scrubbed is True
        assert result.output_path == out_path

        # Verify transfer syntax is preserved
        ds_out = pydicom.dcmread(out_path)
        assert str(ds_out.file_meta.TransferSyntaxUID) == JPEG_BASELINE_TS

    def test_transfer_syntax_preserved(self, jpeg_baseline_rgb):
        """JPEG Baseline transfer syntax remains after blanking."""
        in_path, out_path = jpeg_baseline_rgb

        blank_regions(in_path, out_path, [ScrubRegion(0, 0, 20, 20)])

        ds_out = pydicom.dcmread(out_path)
        assert str(ds_out.file_meta.TransferSyntaxUID) == JPEG_BASELINE_TS

    def test_surrounding_pixels_unchanged(self, jpeg_baseline_rgb):
        """Pixels outside the blanked region are not modified."""
        in_path, out_path = jpeg_baseline_rgb

        # Blank a small region in the top-left corner
        regions = [ScrubRegion(0, 0, 8, 8)]
        blank_regions(in_path, out_path, regions)

        # Decode both original and blanked
        ds_orig = pydicom.dcmread(in_path)
        ds_out = pydicom.dcmread(out_path)
        orig_frame = next(generate_frames(ds_orig.PixelData, number_of_frames=1))
        out_frame = next(generate_frames(ds_out.PixelData, number_of_frames=1))

        orig_arr = np.array(Image.open(io.BytesIO(orig_frame)))
        out_arr = np.array(Image.open(io.BytesIO(out_frame)))

        # Pixels far from the blanked region should be identical
        assert np.array_equal(orig_arr[100:200, 100:200], out_arr[100:200, 100:200])

    def test_multiple_regions(self, jpeg_baseline_rgb):
        """Multiple regions are all blanked."""
        in_path, out_path = jpeg_baseline_rgb
        regions = [ScrubRegion(0, 0, 32, 32), ScrubRegion(64, 64, 32, 32), ScrubRegion(128, 128, 32, 32)]

        result = blank_regions(in_path, out_path, regions)

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        assert str(ds_out.file_meta.TransferSyntaxUID) == JPEG_BASELINE_TS

    def test_multiframe_jpeg_baseline(self, jpeg_baseline_ybr_multiframe):
        """Multi-frame JPEG Baseline processes all frames."""
        in_path, out_path = jpeg_baseline_ybr_multiframe
        # Use a small region on first 2 frames worth of data
        regions = [ScrubRegion(0, 0, 16, 16)]

        result = blank_regions(in_path, out_path, regions)

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        assert str(ds_out.file_meta.TransferSyntaxUID) == JPEG_BASELINE_TS
        # All 120 frames should still be present
        assert int(ds_out.NumberOfFrames) == 120

    def test_fallback_on_value_error(self, uncompressed_mono2, tmp_path):
        """Falls back to general path when scrub_jpeg_bytes raises ValueError."""
        in_path, out_path = uncompressed_mono2

        # Create a fake JPEG Baseline DICOM with invalid JPEG data
        ds = pydicom.dcmread(in_path)
        ds.file_meta.TransferSyntaxUID = UID(JPEG_BASELINE_TS)
        # Write non-JPEG data as pixel data in encapsulated format
        from pydicom.encaps import encapsulate

        ds.PixelData = encapsulate([ds.PixelData])
        ds["PixelData"].is_undefined_length = True
        fake_path = tmp_path / "fake_jpeg.dcm"
        ds.save_as(fake_path)

        result = blank_regions(fake_path, out_path, [ScrubRegion(0, 0, 10, 10)])

        # Should fall back to general path and produce output
        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        assert str(ds_out.file_meta.TransferSyntaxUID) == str(ExplicitVRLittleEndian)


class TestGeneralPath:
    """General path (pydicom + numpy) blanking for non-JPEG-Baseline files."""

    def test_grayscale_uncompressed(self, uncompressed_mono2):
        """Grayscale MONOCHROME2 region pixels are zeroed."""
        in_path, out_path = uncompressed_mono2
        regions = [ScrubRegion(10, 10, 20, 20)]

        result = blank_regions(in_path, out_path, regions)

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        arr = ds_out.pixel_array
        # Blanked region should be zero
        assert np.all(arr[10:30, 10:30] == 0)

    def test_grayscale_surrounding_unchanged(self, uncompressed_mono2):
        """Pixels outside the blanked region are unchanged."""
        in_path, out_path = uncompressed_mono2
        ds_orig = pydicom.dcmread(in_path)
        orig_arr = ds_orig.pixel_array.copy()

        regions = [ScrubRegion(10, 10, 20, 20)]
        blank_regions(in_path, out_path, regions)

        ds_out = pydicom.dcmread(out_path)
        out_arr = ds_out.pixel_array

        # Pixels outside the region should be identical
        assert np.array_equal(orig_arr[0:10, :], out_arr[0:10, :])
        assert np.array_equal(orig_arr[30:, :], out_arr[30:, :])
        assert np.array_equal(orig_arr[:, 0:10], out_arr[:, 0:10])
        assert np.array_equal(orig_arr[:, 30:], out_arr[:, 30:])

    def test_rgb_uncompressed(self, uncompressed_rgb):
        """RGB DICOM region pixels are zeroed across all channels."""
        in_path, out_path = uncompressed_rgb
        regions = [ScrubRegion(5, 5, 20, 20)]

        result = blank_regions(in_path, out_path, regions)

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        arr = ds_out.pixel_array
        # All channels zeroed
        assert np.all(arr[5:25, 5:25, :] == 0)

    def test_transfer_syntax_becomes_explicit_vr(self, jpeg2000_mono):
        """Non-JPEG-Baseline compressed files are saved as Explicit VR LE."""
        in_path, out_path = jpeg2000_mono
        regions = [ScrubRegion(0, 0, 20, 20)]

        blank_regions(in_path, out_path, regions)

        ds_out = pydicom.dcmread(out_path)
        assert str(ds_out.file_meta.TransferSyntaxUID) == str(ExplicitVRLittleEndian)

    def test_multiframe_grayscale(self, uncompressed_multiframe):
        """Multi-frame grayscale blanks region in all frames."""
        in_path, out_path = uncompressed_multiframe
        regions = [ScrubRegion(5, 5, 10, 10)]

        result = blank_regions(in_path, out_path, regions)

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        arr = ds_out.pixel_array
        # All 10 frames should have the region zeroed
        assert arr.shape[0] == 10
        assert np.all(arr[:, 5:15, 5:15] == 0)

    def test_monochrome1_fill_value(self, tmp_path):
        """MONOCHROME1 uses (2^BitsStored)-1 as fill value (display-black)."""
        path = _make_monochrome1_dicom(tmp_path)
        out_path = tmp_path / "out_mono1.dcm"
        regions = [ScrubRegion(10, 10, 20, 20)]

        blank_regions(path, out_path, regions)

        ds_out = pydicom.dcmread(out_path)
        arr = ds_out.pixel_array
        # BitsStored=12, so fill = 4095
        assert np.all(arr[10:30, 10:30] == 4095)

    def test_monochrome1_signed_fill_value(self, tmp_path):
        """Signed MONOCHROME1 fill value stays within the signed range."""
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.1")
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.Rows = 64
        ds.Columns = 64
        ds.BitsAllocated = 16
        ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1  # signed
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME1"
        arr = np.zeros((64, 64), dtype=np.int16)
        ds.PixelData = arr.tobytes()
        path = tmp_path / "mono1_signed.dcm"
        pydicom.dcmwrite(path, ds, enforce_file_format=True)
        out_path = tmp_path / "out_mono1_signed.dcm"
        regions = [ScrubRegion(10, 10, 20, 20)]

        result = blank_regions(path, out_path, regions)

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        out_arr = ds_out.pixel_array
        # Signed 16-bit max is 32767, not 65535
        assert np.all(out_arr[10:30, 10:30] == 32767)

    def test_ybr_full_converted_to_rgb(self, tmp_path):
        """YBR_FULL is converted to RGB when going through general path."""
        # Create a synthetic YBR_FULL DICOM (non-subsampled, same byte layout as RGB)
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.7")
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.Rows = 32
        ds.Columns = 32
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.SamplesPerPixel = 3
        ds.PlanarConfiguration = 0
        ds.PhotometricInterpretation = "YBR_FULL"
        # Fill with YBR values where Y=128, Cb=128, Cr=128 (neutral gray)
        arr = np.full((32, 32, 3), 128, dtype=np.uint8)
        ds.PixelData = arr.tobytes()
        ybr_path = tmp_path / "ybr_full.dcm"
        pydicom.dcmwrite(ybr_path, ds, enforce_file_format=True)

        out_path = tmp_path / "out_ybr.dcm"
        blank_regions(ybr_path, out_path, [ScrubRegion(0, 0, 16, 16)])

        ds_out = pydicom.dcmread(out_path)
        assert ds_out.PhotometricInterpretation == "RGB"

    def test_ybr_rct_relabeled_to_rgb(self, tmp_path):
        """YBR_RCT is relabeled to RGB in the general path.

        YBR_RCT is only valid for JPEG 2000; pydicom inverts the reversible
        color transform on decode, so decompressed samples are RGB. The
        uncompressed output must carry PhotometricInterpretation=RGB.
        """
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.7")
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.Rows = 32
        ds.Columns = 32
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.SamplesPerPixel = 3
        ds.PlanarConfiguration = 0
        ds.PhotometricInterpretation = "YBR_RCT"
        arr = np.full((32, 32, 3), 200, dtype=np.uint8)
        ds.PixelData = arr.tobytes()
        ybr_path = tmp_path / "ybr_rct.dcm"
        pydicom.dcmwrite(ybr_path, ds, enforce_file_format=True)

        out_path = tmp_path / "out_ybr_rct.dcm"
        blank_regions(ybr_path, out_path, [ScrubRegion(0, 0, 16, 16)])

        ds_out = pydicom.dcmread(out_path)
        assert ds_out.PhotometricInterpretation == "RGB"
        assert ds_out.PlanarConfiguration == 0

    def test_sop_instance_uid_unchanged(self, uncompressed_mono2):
        """The blanker does not mint a new SOP Instance UID."""
        in_path, out_path = uncompressed_mono2
        ds_orig = pydicom.dcmread(in_path)
        orig_uid = ds_orig.SOPInstanceUID
        orig_media_uid = ds_orig.file_meta.MediaStorageSOPInstanceUID

        blank_regions(in_path, out_path, [ScrubRegion(10, 10, 20, 20)])

        ds_out = pydicom.dcmread(out_path)
        assert ds_out.SOPInstanceUID == orig_uid
        assert ds_out.file_meta.MediaStorageSOPInstanceUID == orig_media_uid

    def test_signed_pixel_data(self, uncompressed_mono2):
        """Signed MONOCHROME2 region is zeroed without overflow or masking."""
        in_path, out_path = uncompressed_mono2
        # CT_small.dcm is signed 16-bit (PixelRepresentation=1).
        ds_orig = pydicom.dcmread(in_path)
        assert ds_orig.PixelRepresentation == 1
        orig_arr = ds_orig.pixel_array.copy()

        blank_regions(in_path, out_path, [ScrubRegion(10, 10, 20, 20)])

        ds_out = pydicom.dcmread(out_path)
        out_arr = ds_out.pixel_array
        assert np.all(out_arr[10:30, 10:30] == 0)
        # Pixels outside the region round-trip unchanged, including any negative
        # values, confirming no unintended masking of signed data.
        assert np.array_equal(orig_arr[0:10, :], out_arr[0:10, :])

    def test_signed_bits_stored_below_allocated(self, tmp_path):
        """Signed 12-in-16 image with stray high bits round-trips without error."""
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.1")
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
        ds.Rows = 8
        ds.Columns = 8
        ds.BitsAllocated = 16
        ds.BitsStored = 12
        ds.HighBit = 11
        ds.PixelRepresentation = 1  # signed
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        # Raw 16-bit words whose low 12 bits encode signed values and whose
        # high bits 12-15 carry garbage that pydicom discards on decode.
        raw = np.full((8, 8), 0xF000 | 0x07FF, dtype=np.uint16)  # decodes to 2047
        ds.PixelData = raw.tobytes()
        path = tmp_path / "signed_12in16.dcm"
        pydicom.dcmwrite(path, ds, enforce_file_format=True)
        out_path = tmp_path / "out_signed_12in16.dcm"

        result = blank_regions(path, out_path, [ScrubRegion(0, 0, 4, 4)])

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        out_arr = ds_out.pixel_array
        # Decoded values stay within the signed 12-bit stored range.
        assert out_arr.min() >= -2048
        assert out_arr.max() <= 2047
        assert np.all(out_arr[0:4, 0:4] == 0)
        # Unblanked pixels decode to 2047 (garbage high bits stripped).
        assert np.all(out_arr[4:8, 4:8] == 2047)

    def test_unsigned_high_bit_overlay_masked(self, tmp_path):
        """Unsigned 12-in-16 image with high-bit overlay is masked to stored width."""
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.1")
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
        ds.Rows = 8
        ds.Columns = 8
        ds.BitsAllocated = 16
        ds.BitsStored = 12
        ds.HighBit = 11
        ds.PixelRepresentation = 0  # unsigned
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        # Stored value 0x0ABC with a high-bit overlay in bits 12-15 (0xF000).
        raw = np.full((8, 8), 0xF000 | 0x0ABC, dtype=np.uint16)
        ds.PixelData = raw.tobytes()
        path = tmp_path / "unsigned_12in16.dcm"
        pydicom.dcmwrite(path, ds, enforce_file_format=True)
        out_path = tmp_path / "out_unsigned_12in16.dcm"

        result = blank_regions(path, out_path, [ScrubRegion(0, 0, 4, 4)])

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        out_arr = ds_out.pixel_array
        # High-bit overlay stripped; stored value preserved.
        assert np.all(out_arr[4:8, 4:8] == 0x0ABC)
        assert out_arr.max() <= 4095
        assert np.all(out_arr[0:4, 0:4] == 0)

    def test_mask_no_op_when_bits_stored_equals_allocated(self, uncompressed_rgb):
        """Unsigned image with BitsStored == BitsAllocated round-trips unchanged."""
        in_path, out_path = uncompressed_rgb
        ds_orig = pydicom.dcmread(in_path)
        assert ds_orig.BitsStored == ds_orig.BitsAllocated
        orig_arr = ds_orig.pixel_array.copy()

        blank_regions(in_path, out_path, [ScrubRegion(5, 5, 20, 20)])

        ds_out = pydicom.dcmread(out_path)
        out_arr = ds_out.pixel_array
        # Pixels outside the blanked region are bit-for-bit identical.
        assert np.array_equal(orig_arr[30:, :, :], out_arr[30:, :, :])

    def test_multiframe_color_all_frames_blanked(self, tmp_path):
        """Multi-frame RGB blanks every frame and preserves NumberOfFrames."""
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.7")
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
        ds.Rows = 16
        ds.Columns = 16
        ds.NumberOfFrames = 4
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.SamplesPerPixel = 3
        ds.PlanarConfiguration = 0
        ds.PhotometricInterpretation = "RGB"
        arr = np.full((4, 16, 16, 3), 200, dtype=np.uint8)
        ds.PixelData = arr.tobytes()
        path = tmp_path / "multiframe_rgb.dcm"
        pydicom.dcmwrite(path, ds, enforce_file_format=True)
        out_path = tmp_path / "out_multiframe_rgb.dcm"

        result = blank_regions(path, out_path, [ScrubRegion(0, 0, 8, 8)])

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        assert int(ds_out.NumberOfFrames) == 4
        out_arr = ds_out.pixel_array
        assert out_arr.shape[0] == 4
        assert np.all(out_arr[:, 0:8, 0:8, :] == 0)


class TestFloatPixelDataGuard:
    """Float and double-float pixel data are rejected up front."""

    def test_float_pixel_data_raises(self, tmp_path):
        """A dataset with FloatPixelData raises ValueError from blank_regions."""
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.66")
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
        ds.Rows = 8
        ds.Columns = 8
        ds.BitsAllocated = 32
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        arr = np.zeros((8, 8), dtype=np.float32)
        ds.FloatPixelData = arr.tobytes()
        path = tmp_path / "float_pixels.dcm"
        pydicom.dcmwrite(path, ds, enforce_file_format=True)
        out_path = tmp_path / "out_float.dcm"

        with pytest.raises(ValueError, match="Float Pixel Data"):
            blank_regions(path, out_path, [ScrubRegion(0, 0, 4, 4)])

    def test_double_float_pixel_data_raises(self, tmp_path):
        """A dataset with DoubleFloatPixelData raises ValueError from blank_regions."""
        ds = pydicom.Dataset()
        ds.file_meta = FileMetaDataset()
        ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta.MediaStorageSOPClassUID = UID("1.2.840.10008.5.1.4.1.1.66")
        ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
        ds.Rows = 8
        ds.Columns = 8
        ds.BitsAllocated = 64
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        arr = np.zeros((8, 8), dtype=np.float64)
        ds.DoubleFloatPixelData = arr.tobytes()
        path = tmp_path / "double_float_pixels.dcm"
        pydicom.dcmwrite(path, ds, enforce_file_format=True)
        out_path = tmp_path / "out_double_float.dcm"

        with pytest.raises(ValueError, match="Double Float Pixel"):
            blank_regions(path, out_path, [ScrubRegion(0, 0, 4, 4)])


class TestEdgeCases:
    """Edge cases: clipping, boundaries, out-of-bounds regions."""

    def test_region_fully_outside(self, uncompressed_mono2):
        """Region completely outside image bounds is skipped."""
        in_path, out_path = uncompressed_mono2
        ds_orig = pydicom.dcmread(in_path)
        orig_arr = ds_orig.pixel_array.copy()

        # Region starts beyond image dimensions (128x128)
        regions = [ScrubRegion(200, 200, 50, 50)]
        blank_regions(in_path, out_path, regions)

        ds_out = pydicom.dcmread(out_path)
        out_arr = ds_out.pixel_array
        assert np.array_equal(orig_arr, out_arr)

    def test_region_partially_outside(self, uncompressed_mono2):
        """Region extending beyond image bounds is clipped."""
        in_path, out_path = uncompressed_mono2
        # Image is 128x128, region extends to 148x148
        regions = [ScrubRegion(120, 120, 50, 50)]

        blank_regions(in_path, out_path, regions)

        ds_out = pydicom.dcmread(out_path)
        arr = ds_out.pixel_array
        # Clipped to (120:128, 120:128)
        assert np.all(arr[120:128, 120:128] == 0)

    def test_region_at_image_boundary(self, uncompressed_mono2):
        """Region exactly at the image edge does not cause index errors."""
        in_path, out_path = uncompressed_mono2
        # Region at bottom-right corner
        regions = [ScrubRegion(118, 118, 10, 10)]

        result = blank_regions(in_path, out_path, regions)

        assert result.was_scrubbed is True
        ds_out = pydicom.dcmread(out_path)
        arr = ds_out.pixel_array
        assert np.all(arr[118:128, 118:128] == 0)

    def test_zero_width_region(self, uncompressed_mono2):
        """Zero-width region is skipped without error."""
        in_path, out_path = uncompressed_mono2
        ds_orig = pydicom.dcmread(in_path)
        orig_arr = ds_orig.pixel_array.copy()

        regions = [ScrubRegion(10, 10, 0, 20)]
        blank_regions(in_path, out_path, regions)

        ds_out = pydicom.dcmread(out_path)
        assert np.array_equal(orig_arr, ds_out.pixel_array)


class TestHighlight:
    """Highlight mode fills with visible colors instead of black."""

    def test_highlight_grayscale(self, uncompressed_mono2):
        """Highlight fills grayscale with mid-range value."""
        in_path, out_path = uncompressed_mono2
        regions = [ScrubRegion(10, 10, 20, 20)]

        blank_regions(in_path, out_path, regions, highlight=True)

        ds_out = pydicom.dcmread(out_path)
        arr = ds_out.pixel_array
        # CT_small.dcm is signed 16-bit, so highlight = ((2^15 - 1)) // 2 = 16383
        expected = ((2**15) - 1) // 2
        assert np.all(arr[10:30, 10:30] == expected)

    def test_highlight_rgb(self, uncompressed_rgb):
        """Highlight fills RGB with magenta (255, 0, 255)."""
        in_path, out_path = uncompressed_rgb
        regions = [ScrubRegion(5, 5, 20, 20)]

        blank_regions(in_path, out_path, regions, highlight=True)

        ds_out = pydicom.dcmread(out_path)
        arr = ds_out.pixel_array
        assert np.all(arr[5:25, 5:25, 0] == 255)  # R
        assert np.all(arr[5:25, 5:25, 1] == 0)  # G
        assert np.all(arr[5:25, 5:25, 2] == 255)  # B
