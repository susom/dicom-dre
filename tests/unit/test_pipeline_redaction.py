"""Engine-level tests for free-text description redaction in deidentify_file.

The pipeline redacts SeriesDescription, StudyDescription, and
ProtocolName from the dataset using the profile's allowlist unless the caller
supplies a pre-redacted value, which takes precedence.

Pydicom is imported inside functions rather than at module level to avoid
triggering a GDCM segfault during pytest collection on ARM64. See the root
conftest.py pytest_configure hook for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path

    from pydicom.dataset import Dataset


# An allowlisted anatomy token and a PHI-like surname absent from default.csv.
ALLOWLISTED_WORD = "Chest"
UNLISTED_WORD = "Zzytkiewicz"

DEID_PARAMETERS = {
    "PATIENT_ID": "TEST",
    "ACCESSION_NUMBER": "TEST",
    "STUDY_ID": "TEST",
    "JITTER": "10",
    "UIDROOT": "1.2.3",
}


def _write_dataset_with_descriptions(path: Path) -> None:
    """Write a minimal MR file carrying free-text description fields."""
    from pydicom.dataset import Dataset
    from pydicom.dataset import FileMetaDataset
    from pydicom.tag import Tag
    from pydicom.uid import ExplicitVRLittleEndian
    from pydicom.uid import MRImageStorage
    from pydicom.uid import generate_uid

    ds = Dataset()
    ds.add_new(Tag(0x0008, 0x0060), "CS", "MR")  # Modality
    ds.add_new(Tag(0x0008, 0x0070), "LO", "GE MEDICAL SYSTEMS")  # Manufacturer
    ds.add_new(Tag(0x0008, 0x1090), "LO", "SIGNA Premier")  # ManufacturerModelName
    ds.add_new(Tag(0x0008, 0x0008), "CS", ["ORIGINAL", "PRIMARY", "OTHER"])  # ImageType
    ds.add_new(Tag(0x0008, 0x0016), "UI", MRImageStorage)  # SOPClassUID
    ds.add_new(Tag(0x0008, 0x0018), "UI", generate_uid())  # SOPInstanceUID
    ds.add_new(Tag(0x0020, 0x000D), "UI", generate_uid())  # StudyInstanceUID
    ds.add_new(Tag(0x0020, 0x000E), "UI", generate_uid())  # SeriesInstanceUID

    ds.add_new(Tag(0x0008, 0x103E), "LO", f"{ALLOWLISTED_WORD} {UNLISTED_WORD}")  # SeriesDescription
    ds.add_new(Tag(0x0008, 0x1030), "LO", f"{ALLOWLISTED_WORD} {UNLISTED_WORD}")  # StudyDescription
    ds.add_new(Tag(0x0018, 0x1030), "LO", f"{ALLOWLISTED_WORD} {UNLISTED_WORD}")  # ProtocolName

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = MRImageStorage
    file_meta.MediaStorageSOPInstanceUID = ds[Tag(0x0008, 0x0018)].value
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = file_meta
    ds.save_as(path, enforce_file_format=True)


def _deidentify(input_file: Path, output: Path, parameters: dict[str, str]) -> Dataset:
    """Run deidentify_file with the default profile and return the output dataset."""
    import pydicom

    from dicom_dre import Outcome
    from dicom_dre import build_profile
    from dicom_dre import deidentify_file

    profile = build_profile("default", parameters)
    result = deidentify_file(
        input_file=input_file,
        output_file=output,
        profile=profile,
        rename_to_sop_uid=False,
    )
    if result.outcome is not Outcome.DEIDENTIFIED:
        raise AssertionError(f"Expected DEIDENTIFIED, got {result.outcome.name}")
    return pydicom.dcmread(output, force=True)


class TestDescriptionRedaction:
    """deidentify_file redacts description fields from the dataset."""

    def test_unlisted_token_redacted_allowlisted_kept(self, tmp_path):
        """An unlisted token is masked while an allowlisted token survives."""
        from pydicom.tag import Tag

        source = tmp_path / "descriptions.dcm"
        _write_dataset_with_descriptions(source)
        output = tmp_path / "out.dcm"

        ds = _deidentify(source, output, dict(DEID_PARAMETERS))

        series_description = str(ds[Tag(0x0008, 0x103E)].value)
        assert ALLOWLISTED_WORD in series_description, f"Allowlisted token should survive, got {series_description!r}"
        assert UNLISTED_WORD not in series_description, f"Unlisted token should be redacted, got {series_description!r}"
        assert "X" * len(UNLISTED_WORD) in series_description, (
            f"Unlisted token should be masked with X, got {series_description!r}"
        )

    def test_all_description_fields_redacted(self, tmp_path):
        """SeriesDescription, StudyDescription, and ProtocolName are all redacted."""
        from pydicom.tag import Tag

        source = tmp_path / "descriptions.dcm"
        _write_dataset_with_descriptions(source)
        output = tmp_path / "out.dcm"

        ds = _deidentify(source, output, dict(DEID_PARAMETERS))

        for tag, name in (
            (Tag(0x0008, 0x103E), "SeriesDescription"),
            (Tag(0x0008, 0x1030), "StudyDescription"),
            (Tag(0x0018, 0x1030), "ProtocolName"),
        ):
            value = str(ds[tag].value)
            assert UNLISTED_WORD not in value, f"{name} should be redacted, got {value!r}"

    def test_caller_value_takes_precedence(self, tmp_path):
        """A caller-supplied SERIES_DESCRIPTION overrides dataset redaction."""
        from pydicom.tag import Tag

        source = tmp_path / "descriptions.dcm"
        _write_dataset_with_descriptions(source)
        output = tmp_path / "out.dcm"

        parameters = dict(DEID_PARAMETERS)
        parameters["SERIES_DESCRIPTION"] = "OVERRIDE VALUE"

        ds = _deidentify(source, output, parameters)

        series_description = str(ds[Tag(0x0008, 0x103E)].value)
        assert series_description == "OVERRIDE VALUE", (
            f"Caller value should take precedence, got {series_description!r}"
        )
