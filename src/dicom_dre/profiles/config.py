"""Typed build-time configuration for profile construction.

``ProfileSettings`` is the build-time counterpart to
:class:`dicom_dre.parameters.DeidParameters`. It holds the configuration fixed at
profile construction time, while ``DeidParameters`` holds the
per-patient identity values applied at ``apply()`` time.
"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_UID_ROOT = "1.2.840.4267.32."  # UID root prefix when absent
DEFAULT_ALLOWLIST_CSV = "default.csv"  # free-text redaction allowlist when absent
DEFAULT_HASH_SALT = ""  # identifier-hash salt when absent


@dataclass(frozen=True, slots=True)
class ProfileSettings:
    """Typed build-time configuration for profile construction.

    The type is frozen and picklable so it can be serialized and sent to worker
    processes via a :class:`~dicom_dre.batch.ProfileSpec`.

    Attributes:
        uid_root: UID root prefix under which re-derived UIDs are hashed.
        allowlist_csv: Free-text redaction allowlist filename or absolute path.
        hash_salt: Salt applied when hashing PatientID, PatientName, and
            AccessionNumber.
    """

    uid_root: str = DEFAULT_UID_ROOT
    allowlist_csv: str = DEFAULT_ALLOWLIST_CSV
    hash_salt: str = DEFAULT_HASH_SALT
