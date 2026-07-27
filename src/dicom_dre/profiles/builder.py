"""Canonical profile builder.

Given a profile name and an optional build-configuration mapping,
:func:`build_profile` returns a patient-invariant :class:`DeidProfile` policy
object. The configuration carries only build-time knobs (``UIDROOT``,
``ALLOWLIST_CSV``); per-patient identity values are supplied at ``apply()`` time
via :class:`dicom_dre.parameters.DeidParameters`, not to ``build_profile``.

Free-text description elements (``SeriesDescription``, ``StudyDescription``,
``ProtocolName``) follow a precedence-or-redact contract at apply time: a
per-patient value is written verbatim, and when it is absent the element is
redacted using the allowlist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dicom_dre.profiles.default import default_profile
from dicom_dre.profiles.lds import lds_profile
from dicom_dre.profiles.lds_no_dob import lds_no_dob_profile
from dicom_dre.profiles.pixels_only import pixels_only_profile


if TYPE_CHECKING:
    from collections.abc import Mapping

    from dicom_dre.profile import DeidProfile


_DEFAULT_UID_ROOT = "1.2.840.4267.32."
_DEFAULT_ALLOWLIST_CSV = "default.csv"  # free-text redaction allowlist when absent

# Parsed ``--param`` keys that configure profile construction rather than a
# patient's identity. The CLI filters with this so identity values never enter
# a ``ProfileSpec`` shipped to worker processes.
BUILD_CONFIG_KEYS = frozenset({"UIDROOT", "ALLOWLIST_CSV"})


_BUILDERS = {
    "default": default_profile,
    "lds": lds_profile,
    "lds-no-dob": lds_no_dob_profile,
    "pixels-only": pixels_only_profile,
}


def build_profile(name: str, config: Mapping[str, str] | None = None) -> DeidProfile:
    """Construct a patient-invariant :class:`DeidProfile` for a named profile.

    Args:
        name: Profile name, one of ``"default"``, ``"lds"``, ``"lds-no-dob"``,
            or ``"pixels-only"``.
        config: Optional build-time configuration mapping. Only ``UIDROOT`` and
            ``ALLOWLIST_CSV`` are read; other keys are ignored.

    Returns:
        A profile ready for ``apply(ds, params)``.

    Raises:
        ValueError: If the name is unknown.
    """
    factory = _BUILDERS.get(name)
    if factory is None:
        raise ValueError(f"Unknown de-identification profile: {name!r}")
    config = config or {}
    return factory(
        uid_root=config.get("UIDROOT", _DEFAULT_UID_ROOT),
        allowlist_csv=config.get("ALLOWLIST_CSV", _DEFAULT_ALLOWLIST_CSV),
    )


def list_profiles() -> list[str]:
    """Return the names of all buildable profiles."""
    return list(_BUILDERS.keys())
