"""LDS (Limited Data Set) de-identification profile.

Derives from default. All dates are preserved via VR inspection
at apply-time. The PatientAge cap is also overridden to keep the value.
"""

import dataclasses

from pydicom.tag import Tag

from dicom_dre.actions import keep
from dicom_dre.profile import DeidProfile
from dicom_dre.profiles.default import UIDROOT
from dicom_dre.profiles.default import default_profile


def lds_profile(
    *,
    uid_root: str = UIDROOT,
    deid_method: str = "DICOM-PS3.15E-Basic-LDS",
    allowlist_csv: str = "default.csv",
) -> DeidProfile:
    """Construct an LDS profile. All dates are preserved via VR inspection."""
    base = default_profile(
        uid_root=uid_root,
        deid_method=deid_method,
        allowlist_csv=allowlist_csv,
        preserve_dates=True,
    )
    # Preserve PatientAge unchanged (LDS does not cap age)
    updated_rules = dict(base.rules)
    updated_rules[Tag(0x0010, 0x1010)] = keep()  # PatientAge
    # LDS preserves temporal info that the default profile removes.
    updated_rules[Tag(0x0008, 0x0201)] = keep()  # TimezoneOffsetFromUTC
    updated_rules[Tag(0x0018, 0x700C)] = keep()  # DateOfLastDetectorCalibration
    return dataclasses.replace(
        base,
        name="LDS",
        rules=updated_rules,
        preserve_dates=True,
        modifies_dates=False,
    )
