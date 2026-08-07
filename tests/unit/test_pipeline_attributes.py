"""Tests that deidentify_file populates result attribute snapshots.

Validates that input_file, parameters, input_attributes, and output_attributes
are set on a DEIDENTIFIED result, that the snapshots reflect the input versus the
de-identified output, and that computing them adds no file read beyond those the
pipeline already performs.

Pydicom is imported inside functions rather than at module level to avoid
triggering a GDCM segfault during pytest collection on ARM64. See the root
conftest.py pytest_configure hook for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path


DEID_PARAMETERS = {
    "PATIENT_ID": "TEST",
    "ACCESSION_NUMBER": "TEST",
    "STUDY_ID": "TEST",
    "JITTER": "10",
}


class TestPipelineAttributePopulation:
    """Result attribute population on the DEIDENTIFIED path."""

    def test_result_fields_populated(self, signa_premier_file: Path, tmp_path: Path):
        """A DEIDENTIFIED result carries input_file, parameters, and both snapshots."""
        from dicom_dre import DeidParameters
        from dicom_dre import Outcome
        from dicom_dre import build_profile
        from dicom_dre import deidentify_file
        from dicom_dre.profiles.builder import ProfileSettings

        output = tmp_path / "out.dcm"
        params = DeidParameters.from_mapping(DEID_PARAMETERS)
        profile = build_profile("default", ProfileSettings(uid_root="1.2.3"))
        result = deidentify_file(
            input_file=signa_premier_file,
            output_file=output,
            profile=profile,
            parameters=params,
            rename_to_sop_uid=False,
        )

        assert result.outcome is Outcome.DEIDENTIFIED, "Signa Premier file should be de-identified"
        assert result.input_file == signa_premier_file, "input_file should be the source path"
        assert result.parameters == params, "parameters should mirror the supplied DeidParameters"
        assert result.input_attributes is not None, "input_attributes should be populated"
        assert result.output_attributes is not None, "output_attributes should be populated"

    def test_snapshots_reflect_input_versus_output(self, signa_premier_file: Path, tmp_path: Path):
        """input_attributes hold original identifiers; output_attributes hold de-identified ones."""
        from dicom_dre import DeidParameters
        from dicom_dre import build_profile
        from dicom_dre import deidentify_file
        from dicom_dre.profiles.builder import ProfileSettings

        output = tmp_path / "out.dcm"
        profile = build_profile("default", ProfileSettings(uid_root="1.2.3"))
        result = deidentify_file(
            input_file=signa_premier_file,
            output_file=output,
            profile=profile,
            parameters=DeidParameters.from_mapping(DEID_PARAMETERS),
            rename_to_sop_uid=False,
        )

        assert result.input_attributes is not None, "input_attributes should be populated"
        assert result.output_attributes is not None, "output_attributes should be populated"
        assert result.input_attributes.patient_id == "MRN123456", "input snapshot should hold the original PatientID"
        assert result.output_attributes.patient_id == "TEST", "output snapshot should hold the de-identified PatientID"
        assert result.output_attributes.patient_identity_removed == "YES", (
            "output snapshot should record PatientIdentityRemoved=YES"
        )

    def test_no_extra_file_read(self, signa_premier_file: Path, tmp_path: Path, monkeypatch):
        """Producing both snapshots adds no dcmread beyond the metadata and working reads."""
        import pydicom

        from dicom_dre import build_profile
        from dicom_dre import deidentify_file
        from dicom_dre.profiles.builder import ProfileSettings

        calls = {"count": 0}
        original = pydicom.dcmread

        def _counting(*args, **kwargs):
            calls["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(pydicom, "dcmread", _counting)

        output = tmp_path / "out.dcm"
        from dicom_dre import DeidParameters

        profile = build_profile("default", ProfileSettings(uid_root="1.2.3"))
        deidentify_file(
            input_file=signa_premier_file,
            output_file=output,
            profile=profile,
            parameters=DeidParameters.from_mapping(DEID_PARAMETERS),
            rename_to_sop_uid=False,
        )

        # One metadata read (stop_before_pixels) plus one working-file read; the
        # snapshots are built from in-memory datasets and add no further reads.
        assert calls["count"] == 2, f"Expected 2 dcmread calls, got {calls['count']}"


def test_index_attributes_exported_from_package():
    """IndexAttributes is importable from the package root."""
    from dicom_dre import IndexAttributes

    assert IndexAttributes.__name__ == "IndexAttributes", "IndexAttributes should be exported from dicom_dre"


def _write_scrubbable_dataset(path: Path) -> None:
    """Write a small uncompressed image matching a custom scrub device rule."""
    from pydicom.dataset import Dataset
    from pydicom.dataset import FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian
    from pydicom.uid import SecondaryCaptureImageStorage
    from pydicom.uid import generate_uid

    ds = Dataset()
    ds.Modality = "OT"
    ds.Manufacturer = "TESTMFG"
    ds.ManufacturerModelName = "SCRUBBOX"
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientID = "MRN1"
    ds.BurnedInAnnotation = "YES"
    ds.Rows = 20
    ds.Columns = 20
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = b"\xc8" * (20 * 20)

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = file_meta
    ds.save_as(path, enforce_file_format=True)


def _scrub_catalog():
    """A one-device catalog that scrubs the synthetic dataset's top rows."""
    from dicom_dre.catalog import DeviceCatalog
    from dicom_dre.catalog import device
    from dicom_dre.catalog import variant

    rule = device(
        "TestScrub",
        "scrub",
        manufacturer="TESTMFG",
        modality="=OT",
        variants=[variant(rows=20, cols=20, scrub=[(0, 0, 20, 5)])],
    )
    return DeviceCatalog([rule], [])


