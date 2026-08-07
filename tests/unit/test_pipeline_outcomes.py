"""Terminal-outcome contract for deidentify_file and DeidentifyResult.

Covers the FILTERED path (a catalog rule denies the input) and the QUARANTINED
path (a processing error), asserting the outcome, the reason/error field, and the
mutually exclusive boolean properties. The DEIDENTIFIED path is covered elsewhere.

Pydicom and dicom_dre are imported inside test functions rather than at module
level to avoid a GDCM segfault during pytest collection on ARM64. See the root
conftest.py pytest_configure hook for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path


class TestFilteredOutcome:
    """A catalog denial produces a FILTERED result and writes no output."""

    def test_denied_input_is_filtered(self, signa_premier_file: Path, tmp_path: Path):
        """deidentify_file returns FILTERED with a reason when the catalog denies the input."""
        from dicom_dre import DeidParameters
        from dicom_dre import Outcome
        from dicom_dre import build_profile
        from dicom_dre import deidentify_file
        from dicom_dre.catalog import DeviceCatalog
        from dicom_dre.catalog import deny_modalities
        from dicom_dre.profiles.builder import ProfileSettings

        output = tmp_path / "out.dcm"
        catalog = DeviceCatalog([], [deny_modalities(exact=["MR"])])
        result = deidentify_file(
            input_file=signa_premier_file,
            output_file=output,
            profile=build_profile("default", ProfileSettings(uid_root="1.2.3")),
            parameters=DeidParameters(jitter=10),
            catalog=catalog,
        )

        assert result.outcome is Outcome.FILTERED, f"denied MR input should be FILTERED, got {result.outcome}"
        assert result.filter_reason, f"FILTERED result should carry a non-empty reason, got {result.filter_reason!r}"
        assert result.was_filtered is True, "was_filtered should be True on a FILTERED result"
        assert result.was_deidentified is False, "was_deidentified should be False on a FILTERED result"
        assert result.was_quarantined is False, "was_quarantined should be False on a FILTERED result"
        assert result.output_file is None, "a FILTERED result should have no output_file"
        assert not output.exists(), "no output file should be written when the input is filtered"


class TestQuarantinedOutcome:
    """A processing error produces a QUARANTINED result with the error recorded."""

    def test_quarantined_result_property_contract(self):
        """A directly constructed QUARANTINED result exposes the error and boolean contract."""
        from pathlib import Path

        from dicom_dre import Outcome
        from dicom_dre.result import DeidentifyResult

        result = DeidentifyResult.quarantined("boom", input_file=Path("in.dcm"))
        assert result.outcome is Outcome.QUARANTINED, "outcome should be QUARANTINED"
        assert result.error == "boom", f"error should be recorded, got {result.error!r}"
        assert result.was_quarantined is True, "was_quarantined should be True"
        assert result.was_deidentified is False, "was_deidentified should be False on a QUARANTINED result"
        assert result.was_filtered is False, "was_filtered should be False on a QUARANTINED result"
        assert result.output_file is None, "a QUARANTINED result should have no output_file"

    def test_unreadable_input_is_quarantined(self, tmp_path: Path):
        """deidentify_file quarantines an input that cannot be read as DICOM."""
        from dicom_dre import DeidParameters
        from dicom_dre import Outcome
        from dicom_dre import build_profile
        from dicom_dre import deidentify_file
        from dicom_dre.profiles.builder import ProfileSettings

        bad_input = tmp_path / "not_dicom.dcm"
        bad_input.write_bytes(b"this is not a DICOM file")
        output = tmp_path / "out.dcm"
        result = deidentify_file(
            input_file=bad_input,
            output_file=output,
            profile=build_profile("default", ProfileSettings(uid_root="1.2.3")),
            parameters=DeidParameters(jitter=10),
        )

        assert result.outcome is Outcome.QUARANTINED, f"unreadable input should be QUARANTINED, got {result.outcome}"
        assert result.error, f"QUARANTINED result should carry a non-empty error, got {result.error!r}"
        assert result.was_quarantined is True, "was_quarantined should be True on a QUARANTINED result"
        assert result.was_deidentified is False, "was_deidentified should be False on a QUARANTINED result"
