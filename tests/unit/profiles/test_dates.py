"""Date-policy behavior for every profile.

Each test takes an ``expectation`` argument that ``conftest.pytest_generate_tests``
parametrizes over every buildable profile, and branches on
``expectation.date_policy`` (``jitter``, ``preserve``, or ``remove``). The
canonical dataset and harness helpers arrive through the ``canonical_dataset`` and
``profile_harness`` fixtures.
"""

from __future__ import annotations


# Seeded date values in the canonical dataset (kept in sync with conftest.SENTINELS).
_STUDY_DATE = "20200102"
_ACQ_DATETIME = "20211115081500"
_BIRTH_DATE = "19850307"
_BIRTH_TIME = "083015"

# Tags exercised by the date tests.
_STUDY_DATE_TAG = (0x0008, 0x0020)  # DA
_ACQ_DATETIME_TAG = (0x0008, 0x002A)  # DT
_BIRTH_DATE_TAG = (0x0010, 0x0030)  # DA
_BIRTH_TIME_TAG = (0x0010, 0x0032)  # TM


def _tag(pair):
    from pydicom.tag import Tag

    return Tag(*pair)


def test_non_birth_date_policy(expectation, canonical_dataset, profile_harness) -> None:
    """StudyDate (DA) and AcquisitionDateTime (DT) follow the profile date policy."""
    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    study_tag = _tag(_STUDY_DATE_TAG)
    acq_tag = _tag(_ACQ_DATETIME_TAG)

    if expectation.date_policy == "jitter":
        assert study_tag in result, f"{expectation.name}: StudyDate should remain present when jittered"
        study_value = str(result[study_tag].value)
        assert study_value != _STUDY_DATE, f"{expectation.name}: StudyDate should change, got {study_value!r}"
        assert len(study_value) == 8 and study_value.isdigit(), (
            f"{expectation.name}: jittered StudyDate should be a valid 8-digit date, got {study_value!r}"
        )
        assert acq_tag in result, f"{expectation.name}: AcquisitionDateTime should remain present when jittered"
        acq_value = str(result[acq_tag].value)
        assert acq_value[:8] != _ACQ_DATETIME[:8], (
            f"{expectation.name}: AcquisitionDateTime date component should change, got {acq_value!r}"
        )
        assert acq_value[8:] == _ACQ_DATETIME[8:], (
            f"{expectation.name}: AcquisitionDateTime time component should be preserved, got {acq_value!r}"
        )
    elif expectation.date_policy == "preserve":
        assert str(result[study_tag].value) == _STUDY_DATE, (
            f"{expectation.name}: StudyDate should be preserved verbatim, got {result[study_tag].value!r}"
        )
        assert str(result[acq_tag].value) == _ACQ_DATETIME, (
            f"{expectation.name}: AcquisitionDateTime should be preserved verbatim, got {result[acq_tag].value!r}"
        )
    elif expectation.date_policy == "remove":
        assert study_tag not in result, f"{expectation.name}: StudyDate should be removed"
        assert acq_tag not in result, f"{expectation.name}: AcquisitionDateTime should be removed"
    else:
        raise AssertionError(f"{expectation.name}: unknown date_policy {expectation.date_policy!r}")


def test_jitter_is_deterministic_per_patient(expectation, canonical_dataset, profile_harness) -> None:
    """A date-shifting profile derives a stable non-zero shift from the patient/study.

    Applied twice with an unset jitter, the profile derives the same shift, so the
    result is identical and differs from the seeded date. Non-shifting profiles are
    not exercised here.
    """
    if expectation.date_policy != "jitter":
        return
    from dicom_dre.parameters import DeidParameters

    study_tag = _tag(_STUDY_DATE_TAG)
    first = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset, params=DeidParameters())
    second = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset, params=DeidParameters())

    first_value = str(first[study_tag].value)
    second_value = str(second[study_tag].value)
    assert first_value == second_value, (
        f"{expectation.name}: derived jitter should be deterministic, got {first_value!r} and {second_value!r}"
    )
    assert first_value != _STUDY_DATE, (
        f"{expectation.name}: derived jitter must shift StudyDate off its seeded value, got {first_value!r}"
    )


def test_birth_date_and_time_handling(expectation, canonical_dataset, profile_harness) -> None:
    """PatientBirthDate/PatientBirthTime follow the profile's birth-date policy.

    Exercises ``date_override_tags``: lds-no-dob removes PatientBirthDate and
    PatientBirthTime while preserving other dates; lds preserves them; the default
    profile jitters the birth date and removes the birth time; strict removes
    both.
    """
    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    birth_date_tag = _tag(_BIRTH_DATE_TAG)
    birth_time_tag = _tag(_BIRTH_TIME_TAG)
    study_tag = _tag(_STUDY_DATE_TAG)

    if expectation.date_policy == "preserve" and expectation.removes_birth_date:
        assert birth_date_tag not in result, f"{expectation.name}: PatientBirthDate should be removed"
        assert birth_time_tag not in result, f"{expectation.name}: PatientBirthTime should be removed"
        assert str(result[study_tag].value) == _STUDY_DATE, (
            f"{expectation.name}: other dates should stay preserved when the birth date is removed"
        )
    elif expectation.date_policy == "preserve":
        assert str(result[birth_date_tag].value) == _BIRTH_DATE, (
            f"{expectation.name}: PatientBirthDate should be preserved, got {result[birth_date_tag].value!r}"
        )
        assert str(result[birth_time_tag].value) == _BIRTH_TIME, (
            f"{expectation.name}: PatientBirthTime should be preserved, got {result[birth_time_tag].value!r}"
        )
    elif expectation.date_policy == "jitter":
        assert birth_date_tag in result, f"{expectation.name}: PatientBirthDate should remain present when jittered"
        assert str(result[birth_date_tag].value) != _BIRTH_DATE, (
            f"{expectation.name}: PatientBirthDate should be jittered, got {result[birth_date_tag].value!r}"
        )
        assert birth_time_tag not in result, (
            f"{expectation.name}: PatientBirthTime should be removed by the default profile"
        )
    elif expectation.date_policy == "remove":
        assert birth_date_tag not in result, f"{expectation.name}: PatientBirthDate should be removed"
        assert birth_time_tag not in result, f"{expectation.name}: PatientBirthTime should be removed"
    else:
        raise AssertionError(f"{expectation.name}: unknown date_policy {expectation.date_policy!r}")
