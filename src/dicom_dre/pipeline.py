"""De-identification pipeline orchestrator.

Assembles the catalog filter, pixel scrub, and metadata scrub into a single
path returning a :class:`~dicom_dre.result.DeidentifyResult`:

1. Catalog filter  (dicom_dre.catalog.DeviceCatalog)
2. Pixel scrub      (dicom_dre.pixel_blanker.blank_regions)
3. Metadata scrub   (dicom_dre.DeidProfile)
"""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING

import pydicom
from pydicom.dataset import FileMetaDataset

import dicom_dre.pydicom_config  # noqa: F401  applies process-wide pydicom config
from dicom_dre.attributes import IndexAttributes
from dicom_dre.catalog import DicomTags
from dicom_dre.default_catalog import get_default_catalog
from dicom_dre.pixel_blanker import blank_regions
from dicom_dre.result import DeidentifyResult
from dicom_dre.scrub_region import ScrubRegion


if TYPE_CHECKING:
    from pathlib import Path

    from dicom_dre.catalog import DeviceCatalog
    from dicom_dre.parameters import DeidParameters
    from dicom_dre.profile import DeidProfile


logger = logging.getLogger(__name__)

SOP_INSTANCE_UID_TAG = 0x00080018
BURNED_IN_ANNOTATION_TAG = 0x00280301
# CID 7050 code for the Clean Pixel Data Option, recorded when the pixel blanker
# removes burned-in identification.
CLEAN_PIXEL_DATA_CODE = "113101"


def _regenerate_file_meta(ds: pydicom.Dataset) -> None:
    """Rebuild the File Meta Information group from scratch before writing.

    pydicom's save_as(enforce_file_format=True) deep-copies the source file_meta
    verbatim, so every group 0002 element inherited from the original file --
    including SourceApplicationEntityTitle (0002,0016), SendingApplicationEntityTitle
    (0002,0017), ReceivingApplicationEntityTitle (0002,0018), presentation
    addresses, and any private creators -- would persist in the de-identified
    output.

    The source group is discarded and a fresh one is built preserving only the
    Transfer Syntax UID that describes the dataset's actual encoding. save_as then
    re-syncs MediaStorageSOPClassUID/MediaStorageSOPInstanceUID from the dataset
    and stamps pydicom's own implementation identity. Regenerating (rather than
    deleting a known list of tags) guarantees no source-identifying group 0002
    element survives, regardless of what the source writer emitted.
    """
    transfer_syntax = ds.file_meta.get("TransferSyntaxUID", None) if ds.file_meta is not None else None

    new_meta = FileMetaDataset()
    if transfer_syntax is not None:
        new_meta.TransferSyntaxUID = transfer_syntax
    ds.file_meta = new_meta