class TestBurnedInAnnotationAfterScrub:
    """A scrubbed instance is marked BurnedInAnnotation=NO and records 113101."""

    def _code_values(self, ds) -> set[str]:
        from pydicom.tag import Tag

        return {str(item[Tag(0x0008, 0x0100)].value) for item in ds[Tag(0x0012, 0x0064)].value}

    def _run(self, tmp_path: Path):
        import pydicom

        from dicom_dre import DeidParameters
        from dicom_dre import Outcome
        from dicom_dre import build_profile
        from dicom_dre import deidentify_file
        from dicom_dre.profiles.builder import ProfileSettings

        source = tmp_path / "scrubbable.dcm"
        _write_scrubbable_dataset(source)
        output = tmp_path / "out.dcm"

        profile = build_profile("default", ProfileSettings(uid_root="1.2.3"))
        result = deidentify_file(
            input_file=source,
            output_file=output,
            profile=profile,
            parameters=DeidParameters.from_mapping(DEID_PARAMETERS),
            catalog=_scrub_catalog(),
            rename_to_sop_uid=False,
        )
        assert result.outcome is Outcome.DEIDENTIFIED, f"expected DEIDENTIFIED, got {result.outcome.name}"
        assert result.scrub_regions, "scrub_regions should be recorded on the result"
        return result, pydicom.dcmread(output, force=True)

    def test_burned_in_annotation_set_to_no(self, tmp_path: Path):
        """BurnedInAnnotation is set to NO in the scrubbed output."""
        from pydicom.tag import Tag

        result, ds = self._run(tmp_path)
        assert str(ds[Tag(0x0028, 0x0301)].value) == "NO", "BurnedInAnnotation should be NO after scrubbing"
        assert result.output_attributes is not None, "output_attributes should be populated"
        assert result.output_attributes.burned_in_annotation == "NO", "output snapshot should record NO"

    def test_clean_pixel_data_code_recorded(self, tmp_path: Path):
        """The De-identification Method Code Sequence records 113101."""
        _result, ds = self._run(tmp_path)
        assert "113101" in self._code_values(ds), "113101 (Clean Pixel Data Option) should be recorded"


class TestBurnedInAnnotationWithoutScrub:
    """An unscrubbed instance leaves BurnedInAnnotation and omits 113101."""

    def test_no_flag_change_without_scrub(self, signa_premier_file: Path, tmp_path: Path):
        """Without scrub regions, BurnedInAnnotation is not forced and 113101 is absent."""
        import pydicom
        from pydicom.tag import Tag

        from dicom_dre import DeidParameters
        from dicom_dre import build_profile
        from dicom_dre import deidentify_file
        from dicom_dre.profiles.builder import ProfileSettings

        output = tmp_path / "out.dcm"
        profile = build_profile("default", ProfileSettings(uid_root="1.2.3"))
        result = deidentify_file(
            input_file=signa_premier_file,
            output_file=output,
            profile=profile,
            parameters=DeidParameters.from_mapping(DEID_PARAMETERS),
            rename_to_sop_uid=False,
        )
        assert not result.scrub_regions, "signa premier fixture is allowed without scrubbing"
        ds = pydicom.dcmread(output, force=True)
        codes = {str(item[Tag(0x0008, 0x0100)].value) for item in ds[Tag(0x0012, 0x0064)].value}
        assert "113101" not in codes, "113101 should not be recorded without a pixel scrub"
