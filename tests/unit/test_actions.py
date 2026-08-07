"""Tests for the tag-action factories in dicom_dre.actions.

Each factory returns a callable ``(Dataset, BaseTag, DeidParameters) -> None``.
These tests exercise the action behaviors directly on small in-memory datasets:
value replacement, creation-if-missing, VR-aware dummying, per-patient hashing,
date jitter (including non-standard date formats), age capping, and appending.

Pydicom is imported inside the helpers and tests rather than at module level to
avoid triggering a GDCM segfault during pytest collection on ARM64. See the root
conftest.py pytest_configure hook for details.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dicom_dre.parameters import DEFAULT_STUDY_ID
from dicom_dre.parameters import IDENTIFIER_PLACEHOLDER
from dicom_dre.parameters import DeidParameters


if TYPE_CHECKING:
    from pydicom.dataset import Dataset
    from pydicom.tag import BaseTag


def _tag(group: int, element: int) -> BaseTag:
    """Return a pydicom BaseTag for the given group and element."""
    from pydicom.tag import Tag

    return Tag(group, element)


def _dataset() -> Dataset:
    """Return an empty in-memory dataset."""
    from pydicom.dataset import Dataset

    return Dataset()


class TestKeepRemoveEmpty:
    """The keep, remove, and empty action factories."""

    def test_keep_leaves_value_unchanged(self) -> None:
        """keep() does not modify the element value."""
        from dicom_dre.actions import keep

        ds = _dataset()
        tag = _tag(0x0010, 0x0010)
        ds.add_new(tag, "PN", "DOE^JANE")
        keep()(ds, tag, DeidParameters())
        assert ds[tag].value == "DOE^JANE", "keep should leave the value unchanged"

    def test_remove_deletes_present_element(self) -> None:
        """remove() deletes an element that is present."""
        from dicom_dre.actions import remove

        ds = _dataset()
        tag = _tag(0x0010, 0x0010)
        ds.add_new(tag, "PN", "DOE^JANE")
        remove()(ds, tag, DeidParameters())
        assert tag not in ds, "remove should delete the element"

    def test_remove_absent_element_is_noop(self) -> None:
        """remove() on an absent element does nothing."""
        from dicom_dre.actions import remove

        ds = _dataset()
        tag = _tag(0x0010, 0x0010)
        remove()(ds, tag, DeidParameters())
        assert tag not in ds, "remove on an absent element should remain absent"

    def test_empty_scalar_sets_blank_string(self) -> None:
        """empty() replaces a scalar value with an empty string."""
        from dicom_dre.actions import empty

        ds = _dataset()
        tag = _tag(0x0010, 0x0010)
        ds.add_new(tag, "PN", "DOE^JANE")
        empty()(ds, tag, DeidParameters())
        assert ds[tag].value == "", "empty should blank a scalar value"

    def test_empty_sequence_sets_empty_list(self) -> None:
        """empty() replaces a sequence value with an empty list."""
        from dicom_dre.actions import empty

        ds = _dataset()
        item = _dataset()
        item.add_new(_tag(0x0008, 0x0100), "SH", "CODE")
        tag = _tag(0x0008, 0x1032)
        ds.add_new(tag, "SQ", [item])
        empty()(ds, tag, DeidParameters())
        assert list(ds[tag].value) == [], "empty should clear a sequence to an empty list"


class TestSetValue:
    """The set_value action factory."""

    def test_overwrites_present_value(self) -> None:
        """set_value overwrites the value of a present element."""
        from dicom_dre.actions import set_value

        ds = _dataset()
        tag = _tag(0x0010, 0x0010)
        ds.add_new(tag, "PN", "DOE^JANE")
        set_value("ANON")(ds, tag, DeidParameters())
        assert ds[tag].value == "ANON", "set_value should overwrite a present value"

    def test_absent_without_create_is_noop(self) -> None:
        """set_value leaves an absent element absent when create_if_missing is False."""
        from dicom_dre.actions import set_value

        ds = _dataset()
        tag = _tag(0x0010, 0x0010)
        set_value("ANON")(ds, tag, DeidParameters())
        assert tag not in ds, "set_value should not create the element by default"

    def test_absent_with_create_adds_element(self) -> None:
        """set_value creates an absent element when create_if_missing is True."""
        from dicom_dre.actions import set_value

        ds = _dataset()
        tag = _tag(0x0012, 0x0062)  # PatientIdentityRemoved (CS)
        set_value("YES", create_if_missing=True)(ds, tag, DeidParameters())
        assert ds[tag].value == "YES", "set_value should create and set the element"


class TestSetParam:
    """The set_param action factory."""

    def test_writes_param_value(self) -> None:
        """set_param writes the value read from the named parameter field."""
        from dicom_dre.actions import set_param

        ds = _dataset()
        tag = _tag(0x0008, 0x1030)
        ds.add_new(tag, "LO", "ORIGINAL")
        params = DeidParameters(study_description="REPLACED")
        set_param("study_description")(ds, tag, params)
        assert ds[tag].value == "REPLACED", "set_param should write the parameter value"

    def test_falls_back_to_fallback_field(self) -> None:
        """set_param uses the fallback field when the primary field is None."""
        from dicom_dre.actions import set_param

        ds = _dataset()
        tag = _tag(0x0018, 0x1030)
        ds.add_new(tag, "LO", "ORIGINAL")
        params = DeidParameters(study_description="FROM_FALLBACK")
        set_param("protocol_name", fallback_field="study_description")(ds, tag, params)
        assert ds[tag].value == "FROM_FALLBACK", "set_param should use the fallback field value"

    def test_uses_default_when_all_none(self) -> None:
        """set_param writes the default when field and fallback resolve to None."""
        from dicom_dre.actions import set_param

        ds = _dataset()
        tag = _tag(0x0008, 0x1030)
        ds.add_new(tag, "LO", "ORIGINAL")
        set_param("study_description", default="DEFAULTED")(ds, tag, DeidParameters())
        assert ds[tag].value == "DEFAULTED", "set_param should write the default value"

    def test_none_value_is_noop(self) -> None:
        """set_param leaves the element unchanged when nothing resolves."""
        from dicom_dre.actions import set_param

        ds = _dataset()
        tag = _tag(0x0008, 0x1030)
        ds.add_new(tag, "LO", "ORIGINAL")
        set_param("study_description")(ds, tag, DeidParameters())
        assert ds[tag].value == "ORIGINAL", "set_param should not change the value when nothing resolves"

    def test_absent_with_create(self) -> None:
        """set_param creates an absent element when create_if_missing is True."""
        from dicom_dre.actions import set_param

        ds = _dataset()
        tag = _tag(0x0008, 0x1030)
        params = DeidParameters(study_description="NEW")
        set_param("study_description", create_if_missing=True)(ds, tag, params)
        assert ds[tag].value == "NEW", "set_param should create and set the element"

    def test_absent_without_create_is_noop(self) -> None:
        """set_param leaves an absent element absent when create_if_missing is False."""
        from dicom_dre.actions import set_param

        ds = _dataset()
        tag = _tag(0x0008, 0x1030)
        params = DeidParameters(study_description="NEW")
        set_param("study_description")(ds, tag, params)
        assert tag not in ds, "set_param should not create the element by default"


class TestHashValueIdentifier:
    """The hash_value_identifier action factory."""

    def test_hashes_present_value(self) -> None:
        """A present, non-empty value is replaced by a deterministic hash."""
        from dicom_dre.actions import hash_value_identifier
        from dicom_dre.uid_utils import hash_identifier

        ds = _dataset()
        tag = _tag(0x0062, 0x0020)  # TrackingID
        ds.add_new(tag, "UT", "TRACK-1")
        params = DeidParameters(study_id="STUDY-A")
        hash_value_identifier(salt="s")(ds, tag, params)
        expected = hash_identifier("TRACK-1", salt="s", study_id="STUDY-A")
        assert ds[tag].value == expected, "hash_value_identifier should replace with the study-scoped hash"

    def test_empty_value_is_unchanged(self) -> None:
        """An empty value is left as-is (the hash guard skips it)."""
        from dicom_dre.actions import hash_value_identifier

        ds = _dataset()
        tag = _tag(0x0062, 0x0020)
        ds.add_new(tag, "UT", "")
        hash_value_identifier(salt="s")(ds, tag, DeidParameters())
        assert ds[tag].value == "", "hash_value_identifier should leave an empty value unchanged"

    def test_absent_tag_is_noop(self) -> None:
        """An absent element is left absent."""
        from dicom_dre.actions import hash_value_identifier

        ds = _dataset()
        tag = _tag(0x0062, 0x0020)
        hash_value_identifier(salt="s")(ds, tag, DeidParameters())
        assert tag not in ds, "hash_value_identifier should not create the element"

    def test_uses_default_study_id_when_absent(self) -> None:
        """With no study_id the default study id scopes the hash."""
        from dicom_dre.actions import hash_value_identifier
        from dicom_dre.uid_utils import hash_identifier

        ds = _dataset()
        tag = _tag(0x0062, 0x0020)
        ds.add_new(tag, "UT", "TRACK-1")
        hash_value_identifier(salt="s")(ds, tag, DeidParameters())
        expected = hash_identifier("TRACK-1", salt="s", study_id=DEFAULT_STUDY_ID)
        assert ds[tag].value == expected, "hash_value_identifier should use DEFAULT_STUDY_ID when absent"


class TestHashIdentifierParam:
    """The hash_identifier_param action factory."""

    def test_param_value_wins(self) -> None:
        """A supplied parameter value is written verbatim."""
        from dicom_dre.actions import hash_identifier_param

        ds = _dataset()
        tag = _tag(0x0010, 0x0020)
        ds.add_new(tag, "LO", "MRN123")
        params = DeidParameters(patient_id="EXPLICIT")
        hash_identifier_param("patient_id", salt="s")(ds, tag, params)
        assert ds[tag].value == "EXPLICIT", "A supplied parameter value should win"

    def test_hashes_source_when_param_absent(self) -> None:
        """The source element value is hashed when no parameter is supplied."""
        from dicom_dre.actions import hash_identifier_param
        from dicom_dre.uid_utils import hash_identifier

        ds = _dataset()
        tag = _tag(0x0010, 0x0020)
        ds.add_new(tag, "LO", "MRN123")
        params = DeidParameters(study_id="STUDY-A")
        hash_identifier_param("patient_id", salt="s")(ds, tag, params)
        expected = hash_identifier("MRN123", salt="s", study_id="STUDY-A")
        assert ds[tag].value == expected, "The source value should be hashed when no parameter is supplied"

    def test_placeholder_when_nothing_to_hash(self) -> None:
        """The placeholder is written when neither a parameter nor a source value exists."""
        from dicom_dre.actions import hash_identifier_param

        ds = _dataset()
        tag = _tag(0x0010, 0x0020)
        ds.add_new(tag, "LO", "")
        hash_identifier_param("patient_id", salt="s")(ds, tag, DeidParameters())
        assert ds[tag].value == IDENTIFIER_PLACEHOLDER, "The placeholder should be written when nothing is hashable"

    def test_source_tag_derives_from_other_element(self) -> None:
        """source_tag reads the hash source from a different element."""
        from dicom_dre.actions import hash_identifier_param
        from dicom_dre.uid_utils import hash_identifier

        ds = _dataset()
        name_tag = _tag(0x0010, 0x0010)
        id_tag = _tag(0x0010, 0x0020)
        ds.add_new(name_tag, "PN", "DOE^JANE")
        ds.add_new(id_tag, "LO", "MRN123")
        params = DeidParameters(study_id="STUDY-A")
        hash_identifier_param("patient_name", salt="s", source_tag=id_tag)(ds, name_tag, params)
        expected = hash_identifier("MRN123", salt="s", study_id="STUDY-A")
        assert ds[name_tag].value == expected, "PatientName should derive from the PatientID source element"

    def test_absent_with_create(self) -> None:
        """hash_identifier_param creates an absent element when create_if_missing is True."""
        from dicom_dre.actions import hash_identifier_param

        ds = _dataset()
        tag = _tag(0x0010, 0x0020)
        params = DeidParameters(patient_id="EXPLICIT")
        hash_identifier_param("patient_id", salt="s", create_if_missing=True)(ds, tag, params)
        assert ds[tag].value == "EXPLICIT", "hash_identifier_param should create and set the element"


class TestHashUid:
    """The hash_uid action factory."""

    def test_hashes_uid_without_study_salt(self) -> None:
        """Without a study salt the raw UID is hashed with the root."""
        from dicom_dre.actions import hash_uid
        from dicom_dre.uid_utils import hashuid

        ds = _dataset()
        tag = _tag(0x0008, 0x0018)
        ds.add_new(tag, "UI", "1.2.3")
        hash_uid("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == hashuid("1.2.840.99", "1.2.3"), "hash_uid should hash the raw UID"

    def test_hashes_uid_with_study_salt(self) -> None:
        """With a study salt the study id is concatenated before hashing."""
        from dicom_dre.actions import hash_uid
        from dicom_dre.uid_utils import hashuid

        ds = _dataset()
        tag = _tag(0x0008, 0x0018)
        ds.add_new(tag, "UI", "1.2.3")
        params = DeidParameters(study_id="STUDY-A")
        hash_uid("1.2.840.99", use_study_salt=True)(ds, tag, params)
        assert ds[tag].value == hashuid("1.2.840.99", "1.2.3STUDY-A"), "hash_uid should salt with the study id"

    def test_absent_or_empty_is_noop(self) -> None:
        """An absent or empty UID is left unchanged."""
        from dicom_dre.actions import hash_uid

        ds = _dataset()
        tag = _tag(0x0008, 0x0018)
        ds.add_new(tag, "UI", "")
        hash_uid("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == "", "hash_uid should leave an empty UID unchanged"


class TestDummyForVr:
    """The dummy_for_vr action factory across VR classes."""

    def test_text_vr_gets_token(self) -> None:
        """A text VR receives the ANONYMIZED token."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0008, 0x0080)  # InstitutionName (LO)
        ds.add_new(tag, "LO", "SOME HOSPITAL")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == "ANONYMIZED", "A text VR should get the ANONYMIZED token"

    def test_age_string_gets_zero_age(self) -> None:
        """An AS element becomes 000Y."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0010, 0x1010)  # PatientAge (AS)
        ds.add_new(tag, "AS", "045Y")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == "000Y", "An AS element should become 000Y"

    def test_string_number_vr_gets_zero_string(self) -> None:
        """DS and IS elements become the string '0'."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0028, 0x1053)  # RescaleSlope (DS)
        ds.add_new(tag, "DS", "1.5")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == "0", "A DS element should become '0'"

    def test_binary_float_vr_gets_zero(self) -> None:
        """FL and FD elements become 0.0."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0018, 0x9087)
        ds.add_new(tag, "FD", 1.5)
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == 0.0, "An FD element should become 0.0"

    def test_binary_int_vr_gets_zero(self) -> None:
        """Signed and unsigned binary integer VRs become 0."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0028, 0x0010)  # Rows (US)
        ds.add_new(tag, "US", 512)
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == 0, "A US element should become 0"

    def test_uid_vr_is_hashed(self) -> None:
        """A UI element is hashed with the uid root."""
        from dicom_dre.actions import dummy_for_vr
        from dicom_dre.uid_utils import hashuid

        ds = _dataset()
        tag = _tag(0x0008, 0x0018)
        ds.add_new(tag, "UI", "1.2.3")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == hashuid("1.2.840.99", "1.2.3"), "A UI element should be hashed with the root"

    def test_uid_vr_hashed_with_study_salt(self) -> None:
        """A UI element is salted with the study id when requested."""
        from dicom_dre.actions import dummy_for_vr
        from dicom_dre.uid_utils import hashuid

        ds = _dataset()
        tag = _tag(0x0008, 0x0018)
        ds.add_new(tag, "UI", "1.2.3")
        params = DeidParameters(study_id="STUDY-A")
        dummy_for_vr("1.2.840.99", use_study_salt=True)(ds, tag, params)
        assert ds[tag].value == hashuid("1.2.840.99", "1.2.3STUDY-A"), "A UI element should be salted with the study id"

    def test_sequence_vr_becomes_empty(self) -> None:
        """An SQ element becomes an empty sequence."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        item = _dataset()
        item.add_new(_tag(0x0008, 0x0100), "SH", "CODE")
        tag = _tag(0x0008, 0x1032)
        ds.add_new(tag, "SQ", [item])
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert list(ds[tag].value) == [], "An SQ element should become an empty sequence"

    def test_implicit_un_corrected_to_dictionary_vr(self) -> None:
        """A UN element for a known tag is corrected to its dictionary VR."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0010, 0x0010)  # PatientName, dictionary VR PN
        ds.add_new(tag, "UN", b"DOE^JANE")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].VR == "PN", "A UN element should be corrected to the dictionary VR"
        assert ds[tag].value == "ANONYMIZED", "The corrected element should get the text token"

    def test_unknown_un_tag_written_as_bytes(self) -> None:
        """A UN element with no dictionary VR receives the token as bytes."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0009, 0x1001)  # private, no dictionary VR
        ds.add_new(tag, "UN", b"secret")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == b"ANONYMIZED", "An unknown UN element should get the bytes token"

    def test_unknown_ob_tag_becomes_empty_bytes(self) -> None:
        """An OB element with no dictionary VR becomes empty bytes."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0009, 0x1002)  # private, no dictionary VR
        ds.add_new(tag, "OB", b"payload")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == b"", "An unknown OB element should become empty bytes"

    def test_absent_tag_is_noop(self) -> None:
        """dummy_for_vr on an absent element does nothing."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0008, 0x0080)
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert tag not in ds, "dummy_for_vr should not create an absent element"

    def test_date_vr_gets_sentinel(self) -> None:
        """A DA element becomes the sentinel 19000101."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0008, 0x0020)  # StudyDate (DA)
        ds.add_new(tag, "DA", "20200101")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == "19000101", "A DA element should become the sentinel date"

    def test_time_vr_gets_sentinel(self) -> None:
        """A TM element becomes the sentinel 000000."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0008, 0x0030)  # StudyTime (TM)
        ds.add_new(tag, "TM", "131415")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == "000000", "A TM element should become the sentinel time"

    def test_datetime_vr_gets_sentinel(self) -> None:
        """A DT element becomes the sentinel 19000101000000."""
        from dicom_dre.actions import dummy_for_vr

        ds = _dataset()
        tag = _tag(0x0072, 0x0063)  # SelectorDTValue (DT)
        ds.add_new(tag, "DT", "20200101131415")
        dummy_for_vr("1.2.840.99")(ds, tag, DeidParameters())
        assert ds[tag].value == "19000101000000", "A DT element should become the sentinel datetime"


class TestJitterDate:
    """The jitter_date action factory."""

    def test_shifts_da_value(self) -> None:
        """A DA value is shifted by the jitter amount."""
        from dicom_dre.actions import jitter_date

        ds = _dataset()
        tag = _tag(0x0008, 0x0020)  # StudyDate
        ds.add_new(tag, "DA", "20200101")
        jitter_date()(ds, tag, DeidParameters(jitter=5))
        assert ds[tag].value == "20200106", f"Expected 20200106, got {ds[tag].value}"

    def test_preserves_dt_time_and_offset(self) -> None:
        """A DT value shifts only the date component, keeping time and offset."""
        from dicom_dre.actions import jitter_date

        ds = _dataset()
        tag = _tag(0x0008, 0x002A)  # AcquisitionDateTime (DT)
        ds.add_new(tag, "DT", "20200101120000.000000+0500")
        jitter_date()(ds, tag, DeidParameters(jitter=1))
        assert ds[tag].value == "20200102120000.000000+0500", f"Time/offset not preserved: {ds[tag].value}"

    def test_none_jitter_is_noop(self) -> None:
        """A None jitter leaves the date unchanged."""
        from dicom_dre.actions import jitter_date

        ds = _dataset()
        tag = _tag(0x0008, 0x0020)
        ds.add_new(tag, "DA", "20200101")
        jitter_date()(ds, tag, DeidParameters())
        assert ds[tag].value == "20200101", "A None jitter should leave the date unchanged"

    def test_short_value_is_noop(self) -> None:
        """A value shorter than six characters is left unchanged."""
        from dicom_dre.actions import jitter_date

        ds = _dataset()
        tag = _tag(0x0008, 0x0020)
        ds.add_new(tag, "DA", "2020")
        jitter_date()(ds, tag, DeidParameters(jitter=5))
        assert ds[tag].value == "2020", "A short value should be left unchanged"

    def test_unparseable_value_is_noop(self) -> None:
        """A value that matches no known date format is left unchanged."""
        from dicom_dre.actions import jitter_date

        ds = _dataset()
        tag = _tag(0x0008, 0x0020)
        ds.add_new(tag, "DA", "notadate")
        jitter_date()(ds, tag, DeidParameters(jitter=5))
        assert ds[tag].value == "notadate", "An unparseable value should be left unchanged"

    def test_invalid_eight_digit_date_is_noop(self) -> None:
        """An 8-digit numeric value that is not a valid calendar date is left unchanged."""
        from dicom_dre.actions import jitter_date

        ds = _dataset()
        tag = _tag(0x0008, 0x0020)
        ds.add_new(tag, "DA", "20201345")  # month 13, day 45
        jitter_date()(ds, tag, DeidParameters(jitter=5))
        assert ds[tag].value == "20201345", "An invalid 8-digit date should be left unchanged"

    def test_absent_tag_is_noop(self) -> None:
        """jitter_date on an absent element does nothing."""
        from dicom_dre.actions import jitter_date

        ds = _dataset()
        tag = _tag(0x0008, 0x0020)
        jitter_date()(ds, tag, DeidParameters(jitter=5))
        assert tag not in ds, "jitter_date should not create an absent element"

    def test_normalizes_alternate_slash_format(self) -> None:
        """A non-standard MM/DD/YYYY value is normalized to YYYYMMDD before shifting."""
        from dicom_dre.actions import jitter_date

        ds = _dataset()
        tag = _tag(0x0008, 0x0020)
        ds.add_new(tag, "DA", "10/14/2020")
        jitter_date()(ds, tag, DeidParameters(jitter=1))
        assert ds[tag].value == "20201015", f"Alternate format not normalized: {ds[tag].value}"

    def test_normalizes_alternate_dotted_format(self) -> None:
        """A non-standard DD.MM.YYYY value is normalized before shifting."""
        from dicom_dre.actions import jitter_date

        ds = _dataset()
        tag = _tag(0x0008, 0x0020)
        ds.add_new(tag, "DA", "14.10.2020")
        jitter_date()(ds, tag, DeidParameters(jitter=1))
        assert ds[tag].value == "20201015", f"Dotted alternate format not normalized: {ds[tag].value}"


class TestAppendValue:
    """The append_value action factory."""

    def test_appends_to_present_value(self) -> None:
        """append_value joins the new text with a backslash separator."""
        from dicom_dre.actions import append_value

        ds = _dataset()
        tag = _tag(0x0012, 0x0063)  # DeIdentificationMethod (LO)
        ds.add_new(tag, "LO", "PROFILE")
        append_value("EXTRA")(ds, tag, DeidParameters())
        # VR=LO is multi-valued; pydicom parses the backslash-joined value into a list.
        assert list(ds[tag].value) == ["PROFILE", "EXTRA"], f"Expected backslash join, got {ds[tag].value}"

    def test_sets_value_on_present_empty_element(self) -> None:
        """append_value writes the text when the present element is empty."""
        from dicom_dre.actions import append_value

        ds = _dataset()
        tag = _tag(0x0012, 0x0063)
        ds.add_new(tag, "LO", "")
        append_value("EXTRA")(ds, tag, DeidParameters())
        assert ds[tag].value == "EXTRA", "append_value should set the value on an empty element"

    def test_absent_with_create(self) -> None:
        """append_value creates an absent element when create_if_missing is True."""
        from dicom_dre.actions import append_value

        ds = _dataset()
        tag = _tag(0x0012, 0x0063)
        append_value("EXTRA", create_if_missing=True)(ds, tag, DeidParameters())
        assert ds[tag].value == "EXTRA", "append_value should create and set the element"

    def test_absent_without_create_is_noop(self) -> None:
        """append_value leaves an absent element absent by default."""
        from dicom_dre.actions import append_value

        ds = _dataset()
        tag = _tag(0x0012, 0x0063)
        append_value("EXTRA")(ds, tag, DeidParameters())
        assert tag not in ds, "append_value should not create the element by default"


class TestCapAge:
    """The cap_age action factory."""

    def test_replaces_age_over_threshold(self) -> None:
        """An age above the threshold is replaced."""
        from dicom_dre.actions import cap_age

        ds = _dataset()
        tag = _tag(0x0010, 0x1010)
        ds.add_new(tag, "AS", "095Y")
        cap_age(89, "090Y")(ds, tag, DeidParameters())
        assert ds[tag].value == "090Y", "An age over the threshold should be replaced"

    def test_leaves_age_at_threshold(self) -> None:
        """An age equal to the threshold is not replaced (strict greater-than)."""
        from dicom_dre.actions import cap_age

        ds = _dataset()
        tag = _tag(0x0010, 0x1010)
        ds.add_new(tag, "AS", "089Y")
        cap_age(89, "090Y")(ds, tag, DeidParameters())
        assert ds[tag].value == "089Y", "An age at the threshold should be left unchanged"

    def test_non_numeric_age_is_unchanged(self) -> None:
        """An age value with no digits is left unchanged."""
        from dicom_dre.actions import cap_age

        ds = _dataset()
        tag = _tag(0x0010, 0x1010)
        ds.add_new(tag, "AS", "abc")
        cap_age(89, "090Y")(ds, tag, DeidParameters())
        assert ds[tag].value == "abc", "A non-numeric age should be left unchanged"


class TestIfExists:
    """The if_exists action wrapper."""

    def test_applies_inner_when_present(self) -> None:
        """if_exists runs the inner action when the element is present."""
        from dicom_dre.actions import if_exists
        from dicom_dre.actions import set_value

        ds = _dataset()
        tag = _tag(0x0008, 0x1030)
        ds.add_new(tag, "LO", "ORIGINAL")
        if_exists(set_value("REPLACED"))(ds, tag, DeidParameters())
        assert ds[tag].value == "REPLACED", "if_exists should run the inner action when present"

    def test_skips_inner_when_absent(self) -> None:
        """if_exists does not run the inner action when the element is absent."""
        from dicom_dre.actions import if_exists
        from dicom_dre.actions import set_value

        ds = _dataset()
        tag = _tag(0x0008, 0x1030)
        if_exists(set_value("REPLACED", create_if_missing=True))(ds, tag, DeidParameters())
        assert tag not in ds, "if_exists should skip the inner action when absent"


class TestCreateElementFallback:
    """The private _create_element VR fallback used by create_if_missing paths."""

    def test_unknown_tag_falls_back_to_lo(self) -> None:
        """Creating an element for an unknown tag falls back to VR 'LO'."""
        from dicom_dre.actions import set_value

        ds = _dataset()
        tag = _tag(0x0009, 0x1003)  # private, no dictionary VR
        set_value("VALUE", create_if_missing=True)(ds, tag, DeidParameters())
        assert ds[tag].value == "VALUE", "An unknown tag should be created with the LO fallback"
        assert ds[tag].VR == "LO", f"Expected LO fallback VR, got {ds[tag].VR}"
