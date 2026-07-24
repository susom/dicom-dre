"""Shared fixtures for deidentifyr unit tests.

Provides a synthetic GE SIGNA Premier MR instance that matches the device
catalog rule carrying preserved private-tag specs. The dataset is built
programmatically (no PHI, no committed binary) and written to a temporary
path so tests can exercise the pipeline end to end.

Pydicom is imported inside functions rather than at module level to avoid
triggering a GDCM segfault during pytest collection on ARM64. See the root
conftest.py pytest_configure hook for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from pathlib import Path

    from pydicom.dataset import Dataset


# Preserved private elements for the GE SIGNA Premier MR rule, in block 0x10,
# as (group, element, VR, value). Element numbers use the 0x10 creator block.
PRESERVED_ELEMENTS = [
    (0x0019, 0x10BB, "DS", "0"),
    (0x0019, 0x10BC, "DS", "0"),
    (0x0019, 0x10BD, "DS", "0"),
    (0x0043, 0x102F, "SS", 3),
]
# Creator elements for the two preserved private groups, as (group, element, value).
CREATOR_ELEMENTS = [
    (0x0019, 0x0010, "GEMS_ACQU_01"),
    (0x0043, 0x0010, "GEMS_PARM_01"),
]
# Private elements that must be removed by global private-group removal,
# as (group, element, VR, value).
DECOY_PRIVATE_ELEMENTS = [
    (0x0019, 0x109C, "LO", "SWAN"),
    (0x0043, 0x1030, "SS", 7),
]
# Standard identifier tags that normal de-identification must scrub,
# as (group, element, VR, value).
PHI_ELEMENTS = [
    (0x0010, 0x0010, "PN", "DOE^JANE"),  # PatientName
    (0x0010, 0x0020, "LO", "MRN123456"),  # PatientID
    (0x0010, 0x0030, "DA", "19700101"),  # PatientBirthDate
    (0x0008, 0x0050, "SH", "ACC987654"),  # AccessionNumber
    (0x0008, 0x0020, "DA", "20230601"),  # StudyDate
]


def _build_signa_premier_dataset() -> Dataset:
    """Build a synthetic GE SIGNA Premier MR dataset with no PHI.

    The dataset carries the scanner identity that the catalog rule matches,
    the four preserved private elements plus their creators, decoy private
    elements that must be removed, and standard identifier tags that normal
    de-identification must scrub. Private-creator values are space padded to
    exercise creator-block resolution.
    """
    from pydicom.dataset import Dataset
    from pydicom.dataset import FileMetaDataset
    from pydicom.tag import Tag
    from pydicom.uid import ExplicitVRLittleEndian
    from pydicom.uid import MRImageStorage
    from pydicom.uid import generate_uid

    ds = Dataset()

    # Scanner identity — matches "GE SIGNA Premier MR - preserved private tags".
    ds.add_new(Tag(0x0008, 0x0060), "CS", "MR")  # Modality
    ds.add_new(Tag(0x0008, 0x0070), "LO", "GE MEDICAL SYSTEMS")  # Manufacturer
    ds.add_new(Tag(0x0008, 0x1090), "LO", "SIGNA Premier")  # ManufacturerModelName
    ds.add_new(Tag(0x0008, 0x0008), "CS", ["ORIGINAL", "PRIMARY", "OTHER"])  # ImageType

    # Required identity UIDs.
    ds.add_new(Tag(0x0008, 0x0016), "UI", MRImageStorage)  # SOPClassUID
    ds.add_new(Tag(0x0008, 0x0018), "UI", generate_uid())  # SOPInstanceUID
    ds.add_new(Tag(0x0020, 0x000D), "UI", generate_uid())  # StudyInstanceUID
    ds.add_new(Tag(0x0020, 0x000E), "UI", generate_uid())  # SeriesInstanceUID

    # Standard identifiers that normal de-identification must scrub.
    for group, element, vr, value in PHI_ELEMENTS:
        ds.add_new(Tag(group, element), vr, value)

    # Private creators (space padded) and their preserved data elements.
    for group, element, creator_value in CREATOR_ELEMENTS:
        ds.add_new(Tag(group, element), "LO", f"{creator_value} ")
    for group, element, vr, value in PRESERVED_ELEMENTS:
        ds.add_new(Tag(group, element), vr, value)

    # Decoy private elements that must be removed.
    for group, element, vr, value in DECOY_PRIVATE_ELEMENTS:
        ds.add_new(Tag(group, element), vr, value)

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = MRImageStorage
    file_meta.MediaStorageSOPInstanceUID = ds[Tag(0x0008, 0x0018)].value
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = file_meta

    return ds


@pytest.fixture()
def signa_premier_file(tmp_path: Path) -> Path:
    """Write a synthetic SIGNA Premier MR file and return its path."""
    ds = _build_signa_premier_dataset()
    path = tmp_path / "signa_premier.dcm"
    ds.save_as(path, enforce_file_format=True)
    return path
