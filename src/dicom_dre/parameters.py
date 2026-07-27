"""Per-patient de-identification parameters applied at ``apply()`` time.

``DeidParameters`` is the typed, immutable record of the per-patient values a
caller supplies when de-identifying a dataset. A profile is a build-once,
patient-invariant policy object; the identity values that vary per patient travel
on ``DeidParameters`` and are threaded through :meth:`DeidProfile.apply`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Mapping


# Write-time defaults resolved by the parameterized tag actions. Kept here as a
# single source of truth for the placeholder identifiers, the UID-hash salt, and
# the date-shift amount used when the caller supplies no value.
IDENTIFIER_PLACEHOLDER = "######"  # PatientID/AccessionNumber when absent
DEFAULT_STUDY_ID = "UNKNOWN"  # STUDY_ID (UID-hash salt / ClinicalTrialProtocolID) when absent
DEFAULT_JITTER = 10  # date shift in days when jitter is absent


@dataclass(frozen=True, slots=True)
class DeidParameters:
    """Immutable per-patient de-identification parameters.

    Each field records exactly what the caller supplied; ``None`` means "not
    supplied" and the parameterized tag actions resolve placeholder defaults at
    write time. The type is hashable and picklable so it can be shared read-only
    across threads and shipped to worker processes.
    """

    patient_id: str | None = None
    patient_name: str | None = None
    accession_number: str | None = None
    study_id: str | None = None
    series_description: str | None = None
    study_description: str | None = None
    protocol_name: str | None = None
    jitter: int | None = None

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, str]) -> DeidParameters:
        """Build ``DeidParameters`` from an uppercase-keyed parameter mapping.

        Reads the identity keys ``PATIENT_ID``, ``PATIENT_NAME``,
        ``ACCESSION_NUMBER``, ``STUDY_ID``, ``SERIES_DESCRIPTION``,
        ``STUDY_DESCRIPTION``, ``PROTOCOL_NAME``, and ``JITTER``. Any other key
        (for example the build knobs ``UIDROOT``/``ALLOWLIST_CSV``) is ignored.

        Args:
            mapping: Parameter mapping with uppercase keys.

        Returns:
            The parsed parameters.

        Raises:
            ValueError: If ``JITTER`` is present but not an integer.
        """
        jitter_value = mapping.get("JITTER")
        if jitter_value is None:
            jitter: int | None = None
        else:
            try:
                jitter = int(jitter_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"JITTER parameter must be an integer, got {jitter_value!r}") from exc

        return cls(
            patient_id=mapping.get("PATIENT_ID"),
            patient_name=mapping.get("PATIENT_NAME"),
            accession_number=mapping.get("ACCESSION_NUMBER"),
            study_id=mapping.get("STUDY_ID"),
            series_description=mapping.get("SERIES_DESCRIPTION"),
            study_description=mapping.get("STUDY_DESCRIPTION"),
            protocol_name=mapping.get("PROTOCOL_NAME"),
            jitter=jitter,
        )