def deidentify_file(
    input_file: Path,
    output_file: Path,
    *,
    profile: DeidProfile,
    parameters: DeidParameters,
    catalog: DeviceCatalog | None = None,
    decompress: bool = False,
    rename_to_sop_uid: bool = True,
    dataset: pydicom.Dataset | None = None,
    highlight_blanked_pixels: bool = False,
) -> DeidentifyResult:
    """De-identify a single DICOM file using the de-identification pipeline.

    Runs the device catalog filter, pixel blanker, and metadata deidentifyr in
    sequence and returns a library-owned :class:`DeidentifyResult`.

    Args:
        input_file: Path to the PHI DICOM file.
        output_file: Path to write the de-identified DICOM file.
        profile: The bound de-identification profile to apply. Build one with
            :func:`dicom_dre.build_profile` or the exported profile factories.
        parameters: Per-patient values applied to the dataset at apply time.
        catalog: Device catalog for filtering and pixel-scrub decisions.
            Defaults to :func:`dicom_dre.get_default_catalog`.
        decompress: Whether to decompress encapsulated pixel data on output.
        rename_to_sop_uid: Rename the output file to the new SOP Instance UID.
        dataset: Optional pre-read dataset to avoid re-opening ``input_file``.
            Used only when no pixel scrubbing is required; it is mutated and
            written out in place.
        highlight_blanked_pixels: Fill scrubbed regions with a visible color.

    Returns:
        A :class:`DeidentifyResult` whose outcome is DEIDENTIFIED, FILTERED, or
        QUARANTINED.
    """
    if catalog is None:
        catalog = get_default_catalog()

    input_attributes: IndexAttributes | None = None
    try:
        # Read the input once (or reuse the supplied dataset) and build both the
        # catalog tags and the input attribute snapshot from it, so the deny path
        # stays at a single read and no snapshot triggers an extra dcmread.
        if dataset is not None:
            input_ds = dataset
        else:
            input_ds = pydicom.dcmread(str(input_file), stop_before_pixels=True)
        tags = DicomTags.from_dataset(input_ds)
        input_attributes = IndexAttributes.from_dataset(input_ds)
        decision = catalog.evaluate(tags)

        if decision.action == "deny":
            return DeidentifyResult.filtered(
                reason=decision.reason,
                input_file=input_file,
                parameters=parameters,
                input_attributes=input_attributes,
            )

        was_scrubbed = False
        scrub_decompressed = False
        working_file = input_file
        if decision.scrub_regions:
            blank_result = blank_regions(
                file_path=input_file,
                output_path=output_file,
                regions=decision.scrub_regions,
                highlight=highlight_blanked_pixels,
            )
            was_scrubbed = blank_result.was_scrubbed
            scrub_decompressed = blank_result.was_decompressed
            if was_scrubbed:
                working_file = output_file

        scrub_regions: frozenset[ScrubRegion] = frozenset(decision.scrub_regions) if was_scrubbed else frozenset()

        if working_file == input_file and dataset is not None:
            ds = dataset
        else:
            ds = pydicom.dcmread(working_file, force=True)

        # The pixel blanker's general path decompresses compressed input while
        # scrubbing; carry that through so was_decompressed reflects it even when
        # the optional decompress flag is not set.
        was_decompressed = scrub_decompressed
        transfer_syntax = getattr(ds.file_meta, "TransferSyntaxUID", None) if ds.file_meta is not None else None
        if decompress and transfer_syntax is not None and transfer_syntax.is_compressed:
            ds.decompress(generate_instance_uid=False)
            was_decompressed = True

        anon_profile = profile
        if decision.preserved_private_tags:
            anon_profile = dataclasses.replace(
                anon_profile,
                preserved_private_specs=frozenset(decision.preserved_private_tags),
            )
        # Clean Pixel Data (113101) is a per-instance outcome, so it is passed to
        # apply() rather than mutated onto the profile's declared options.
        applied_options = frozenset({CLEAN_PIXEL_DATA_CODE}) if was_scrubbed else frozenset()
        anon_profile.apply(ds, parameters, applied_options=applied_options)
        if was_scrubbed:
            # Burned-in identification was removed from the pixel data.
            ds.add_new(BURNED_IN_ANNOTATION_TAG, "CS", "NO")
        _regenerate_file_meta(ds)
        # Snapshot the final in-memory dataset before writing so transfer_syntax_uid
        # reads from the regenerated file_meta; this is an in-memory read only.
        output_attributes = IndexAttributes.from_dataset(ds)
        ds.save_as(output_file, enforce_file_format=True)

        if rename_to_sop_uid:
            new_sop_uid = str(ds[SOP_INSTANCE_UID_TAG].value)
            new_output = output_file.parent / f"{new_sop_uid}.dcm"
            if new_output != output_file:
                output_file.rename(new_output)
                output_file = new_output

        return DeidentifyResult.deidentified(
            output_file=output_file,
            was_decompressed=was_decompressed,
            scrub_regions=scrub_regions,
            input_file=input_file,
            parameters=parameters,
            input_attributes=input_attributes,
            output_attributes=output_attributes,
        )
    except Exception as exc:
        # Quarantine is a normal terminal outcome reported to the caller via the
        # result; keep the traceback at debug level so it does not spam stderr.
        logger.debug("Error during Python de-identification of %s: %s", input_file, exc, exc_info=True)
        return DeidentifyResult.quarantined(
            error=str(exc),
            input_file=input_file,
            parameters=parameters,
            input_attributes=input_attributes,
        )
