"""LDS-No-DOB de-identification profile.

Derives from LDS. All dates kept except PatientBirthDate and
PatientBirthTime, which are removed.
"""

import dataclasses

from pydicom.tag import Tag

from dicom_dre.actions import remove
from dicom_dre.profile import DeidProfile
from dicom_dre.profiles.config import ProfileSettings
from dicom_dre.profiles.lds import lds_profile


def lds_no_dob_profile(settings: ProfileSettings | None = None) -> DeidProfile:
    """Construct an LDS-No-DOB profile. All dates kept except BirthDate/BirthTime."""
    base = lds_profile(
        settings,
        deid_method="DICOM-PS3.15E-Basic-LDS-No-DOB",
    )
    # Remove PatientBirthDate and PatientBirthTime
    updated_rules = dict(base.rules)
    updated_rules[Tag(0x0010, 0x0030)] = remove()  # PatientBirthDate
    updated_rules[Tag(0x0010, 0x0032)] = remove()  # PatientBirthTime
    return dataclasses.replace(
        base,
        name="LDS-No-DOB",
        rules=updated_rules,
        deid_options=frozenset({"113105", "113108"}),
        date_override_tags=frozenset(
            {
                Tag(0x0010, 0x0030),  # PatientBirthDate
                Tag(0x0010, 0x0032),  # PatientBirthTime
            }
        ),
    )
