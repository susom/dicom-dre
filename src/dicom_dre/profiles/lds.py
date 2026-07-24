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
    patient_id: str,
    accession_number: str,
    study_id: str,
    uid_root: str = UIDROOT,
    series_description: str | None = None,
    study_description: str | None = None,
    protocol_name: str | None = None,
    deid_method: str = "DICOM-PS3.15E-Basic-LDS",
    patient_name: str | None = None,
    allowlist_csv: str = "default.csv",
) -> DeidProfile:
    """Construct an LDS profile. All dates are preserved via VR inspection."""
    base = default_profile(
        patient_id=patient_id,
        accession_number=accession_number,
        study_id=study_id,
        jitter=0,
        uid_root=uid_root,
        series_description=series_description,
        study_description=study_description,
        protocol_name=protocol_name,
        deid_method=deid_method,
        patient_name=patient_name,
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
