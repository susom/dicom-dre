"""Canonical profile builder.

Provides profile-name dispatch, JITTER parsing, and the per-profile parameter
defaults. Given a profile name and a runtime parameter dict,
:func:`build_profile` returns a fully-bound :class:`DeidProfile` ready
for ``apply()``.

The parameter dict is consumed as-is: the library performs no hashing, no
settings lookups, and no free-text redaction. Callers supply already-hashed and
already-redacted values.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dicom_dre.profiles.default import default_profile
from dicom_dre.profiles.lds import lds_profile
from dicom_dre.profiles.lds_no_dob import lds_no_dob_profile
from dicom_dre.profiles.pixels_only import pixels_only_profile


if TYPE_CHECKING:
    from dicom_dre.profile import DeidProfile


# Fallback values for de-identification parameters not supplied at runtime.
# These fill placeholder identifiers and the UID-hash salt so the engine
# produces deterministic output when optional parameters are absent.
_DEFAULT_PLACEHOLDER = "######"  # PATIENT_ID/ACCESSION_NUMBER placeholder when absent
_DEFAULT_STUDY_ID = "UNKNOWN"  # STUDY_ID (UID-hash salt via ClinicalTrialProtocolID) when absent
_DEFAULT_UID_ROOT = "1.2.840.4267.32."
_DEFAULT_ALLOWLIST_CSV = "default.csv"  # free-text redaction allowlist when absent


def _build_default(parameters: dict[str, str]) -> DeidProfile:
    jitter_value = parameters.get("JITTER", "10")
    try:
        jitter = int(jitter_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"JITTER parameter must be an integer, got {jitter_value!r}") from exc

    return default_profile(
        patient_id=parameters.get("PATIENT_ID", _DEFAULT_PLACEHOLDER),
        accession_number=parameters.get("ACCESSION_NUMBER", _DEFAULT_PLACEHOLDER),
        study_id=parameters.get("STUDY_ID", _DEFAULT_STUDY_ID),
        jitter=jitter,
        uid_root=parameters.get("UIDROOT", _DEFAULT_UID_ROOT),
        series_description=parameters.get("SERIES_DESCRIPTION"),
        study_description=parameters.get("STUDY_DESCRIPTION"),
        protocol_name=parameters.get("PROTOCOL_NAME"),
        patient_name=parameters.get("PATIENT_NAME"),
        allowlist_csv=parameters.get("ALLOWLIST_CSV", _DEFAULT_ALLOWLIST_CSV),
    )


def _build_lds(parameters: dict[str, str]) -> DeidProfile:
    return lds_profile(
        patient_id=parameters.get("PATIENT_ID", _DEFAULT_PLACEHOLDER),
        accession_number=parameters.get("ACCESSION_NUMBER", _DEFAULT_PLACEHOLDER),
        study_id=parameters.get("STUDY_ID", _DEFAULT_STUDY_ID),
        uid_root=parameters.get("UIDROOT", _DEFAULT_UID_ROOT),
        series_description=parameters.get("SERIES_DESCRIPTION"),
        study_description=parameters.get("STUDY_DESCRIPTION"),
        protocol_name=parameters.get("PROTOCOL_NAME"),
        patient_name=parameters.get("PATIENT_NAME"),
        allowlist_csv=parameters.get("ALLOWLIST_CSV", _DEFAULT_ALLOWLIST_CSV),
    )


def _build_lds_no_dob(parameters: dict[str, str]) -> DeidProfile:
    return lds_no_dob_profile(
        patient_id=parameters.get("PATIENT_ID", _DEFAULT_PLACEHOLDER),
        accession_number=parameters.get("ACCESSION_NUMBER", _DEFAULT_PLACEHOLDER),
        study_id=parameters.get("STUDY_ID", _DEFAULT_STUDY_ID),
        uid_root=parameters.get("UIDROOT", _DEFAULT_UID_ROOT),
        series_description=parameters.get("SERIES_DESCRIPTION"),
        study_description=parameters.get("STUDY_DESCRIPTION"),
        protocol_name=parameters.get("PROTOCOL_NAME"),
        patient_name=parameters.get("PATIENT_NAME"),
        allowlist_csv=parameters.get("ALLOWLIST_CSV", _DEFAULT_ALLOWLIST_CSV),
    )


def _build_pixels_only(parameters: dict[str, str]) -> DeidProfile:
    return pixels_only_profile(
        patient_id=parameters.get("PATIENT_ID", _DEFAULT_PLACEHOLDER),
        accession_number=parameters.get("ACCESSION_NUMBER", _DEFAULT_PLACEHOLDER),
        uid_root=parameters.get("UIDROOT", _DEFAULT_UID_ROOT),
        series_description=parameters.get("SERIES_DESCRIPTION"),
        study_description=parameters.get("STUDY_DESCRIPTION"),
        protocol_name=parameters.get("PROTOCOL_NAME"),
        patient_name=parameters.get("PATIENT_NAME"),
        allowlist_csv=parameters.get("ALLOWLIST_CSV", _DEFAULT_ALLOWLIST_CSV),
    )


_BUILDERS = {
    "default": _build_default,
    "lds": _build_lds,
    "lds-no-dob": _build_lds_no_dob,
    "pixels-only": _build_pixels_only,
}


def build_profile(name: str, parameters: dict[str, str]) -> DeidProfile:
    """Construct a bound :class:`DeidProfile` for a named profile.

    Args:
        name: Profile name, one of ``"default"``, ``"lds"``, ``"lds-no-dob"``,
            or ``"pixels-only"``.
        parameters: Runtime parameter dict (PATIENT_ID, ACCESSION_NUMBER,
            STUDY_ID, JITTER, UIDROOT, description fields, etc.), consumed
            as-is with no hashing or redaction.

    Returns:
        A fully-bound profile ready for ``apply()``.

    Raises:
        ValueError: If the name is unknown or JITTER is not an integer.
    """
    builder = _BUILDERS.get(name)
    if builder is None:
        raise ValueError(f"Unknown de-identification profile: {name!r}")
    return builder(parameters)


def list_profiles() -> list[str]:
    """Return the names of all buildable profiles."""
    return list(_BUILDERS.keys())
