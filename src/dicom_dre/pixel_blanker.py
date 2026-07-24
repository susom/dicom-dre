"""Python pixel blanker for DICOM images.

Blanks rectangular regions in DICOM pixel data using two strategies based on
transfer syntax:

1. JPEG Baseline (1.2.840.10008.1.2.4.50): DCT-domain blanking via
   jpeg_dct_scrubber. Preserves the original compressed bitstream; only
   blanked MCU blocks are modified.

2. All other transfer syntaxes: pydicom pixel_array + numpy decompression,
   region zeroing, and save as Explicit VR Little Endian (uncompressed).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.encaps import generate_frames
from pydicom.uid import ExplicitVRLittleEndian

import dicom_dre.pydicom_config  # noqa: F401  applies process-wide pydicom config
from dicom_dre.jpeg_dct_scrubber import scrub_jpeg_bytes
from dicom_dre.scrub_region import ScrubRegion


logger = logging.getLogger(__name__)

# JPEG Baseline transfer syntax UID
_JPEG_BASELINE_TS = "1.2.840.10008.1.2.4.50"


@dataclass(frozen=True, slots=True)
class BlankResult:
    """Result of a pixel blanking operation.

    Attributes:
        output_path: Path to the output DICOM file.
        was_scrubbed: True if pixel data was modified, False if skipped.
        was_decompressed: True if the pixel data was decompressed while
            scrubbing (the general path decodes compressed input and rewrites
            it as Explicit VR Little Endian). False for the JPEG Baseline
            DCT-domain path, which preserves the compressed bitstream, and
            when the input was already uncompressed.
    """

    output_path: Path
    was_scrubbed: bool
    was_decompressed: bool = False


def blank_regions(
    file_path: Path,
    output_path: Path,
    regions: list[ScrubRegion],
    highlight: bool = False,
) -> BlankResult:
    """Blank rectangular regions in DICOM pixel data.

    Dispatches to DCT-domain blanking for JPEG Baseline files, or
    pydicom+numpy blanking for all other transfer syntaxes.

    Args:
        file_path: Path to the input DICOM file.
        output_path: Path to write the output DICOM file.
        regions: List of (x, y, width, height) rectangles to blank.
        highlight: If True, fill with a visible color instead of black in the
            general (non-JPEG Baseline DCT) path.

    Returns:
        BlankResult with the output path, whether scrubbing occurred, and
        whether the pixel data was decompressed while scrubbing. When the
        dataset has no PixelData, or when regions is empty, no output file is
        written and BlankResult.output_path is the input file_path with
        was_scrubbed=False.

    Raises:
        ValueError: If the file uses FloatPixelData/DoubleFloatPixelData, or if
            the decoded pixel array has an unsupported number of dimensions.
        FileNotFoundError: If the input file does not exist.
    """
    ds = pydicom.dcmread(file_path, force=True)

    if "FloatPixelData" in ds or "DoubleFloatPixelData" in ds:
        raise ValueError(
            f"{file_path} uses Float Pixel Data (7FE0,0008) or Double Float Pixel "
            "Data (7FE0,0009); the pixel blanker only supports integer Pixel Data "
            "(7FE0,0010)."
        )

    if "PixelData" not in ds:
        return BlankResult(output_path=file_path, was_scrubbed=False)

    if not regions:
        return BlankResult(output_path=file_path, was_scrubbed=False)

    # A dataset read with force=True may have no file_meta or a file_meta
    # missing TransferSyntaxUID. Treat a missing/unknown transfer syntax as
    # non-JPEG Baseline so the general numpy path still runs instead of raising.
    file_meta = getattr(ds, "file_meta", None)
    transfer_syntax_uid = getattr(file_meta, "TransferSyntaxUID", None)
    transfer_syntax = str(transfer_syntax_uid) if transfer_syntax_uid else None
    input_compressed = bool(getattr(transfer_syntax_uid, "is_compressed", False))

    # The general path decodes pixel data and rewrites the file as Explicit VR
    # Little Endian, so it decompresses whenever the input was compressed. The
    # JPEG Baseline DCT-domain path preserves the compressed bitstream and does
    # not decompress.
    was_decompressed = False
    if transfer_syntax == _JPEG_BASELINE_TS:
        try:
            _blank_jpeg_baseline(ds, regions)
        except ValueError as exc:
            logger.warning(
                "JPEG Baseline DCT blanking failed (%s), falling back to general path",
                exc,
            )
            _blank_general(ds, regions, highlight)
            was_decompressed = input_compressed
    else:
        _blank_general(ds, regions, highlight)
        was_decompressed = input_compressed

    pydicom.dcmwrite(output_path, ds, enforce_file_format=True)
    return BlankResult(output_path=output_path, was_scrubbed=True, was_decompressed=was_decompressed)


def _blank_jpeg_baseline(
    ds: pydicom.Dataset,
    regions: list[ScrubRegion],
) -> None:
    """Blank regions in a JPEG Baseline DICOM using DCT-domain blanking.

    Modifies ds.PixelData in place. The transfer syntax is preserved.

    Args:
        ds: pydicom Dataset with JPEG Baseline pixel data.
        regions: List of (x, y, width, height) rectangles to blank.
    """
    number_of_frames = getattr(ds, "NumberOfFrames", 1)
    if isinstance(number_of_frames, str):
        number_of_frames = int(number_of_frames)

    modified_frames = []
    for frame_data in generate_frames(ds.PixelData, number_of_frames=number_of_frames):
        modified_frame = scrub_jpeg_bytes(frame_data, regions)
        modified_frames.append(modified_frame)

    ds.PixelData = encapsulate(modified_frames)
    ds["PixelData"].is_undefined_length = True


def _blank_general(
    ds: pydicom.Dataset,
    regions: list[ScrubRegion],
    highlight: bool,
) -> None:
    """Blank regions using pydicom pixel_array + numpy.

    Decompresses pixel data, zeros (or highlights) regions, and updates the
    dataset to Explicit VR Little Endian (uncompressed).

    Args:
        ds: pydicom Dataset.
        regions: List of (x, y, width, height) rectangles to blank.
        highlight: If True, use a visible fill color instead of black.
    """
    arr = ds.pixel_array

    photometric = getattr(ds, "PhotometricInterpretation", "MONOCHROME2")

    # Convert YBR color spaces to RGB before filling so that zero-fill
    # produces black rather than green.
    if photometric in ("YBR_FULL", "YBR_FULL_422"):
        from pydicom.pixels.processing import convert_color_space

        arr = convert_color_space(arr, photometric, "RGB")
        ds.PhotometricInterpretation = "RGB"
        photometric = "RGB"

    # JPEG 2000 reversible/irreversible color transforms (YBR_RCT, YBR_ICT) are
    # inverted to RGB by pydicom during decode, so the decompressed array already
    # holds RGB samples. Relabel to RGB to match the uncompressed pixel data;
    # leaving YBR_RCT/YBR_ICT (valid only for JPEG 2000) on an Explicit VR Little
    # Endian file is non-conformant and misrenders in viewers.
    elif photometric in ("YBR_RCT", "YBR_ICT"):
        ds.PhotometricInterpretation = "RGB"
        photometric = "RGB"

    fill_value = _get_fill_value(ds, photometric, highlight)

    # Cast fill value to the array's dtype to avoid overflow for signed types
    if isinstance(fill_value, (int, np.integer)):
        fill_value = arr.dtype.type(fill_value)

    rows = ds.Rows
    cols = ds.Columns

    for region in regions:
        # Clip region to image bounds
        x0 = max(0, region.x)
        y0 = max(0, region.y)
        x1 = min(cols, region.x + region.width)
        y1 = min(rows, region.y + region.height)

        if x0 >= x1 or y0 >= y1:
            continue

        _fill_region(arr, y0, y1, x0, x1, fill_value, samples_per_pixel=ds.SamplesPerPixel)

    arr = np.ascontiguousarray(arr)
    # Strip any bits above the stored depth (e.g. retired high-bit overlays or
    # padding embedded in unused pixel bits) so they never reach the output and
    # so every value falls within the range set_pixel_data enforces from
    # BitsStored. Use a non-in-place & so the dataset's cached pixel_array is not
    # mutated as a side effect. Signed data is left unmasked because pydicom
    # sign-extends it to the stored range on decode.
    if arr.dtype.kind == "u":
        arr = arr & ((1 << ds.BitsStored) - 1)

    # Force Explicit VR Little Endian before set_pixel_data, which only rewrites
    # the Transfer Syntax when it is absent or compressed. This relabels
    # Implicit VR LE inputs and sidesteps the big-endian NotImplementedError;
    # pixel_array already decoded to a native-endian array so arr.tobytes() is
    # little-endian regardless of source byte order.
    if not hasattr(ds, "file_meta") or ds.file_meta is None:
        ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.set_pixel_data(arr, photometric, ds.BitsStored, generate_instance_uid=False)


def _fill_region(
    arr: np.ndarray,
    y0: int,
    y1: int,
    x0: int,
    x1: int,
    fill_value: int | tuple,
    samples_per_pixel: int = 1,
) -> None:
    """Fill a rectangular region in a pixel array.

    Handles 2D (grayscale), 3D (color or multi-frame grayscale),
    and 4D (multi-frame color) arrays.

    Args:
        arr: Pixel array (modified in place).
        y0: Start row (inclusive).
        y1: End row (exclusive).
        x0: Start column (inclusive).
        x1: End column (exclusive).
        fill_value: Scalar for grayscale, tuple for color.
        samples_per_pixel: DICOM SamplesPerPixel value (1=grayscale, 3=color).

    Raises:
        ValueError: If the pixel array has an unsupported number of dimensions
            (not 2, 3, or 4).
    """
    is_color = samples_per_pixel > 1
    ndim = arr.ndim
    if ndim == 2:
        arr[y0:y1, x0:x1] = fill_value
    elif ndim == 3:
        if is_color:
            # Single-frame color: (rows, cols, channels)
            arr[y0:y1, x0:x1, :] = fill_value
        else:
            # Multi-frame grayscale: (frames, rows, cols)
            arr[:, y0:y1, x0:x1] = fill_value
    elif ndim == 4:
        # Multi-frame color: (frames, rows, cols, channels)
        arr[:, y0:y1, x0:x1, :] = fill_value
    else:
        raise ValueError(
            f"Unsupported pixel array with {ndim} dimensions; expected 2 "
            "(grayscale), 3 (color or multi-frame grayscale), or 4 "
            "(multi-frame color)."
        )


def _get_fill_value(
    ds: pydicom.Dataset,
    photometric: str,
    highlight: bool,
) -> int | tuple:
    """Determine the fill value for blanking based on photometric interpretation.

    Args:
        ds: pydicom Dataset.
        photometric: PhotometricInterpretation string.
        highlight: If True, return a visible debug color.

    Returns:
        Fill value: scalar for grayscale, tuple for color.
    """
    bits_stored = ds.BitsStored
    pixel_representation = getattr(ds, "PixelRepresentation", 0)

    # Maximum stored value, respecting signedness. For signed pixel data
    # (PixelRepresentation == 1) the high bit is the sign, so the maximum
    # positive value is 2**(bits_stored - 1) - 1 rather than 2**bits_stored - 1.
    if pixel_representation == 1:
        max_val = (2 ** (bits_stored - 1)) - 1
    else:
        max_val = (2**bits_stored) - 1

    if highlight:
        if photometric in ("RGB", "YBR_FULL", "YBR_FULL_422"):
            return (255, 0, 255)
        # Grayscale highlight: mid-range value within the stored range
        return max_val // 2

    if photometric == "MONOCHROME1":
        # Inverted grayscale: max stored value = display-black
        return max_val

    if photometric in ("RGB", "YBR_FULL", "YBR_FULL_422"):
        return (0, 0, 0)

    # MONOCHROME2 and other grayscale
    return 0
