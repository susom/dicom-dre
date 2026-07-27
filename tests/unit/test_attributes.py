"""Tests for the IndexAttributes DICOM attribute snapshot.

Validates typed extraction from a dataset and a file, the present-vs-absent
convention, multi-valued and special-cased fields, hashability of the frozen
snapshot, and that from_file does not read pixel data.

Pydicom is imported inside functions rather than at module level to avoid
triggering a GDCM segfault during pytest collection on ARM64. See the root
conftest.py pytest_configure hook for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path

    from pydicom.dataset import Dataset


def _build_dataset() -> Dataset:
    """Build a small dataset exercising scalar, int, multi-valued, and sequence fields."""
    from pydicom.dataset import Dataset
    from pydicom.dataset import FileMetaDataset
    from pydicom.tag import Tag
    from pydicom.uid import ExplicitVRLittleEndian
    from pydicom.uid import MRImageStorage
    from pydicom.uid import generate_uid

    ds = Dataset()
    ds.add_new(Tag(0x0008, 0x0016), "UI", MRImageStorage)  # SOPClassUID
    ds.add_new(Tag(0x0008, 0x0018), "UI", generate_uid())  # SOPInstanceUID
    ds.add_new(Tag(0x0020, 0x000D), "UI", generate_uid())  # StudyInstanceUID
    ds.add_new(Tag(0x0020, 0x000E), "UI", generate_uid())  # SeriesInstanceUID
    ds.add_new(Tag(0x0008, 0x0050), "SH", "ACC987654")  # AccessionNumber
    ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN123456")  # PatientID
    ds.add_new(Tag(0x0010, 0x0010), "PN", "DOE^JANE")  # PatientName
    ds.add_new(Tag(0x0008, 0x0060), "CS", "MR")  # Modality
    ds.add_new(Tag(0x0008, 0x0008), "CS", ["ORIGINAL", "PRIMARY", "OTHER"])  # ImageType
    ds.add_new(Tag(0x0028, 0x0010), "US", 512)  # Rows
    ds.add_new(Tag(0x0028, 0x0011), "US", 256)  # Columns
    ds.add_new(Tag(0x0020, 0x0013), "IS", "7")  # InstanceNumber

    # ProcedureCodeSequence with one item carrying a CodeValue.
    item = Dataset()
    item.add_new(Tag(0x0008, 0x0100), "SH", "CODE42")  # CodeValue
    ds.add_new(Tag(0x0008, 0x1032), "SQ", [item])  # ProcedureCodeSequence

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = MRImageStorage
    file_meta.MediaStorageSOPInstanceUID = ds[Tag(0x0008, 0x0018)].value
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = file_meta
    return ds


class TestIndexAttributesFromDataset:
    """Extraction from an in-memory dataset."""

    def test_scalar_string_fields(self):
        """Scalar string elements are captured as strings."""
        from dicom_dre.attributes import IndexAttributes

        attrs = IndexAttributes.from_dataset(_build_dataset())
        assert attrs.accession_number == "ACC987654", "AccessionNumber should be captured"
        assert attrs.patient_id == "MRN123456", "PatientID should be captured"
        assert attrs.patient_name == "DOE^JANE", "PatientName should be captured as a string"
        assert attrs.modality == "MR", "Modality should be captured"

    def test_int_fields(self):
        """Numeric elements are captured as ints."""
        from dicom_dre.attributes import IndexAttributes

        attrs = IndexAttributes.from_dataset(_build_dataset())
        assert attrs.rows == 512, "Rows should be an int"
        assert attrs.columns == 256, "Columns should be an int"
        assert attrs.instance_number == 7, "InstanceNumber should be parsed to int"

    def test_multivalued_field_is_tuple(self):
        """Multi-valued elements are captured as tuples of strings."""
        from dicom_dre.attributes import IndexAttributes

        attrs = IndexAttributes.from_dataset(_build_dataset())
        assert attrs.image_type == ("ORIGINAL", "PRIMARY", "OTHER"), "ImageType should be a tuple"

    def test_transfer_syntax_uid_from_file_meta(self):
        """Transfer Syntax UID is sourced from the File Meta group."""
        from pydicom.uid import ExplicitVRLittleEndian

        from dicom_dre.attributes import IndexAttributes

        attrs = IndexAttributes.from_dataset(_build_dataset())
        assert attrs.transfer_syntax_uid == str(ExplicitVRLittleEndian), (
            "Transfer Syntax UID should come from file_meta"
        )

    def test_transfer_syntax_uid_none_without_file_meta(self):
        """A dataset with no file_meta yields a None transfer_syntax_uid."""
        from pydicom.dataset import Dataset
        from pydicom.tag import Tag

        from dicom_dre.attributes import IndexAttributes

        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN123456")  # PatientID
        attrs = IndexAttributes.from_dataset(ds)
        assert attrs.transfer_syntax_uid is None, "Absent file_meta should yield None"

    def test_procedure_code_sequence_first_code_value(self):
        """ProcedureCodeSequence resolves to the first item's CodeValue."""
        from dicom_dre.attributes import IndexAttributes

        attrs = IndexAttributes.from_dataset(_build_dataset())
        assert attrs.procedure_code_sequence == "CODE42", "First item CodeValue should be extracted"

    def test_absent_element_is_none(self):
        """An absent element is reported as None."""
        from dicom_dre.attributes import IndexAttributes

        attrs = IndexAttributes.from_dataset(_build_dataset())
        assert attrs.study_description is None, "Absent StudyDescription should be None"
        assert attrs.referring_physician_name is None, "Absent physician should be None"

    def test_snapshot_is_hashable(self):
        """The frozen snapshot with tuple fields is hashable."""
        from dicom_dre.attributes import IndexAttributes

        attrs = IndexAttributes.from_dataset(_build_dataset())
        assert isinstance(hash(attrs), int), "Snapshot should be hashable"


class TestIndexAttributesFromFile:
    """Extraction from a file on disk."""

    def test_from_file_equals_from_dataset(self, tmp_path: Path):
        """from_file and from_dataset return equal snapshots for the same dataset."""
        from dicom_dre.attributes import IndexAttributes

        ds = _build_dataset()
        path = tmp_path / "sample.dcm"
        ds.save_as(path, enforce_file_format=True)
        from_file = IndexAttributes.from_file(path)
        from_dataset = IndexAttributes.from_dataset(ds)
        assert from_file == from_dataset, "from_file and from_dataset should be equal"

    def test_from_file_does_not_read_pixels(self, tmp_path: Path, monkeypatch):
        """from_file reads with stop_before_pixels=True."""
        import pydicom

        from dicom_dre.attributes import IndexAttributes

        ds = _build_dataset()
        path = tmp_path / "sample.dcm"
        ds.save_as(path, enforce_file_format=True)

        captured: dict[str, object] = {}
        original = pydicom.dcmread

        def _spy(*args, **kwargs):
            captured.update(kwargs)
            return original(*args, **kwargs)

        monkeypatch.setattr(pydicom, "dcmread", _spy)
        IndexAttributes.from_file(path)
        assert captured.get("stop_before_pixels") is True, "from_file should read with stop_before_pixels=True"
