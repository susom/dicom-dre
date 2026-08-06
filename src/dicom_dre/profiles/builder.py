"""Canonical profile builder.

Given a profile name and an optional :class:`ProfileSettings`, :func:`build_profile`
returns a patient-invariant :class:`DeidProfile` policy object. The build
configuration carries only build-time settings (UID root, allowlist CSV, and
identifier-hash salt); per-patient identity values are supplied at ``apply()``
time via :class:`dicom_dre.parameters.DeidParameters`.

Free-text description elements (``SeriesDescription``, ``StudyDescription``,
``ProtocolName``) follow a precedence-or-redact contract at apply time: a
per-patient value is written verbatim, and when it is absent the element is
redacted using the allowlist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dicom_dre.profiles.config import ProfileSettings
from dicom_dre.profiles.default import default_profile
from dicom_dre.profiles.lds import lds_profile
from dicom_dre.profiles.lds_no_dob import lds_no_dob_profile
from dicom_dre.profiles.strict import strict_profile


if TYPE_CHECKING:
    from dicom_dre.profile import DeidProfile


_BUILDERS = {
    "default": default_profile,
    "lds": lds_profile,
    "lds-no-dob": lds_no_dob_profile,
    "strict": strict_profile,
}


def build_profile(name: str, settings: ProfileSettings | None = None) -> DeidProfile:
    """Construct a patient-invariant :class:`DeidProfile` for a named profile.

    Args:
        name: Profile name, one of ``"default"``, ``"lds"``, ``"lds-no-dob"``,
            or ``"strict"``.
        settings: Optional build-time configuration. When omitted, the
            :class:`ProfileSettings` defaults apply.

    Returns:
        A profile ready for ``apply(ds, params)``.

    Raises:
        ValueError: If the name is unknown.
    """
    factory = _BUILDERS.get(name)
    if factory is None:
        raise ValueError(f"Unknown de-identification profile: {name!r}")
    return factory(settings or ProfileSettings())


def list_profiles() -> list[str]:
    """Return the names of all buildable profiles."""
    return list(_BUILDERS.keys())
