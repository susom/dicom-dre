"""Profile-specific behaviors that distinguish the profiles.

Covers the LDS keep-overrides (retained where the default profile caps or
removes), the default profile's age cap and timezone removal, and the
strict retention of KO content-root subtrees with de-identification of the
PHI inside them. These use focused, purpose-built datasets applied through the
``profile_harness`` fixture.
"""

from __future__ import annotations


# LDS keep-override tags and their seeded values.
_PATIENT_AGE_TAG = (0x0010, 0x1010)  # AS
_TIMEZONE_TAG = (0x0008, 0x0201)  # SH
_DETECTOR_CAL_DATE_TAG = (0x0018, 0x700C)  # DA, DateOfLastDetectorCalibration


def _tag(pair):
    from pydicom.tag import Tag

    return Tag(*pair)


def _keep_override_dataset():
    """Build a dataset holding the three LDS keep-override elements."""
    from pydicom.dataset import Dataset
    from pydicom.tag import Tag

    ds = Dataset()
    ds.add_new(Tag(*_PATIENT_AGE_TAG), "AS", "045Y")
    ds.add_new(Tag(*_TIMEZONE_TAG), "SH", "-0730")
    ds.add_new(Tag(*_DETECTOR_CAL_DATE_TAG), "DA", "20230515")
    return ds


class TestLdsKeepOverrides:
    """LDS retains PatientAge, TimezoneOffsetFromUTC, and DateOfLastDetectorCalibration."""

    def test_lds_preserves_keep_overrides(self, profile_harness):
        """LDS keeps all three keep-override elements verbatim."""
        result = profile_harness.apply_profile("lds", dataset=_keep_override_dataset())
        age_tag = _tag(_PATIENT_AGE_TAG)
        tz_tag = _tag(_TIMEZONE_TAG)
        cal_tag = _tag(_DETECTOR_CAL_DATE_TAG)
        assert str(result[age_tag].value) == "045Y", f"LDS should keep PatientAge, got {result[age_tag].value!r}"
        assert str(result[tz_tag].value) == "-0730", (
            f"LDS should keep TimezoneOffsetFromUTC, got {result[tz_tag].value!r}"
        )
        assert str(result[cal_tag].value) == "20230515", (
            f"LDS should keep DateOfLastDetectorCalibration, got {result[cal_tag].value!r}"
        )

    def test_default_caps_age(self, profile_harness):
        """The default profile caps a PatientAge above the 89-year threshold."""
        from pydicom.dataset import Dataset
        from pydicom.tag import Tag

        ds = Dataset()
        ds.add_new(Tag(*_PATIENT_AGE_TAG), "AS", "095Y")
        result = profile_harness.apply_profile("default", dataset=ds)
        age_tag = _tag(_PATIENT_AGE_TAG)
        assert str(result[age_tag].value) == "090Y", (
            f"default should cap age over 89 to 090Y, got {result[age_tag].value!r}"
        )

    def test_default_removes_timezone_and_detector_calibration(self, profile_harness):
        """The default profile removes TimezoneOffsetFromUTC and DateOfLastDetectorCalibration."""
        result = profile_harness.apply_profile("default", dataset=_keep_override_dataset())
        assert _tag(_TIMEZONE_TAG) not in result, "default should remove TimezoneOffsetFromUTC"
        assert _tag(_DETECTOR_CAL_DATE_TAG) not in result, "default should remove DateOfLastDetectorCalibration"


class TestPixelsOnlyContentRetention:
    """strict retains KO content-root subtrees while de-identifying PHI inside them."""

    _TITLE_CODE = "113000"
    _TITLE_MEANING = "Of Interest"

    def _ko_dataset(self):
        from pydicom.dataset import Dataset
        from pydicom.sequence import Sequence
        from pydicom.tag import Tag

        ds = Dataset()
        ds.add_new(Tag(0x0008, 0x0060), "CS", "KO")  # Modality
        ds.add_new(Tag(0x0008, 0x0016), "UI", "1.2.840.10008.5.1.4.1.1.88.59")  # SOPClassUID
        ds.add_new(Tag(0x0008, 0x0018), "UI", "1.2.826.0.1.3680043.KO.1")  # SOPInstanceUID
        ds.add_new(Tag(0x0010, 0x0010), "PN", "DOE^JANE")  # PatientName
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN-KO-1")  # PatientID

        title = Dataset()
        title.add_new(Tag(0x0008, 0x0100), "SH", self._TITLE_CODE)  # CodeValue
        title.add_new(Tag(0x0008, 0x0102), "SH", "DCM")  # CodingSchemeDesignator
        title.add_new(Tag(0x0008, 0x0104), "LO", self._TITLE_MEANING)  # CodeMeaning
        ds.add_new(Tag(0x0040, 0xA043), "SQ", Sequence([title]))  # ConceptNameCodeSequence

        text_item = Dataset()
        text_item.add_new(Tag(0x0040, 0xA040), "CS", "TEXT")  # ValueType
        text_item.add_new(Tag(0x0040, 0xA160), "UT", "Key Image")  # TextValue
        text_item.add_new(Tag(0x0040, 0xA123), "PN", "SMITH^JOHN")  # PersonName (PHI)
        text_item.add_new(Tag(0x0040, 0xA032), "DT", "20240101120000")  # ObservationDateTime (PHI)
        ds.add_new(Tag(0x0040, 0xA730), "SQ", Sequence([text_item]))  # ContentSequence
        return ds

    def test_content_root_and_coded_title_retained(self, profile_harness):
        """The Content Sequence and its coded document title survive strict."""
        from pydicom.tag import Tag

        result = profile_harness.apply_profile("strict", dataset=self._ko_dataset())
        assert Tag(0x0040, 0xA730) in result, "Content Sequence should be retained"
        title = result[Tag(0x0040, 0xA043)].value[0]
        assert str(title[Tag(0x0008, 0x0100)].value) == self._TITLE_CODE, "document title code value retained"
        assert str(title[Tag(0x0008, 0x0104)].value) == self._TITLE_MEANING, "document title meaning retained"

    def test_phi_inside_content_removed(self, profile_harness):
        """PHI nested in the retained Content Sequence is de-identified."""
        result = profile_harness.apply_profile("strict", dataset=self._ko_dataset())
        values = set(_scalar_strings(result))
        assert "SMITH^JOHN" not in values, "PersonName in content should be removed"
        assert "20240101120000" not in values, "ObservationDateTime in content should be removed"


def _scalar_strings(ds):
    """Yield the string form of every scalar value, descending into sequences."""
    for elem in ds:
        try:
            vr = elem.VR
        except (ValueError, NotImplementedError):
            continue
        if vr == "SQ" and elem.value:
            for item in elem.value:
                yield from _scalar_strings(item)
            continue
        value = elem.value
        if isinstance(value, (list, tuple)) or type(value).__name__ == "MultiValue":
            for sub in value:
                yield str(sub)
        else:
            yield str(value)
