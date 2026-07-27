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
    "UIDROOT": "1.2.3",
}


class TestPipelineAttributePopulation:
    """Result attribute population on the DEIDENTIFIED path."""

    def test_result_fields_populated(self, signa_premier_file: Path, tmp_path: Path):
        """A DEIDENTIFIED result carries input_file, parameters, and both snapshots."""
        from dicom_dre import DeidParameters
        from dicom_dre import Outcome
        from dicom_dre import build_profile
        from dicom_dre import deidentify_file

        output = tmp_path / "out.dcm"
        params = DeidParameters.from_mapping(DEID_PARAMETERS)
        profile = build_profile("default", dict(DEID_PARAMETERS))
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

        output = tmp_path / "out.dcm"
        profile = build_profile("default", dict(DEID_PARAMETERS))
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

        calls = {"count": 0}
        original = pydicom.dcmread

        def _counting(*args, **kwargs):
            calls["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(pydicom, "dcmread", _counting)

        output = tmp_path / "out.dcm"
        from dicom_dre import DeidParameters

        profile = build_profile("default", dict(DEID_PARAMETERS))
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
