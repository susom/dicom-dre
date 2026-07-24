"""LDS-No-DOB de-identification profile.

Derives from LDS. All dates kept except PatientBirthDate and
PatientBirthTime, which are removed.
"""

import dataclasses

from pydicom.tag import Tag

from dicom_dre.actions import remove
from dicom_dre.profile import DeidProfile
from dicom_dre.profiles.default import UIDROOT
from dicom_dre.profiles.lds import lds_profile


def lds_no_dob_profile(
    patient_id: str,
    accession_number: str,
    study_id: str,
    uid_root: str = UIDROOT,
    series_description: str | None = None,
    study_description: str | None = None,
    protocol_name: str | None = None,
    patient_name: str | None = None,
    allowlist_csv: str = "default.csv",
) -> DeidProfile:
    """Construct an LDS-No-DOB profile. All dates kept except BirthDate/BirthTime."""
    base = lds_profile(
        patient_id=patient_id,
        accession_number=accession_number,
        study_id=study_id,
        uid_root=uid_root,
        series_description=series_description,
        study_description=study_description,
        protocol_name=protocol_name,
        deid_method="DICOM-PS3.15E-Basic-LDS-No-DOB",
        patient_name=patient_name,
        allowlist_csv=allowlist_csv,
    )
    # Remove PatientBirthDate and PatientBirthTime
    updated_rules = dict(base.rules)
    updated_rules[Tag(0x0010, 0x0030)] = remove()  # PatientBirthDate
    updated_rules[Tag(0x0010, 0x0032)] = remove()  # PatientBirthTime
    return dataclasses.replace(
        base,
        name="LDS-No-DOB",
        rules=updated_rules,
        date_override_tags=frozenset(
            {
                Tag(0x0010, 0x0030),  # PatientBirthDate
                Tag(0x0010, 0x0032),  # PatientBirthTime
            }
        ),
    )
