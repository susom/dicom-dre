"""End-to-end pipeline tests for device-scoped private-tag preservation.

Runs the real de-identification pipeline against a synthetic GE SIGNA
Premier MR file and asserts the preserved private elements survive verbatim,
all other private tags are removed, standard identifiers are scrubbed, and the
De-identification Method Code Sequence (0012,0064) is emitted with the correct
codes per profile.

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


DEID_PARAMETERS = {
    "PATIENT_ID": "TEST",
    "ACCESSION_NUMBER": "TEST",
    "STUDY_ID": "TEST",
    "JITTER": "10",
    "UIDROOT": "1.2.3",
}

# Preserved data element tags, as (group, element).
PRESERVED_DATA_TAGS = [
    (0x0019, 0x10BB),
    (0x0019, 0x10BC),
    (0x0019, 0x10BD),
    (0x0043, 0x102F),
]
CREATOR_TAGS = [(0x0019, 0x0010), (0x0043, 0x0010)]
DECOY_PRIVATE_TAGS = [(0x0019, 0x109C), (0x0043, 0x1030)]
METHOD_CODE_SEQUENCE_TAG = (0x0012, 0x0064)


def _deidentify(
    signa_premier_file: Path,
    tmp_path: Path,
    profile_name: str,
    deid_parameters: dict[str, str] | None = None,
) -> Dataset:
    """Run the pipeline for a profile and return the output dataset."""
    import pydicom

    from dicom_dre import Outcome
    from dicom_dre import build_profile
    from dicom_dre import deidentify_file

    output = tmp_path / f"out_{profile_name}.dcm"
    parameters = dict(deid_parameters) if deid_parameters is not None else dict(DEID_PARAMETERS)
    profile = build_profile(profile_name, parameters)
    result = deidentify_file(
        input_file=signa_premier_file,
        output_file=output,
        profile=profile,
        rename_to_sop_uid=False,
    )
    if result.outcome is not Outcome.DEIDENTIFIED:
        raise AssertionError(f"Expected DEIDENTIFIED, got {result.outcome.name}")
    return pydicom.dcmread(output, force=True)


def _code_values(ds: Dataset) -> set[str]:
    """Return the set of CodeValue strings in (0012,0064)."""
    from pydicom.tag import Tag

    mcs_tag = Tag(*METHOD_CODE_SEQUENCE_TAG)
    if mcs_tag not in ds:
        return set()
    return {str(item[Tag(0x0008, 0x0100)].value) for item in ds[mcs_tag].value}


class TestPreservationRoundTrip:
    """The pipeline preserves approved private tags end to end."""

    def test_preserved_elements_survive_verbatim(self, signa_premier_file, tmp_path):
        """The four preserved elements survive with input values unchanged."""
        import pydicom
        from pydicom.tag import Tag

        source = pydicom.dcmread(signa_premier_file, force=True)
        ds = _deidentify(signa_premier_file, tmp_path, "default")
        for group, element in PRESERVED_DATA_TAGS:
            tag = Tag(group, element)
            assert tag in ds, f"Preserved element {tag} was removed"
            assert str(ds[tag].value) == str(source[tag].value), (
                f"{tag} value changed: input {source[tag].value!r}, output {ds[tag].value!r}"
            )

    def test_creator_elements_survive(self, signa_premier_file, tmp_path):
        """Both preserved private creator elements survive."""
        from pydicom.tag import Tag

        ds = _deidentify(signa_premier_file, tmp_path, "default")
        for group, element in CREATOR_TAGS:
            tag = Tag(group, element)
            assert tag in ds, f"Preserved creator element {tag} was removed"

    def test_decoy_private_tags_removed(self, signa_premier_file, tmp_path):
        """Private tags not on the preserve list are removed."""
        from pydicom.tag import Tag

        ds = _deidentify(signa_premier_file, tmp_path, "default")
        for group, element in DECOY_PRIVATE_TAGS:
            tag = Tag(group, element)
            assert tag not in ds, f"Non-preserved private tag {tag} should have been removed"

    def test_only_preserved_private_tags_remain(self, signa_premier_file, tmp_path):
        """The sole residual private tags are the preserved elements and creators."""
        from pydicom.tag import Tag

        ds = _deidentify(signa_premier_file, tmp_path, "default")
        residual = {e.tag for e in ds if e.tag.is_private}
        expected = {Tag(g, e) for g, e in PRESERVED_DATA_TAGS} | {Tag(g, e) for g, e in CREATOR_TAGS}
        assert residual == expected, f"Residual private tags {residual} do not match expected {expected}"

    def test_standard_identifiers_scrubbed(self, signa_premier_file, tmp_path):
        """Normal de-identification still scrubs standard identifier tags."""
        import pydicom
        from pydicom.tag import Tag

        source = pydicom.dcmread(signa_premier_file, force=True)
        ds = _deidentify(signa_premier_file, tmp_path, "default")
        patient_name_tag = Tag(0x0010, 0x0010)
        # PatientName is replaced with the parameter value, not the source PHI.
        assert str(ds[patient_name_tag].value) != str(source[patient_name_tag].value), (
            "PatientName was not scrubbed; output retains the source value"
        )


class TestPreservationMethodCode:
    """(0012,0064) is emitted with profile-correct codes."""

    def test_default_profile_emits_modified_dates_code(self, signa_premier_file, tmp_path):
        """The date-shifting default profile emits 113100, 113111, and 113107."""
        ds = _deidentify(signa_premier_file, tmp_path, "default")
        codes = _code_values(ds)
        assert codes == {"113100", "113111", "113107"}, f"Unexpected (0012,0064) codes for default profile: {codes}"

    @pytest.mark.parametrize("profile_name", ["lds", "lds-no-dob", "pixels-only"])
    def test_non_date_shifting_profiles_omit_modified_dates_code(self, signa_premier_file, tmp_path, profile_name):
        """Date-preserving and date-removing profiles omit 113107."""
        ds = _deidentify(signa_premier_file, tmp_path, profile_name)
        codes = _code_values(ds)
        assert "113100" in codes, f"113100 missing for profile {profile_name}: {codes}"
        assert "113111" in codes, f"113111 missing for profile {profile_name}: {codes}"
        assert "113107" not in codes, f"113107 should be absent for profile {profile_name}: {codes}"

    @pytest.mark.parametrize("profile_name", ["default", "lds", "lds-no-dob", "pixels-only"])
    def test_preserved_elements_survive_all_profiles(self, signa_premier_file, tmp_path, profile_name):
        """Preservation applies regardless of profile."""
        from pydicom.tag import Tag

        ds = _deidentify(signa_premier_file, tmp_path, profile_name)
        for group, element in PRESERVED_DATA_TAGS:
            tag = Tag(group, element)
            assert tag in ds, f"Preserved element {tag} removed under profile {profile_name}"


class TestPatientNameMapping:
    """PatientName (0010,0010) is bound from PATIENT_NAME with PATIENT_ID fallback."""

    PATIENT_NAME_TAG = (0x0010, 0x0010)

    @pytest.mark.parametrize("profile_name", ["default", "lds", "lds-no-dob", "pixels-only"])
    def test_patient_name_set_from_parameter_when_provided(self, signa_premier_file, tmp_path, profile_name):
        """PatientName is set to PATIENT_NAME when the parameter is supplied."""
        from pydicom.tag import Tag

        parameters = dict(DEID_PARAMETERS)
        parameters["PATIENT_NAME"] = "ANON^NAME"
        ds = _deidentify(signa_premier_file, tmp_path, profile_name, deid_parameters=parameters)
        tag = Tag(*self.PATIENT_NAME_TAG)
        assert str(ds[tag].value) == "ANON^NAME", (
            f"PatientName not set from PATIENT_NAME under profile {profile_name}: got {ds[tag].value!r}"
        )

    @pytest.mark.parametrize("profile_name", ["default", "lds", "lds-no-dob", "pixels-only"])
    def test_patient_name_falls_back_to_patient_id_when_absent(self, signa_premier_file, tmp_path, profile_name):
        """PatientName falls back to PATIENT_ID when PATIENT_NAME is not supplied."""
        from pydicom.tag import Tag

        parameters = dict(DEID_PARAMETERS)
        parameters.pop("PATIENT_NAME", None)
        ds = _deidentify(signa_premier_file, tmp_path, profile_name, deid_parameters=parameters)
        tag = Tag(*self.PATIENT_NAME_TAG)
        assert str(ds[tag].value) == parameters["PATIENT_ID"], (
            f"PatientName did not fall back to PATIENT_ID under profile {profile_name}: got {ds[tag].value!r}"
        )
