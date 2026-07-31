"""Per-patient de-identification parameters applied at ``apply()`` time.

``DeidParameters`` is the typed, immutable record of the per-patient values a
caller supplies when de-identifying a dataset. A profile is a build-once,
patient-invariant policy object; the per-patient identity values are supplied on
``DeidParameters`` and passed to :meth:`DeidProfile.apply`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Mapping


# Write-time defaults resolved by the parameterized tag actions. Kept here as a
# single source of truth for the placeholder identifiers and the default study id.
# When jitter is absent the date-shift is derived per study by stable_jitter.
IDENTIFIER_PLACEHOLDER = "[REDACTED]"  # PatientID/AccessionNumber fail-safe when neither supplied nor hashable
DEFAULT_STUDY_ID = "UNKNOWN"  # STUDY_ID (UID-hash salt / ClinicalTrialProtocolID) when absent

# Per-patient identity keys accepted by ``DeidParameters.from_mapping``. Build-time
# settings (UID root, allowlist CSV, hash salt) are not part of this set; they are
# held on ``ProfileSettings`` instead.
_IDENTITY_KEYS = frozenset(
    {
        "PATIENT_ID",
        "PATIENT_NAME",
        "ACCESSION_NUMBER",
        "STUDY_ID",
        "SERIES_DESCRIPTION",
        "STUDY_DESCRIPTION",
        "PROTOCOL_NAME",
        "JITTER",
    }
)


@dataclass(frozen=True, slots=True)
class DeidParameters:
    """Immutable per-patient de-identification parameters.

    Each field records exactly what the caller supplied; ``None`` means "not
    supplied" and the parameterized tag actions resolve placeholder defaults at
    write time. The type is hashable and picklable so it can be shared read-only
    across threads and serialized to worker processes.
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

        Reads the per-patient identity keys ``PATIENT_ID``, ``PATIENT_NAME``,
        ``ACCESSION_NUMBER``, ``STUDY_ID``, ``SERIES_DESCRIPTION``,
        ``STUDY_DESCRIPTION``, ``PROTOCOL_NAME``, and ``JITTER``. Build-time
        settings (UID root, allowlist CSV, identifier-hash salt) are not accepted
        here; they belong to :class:`dicom_dre.profiles.config.ProfileSettings`.

        Args:
            mapping: Parameter mapping with uppercase keys.

        Returns:
            The parsed parameters.

        Raises:
            ValueError: If ``JITTER`` is present but not an integer, or if the
                mapping contains a key that is not a per-patient identity key.
        """
        unknown = set(mapping) - _IDENTITY_KEYS
        if unknown:
            keys = ", ".join(sorted(unknown))
            raise ValueError(
                f"Unknown de-identification parameter(s): {keys}. "
                f"Valid parameters: {', '.join(sorted(_IDENTITY_KEYS))}."
            )

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
