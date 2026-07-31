"""Tests for DeidProfile.apply() behavior."""

from pydicom.dataset import Dataset
from pydicom.tag import Tag

from dicom_dre.actions import empty
from dicom_dre.actions import keep
from dicom_dre.actions import set_value
from dicom_dre.catalog import PrivateTagSpec
from dicom_dre.parameters import DeidParameters
from dicom_dre.profile import DeidProfile


_PARAMS = DeidParameters()


def _minimal_profile(**overrides):
    """Build a minimal DeidProfile with sensible defaults."""
    defaults = {
        "name": "test",
        "rules": {},
        "keep_groups": frozenset(),
        "remove_private": False,
        "remove_curves": False,
        "remove_overlays": False,
    }
    defaults.update(overrides)
    return DeidProfile(**defaults)


class TestSpecificCharacterSetDefault:
    """A default ISO_IR 100 SpecificCharacterSet is inserted when absent."""

    TAG = Tag(0x0008, 0x0005)

    def test_inserts_iso_ir_100_when_absent(self):
        """SpecificCharacterSet is created with 'ISO_IR 100' when missing."""
        ds = Dataset()
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)
        assert self.TAG in ds
        assert ds[self.TAG].value == "ISO_IR 100"

    def test_preserves_existing_value(self):
        """SpecificCharacterSet is not overwritten when already present."""
        ds = Dataset()
        ds.add_new(self.TAG, "CS", "ISO_IR 192")
        profile = _minimal_profile(rules={self.TAG: keep()})
        profile.apply(ds, _PARAMS)
        assert ds[self.TAG].value == "ISO_IR 192"

    def test_replaces_empty_value(self):
        """An existing empty SpecificCharacterSet is set to ISO_IR 100."""
        ds = Dataset()
        ds.add_new(self.TAG, "CS", "")
        profile = _minimal_profile(rules={self.TAG: keep()})
        profile.apply(ds, _PARAMS)
        assert ds[self.TAG].value == "ISO_IR 100"


class TestPrivateTagExemption:
    """Private tags with explicit rules survive remove_private."""

    def test_scripted_private_tag_preserved(self):
        """A private tag with a rule is not removed by remove_private."""
        private_tag = Tag(0x0009, 0x0010)
        ds = Dataset()
        ds.add_new(private_tag, "LO", "VENDOR")
        profile = _minimal_profile(
            rules={private_tag: set_value("VENDOR")},
            remove_private=True,
        )
        profile.apply(ds, _PARAMS)
        assert private_tag in ds
        assert ds[private_tag].value == "VENDOR"

    def test_unscripted_private_tag_removed(self):
        """A private tag without a rule is removed by remove_private."""
        ds = Dataset()
        other_private = Tag(0x0009, 0x0010)
        ds.add_new(other_private, "LO", "vendor data")
        profile = _minimal_profile(remove_private=True)
        profile.apply(ds, _PARAMS)
        assert other_private not in ds

    def test_private_tags_kept_when_remove_private_false(self):
        """Private tags remain when remove_private is False."""
        ds = Dataset()
        other_private = Tag(0x0009, 0x0010)
        ds.add_new(other_private, "LO", "vendor data")
        profile = _minimal_profile(remove_private=False)
        profile.apply(ds, _PARAMS)
        assert other_private in ds


class TestNoActionTagsEmptyValue:
    """Empty-action tags are set to '' rather than removed."""

    def test_existing_tag_set_to_empty(self):
        """A NO_ACTION_TAG present in input is set to empty string."""
        tag = Tag(0x0040, 0x1003)  # RequestedProcedurePriority
        ds = Dataset()
        ds.add_new(tag, "SH", "HIGH")
        profile = _minimal_profile(rules={tag: empty()})
        profile.apply(ds, _PARAMS)
        assert tag in ds
        assert ds[tag].value == ""

    def test_absent_tag_not_created(self):
        """A NO_ACTION_TAG absent from input is not created."""
        tag = Tag(0x0040, 0x1003)  # RequestedProcedurePriority
        ds = Dataset()
        profile = _minimal_profile(rules={tag: empty()})
        profile.apply(ds, _PARAMS)
        assert tag not in ds


class TestCurveRetention:
    """Curve data (50xx) is not removed despite the remove-curves flag."""

    def test_curves_kept_when_remove_curves_false(self):
        """Curve elements survive when remove_curves is False."""
        curve_tag = Tag(0x5000, 0x0005)  # CurveDimensions
        ds = Dataset()
        ds.add_new(curve_tag, "US", 1)
        profile = _minimal_profile(remove_curves=False)
        profile.apply(ds, _PARAMS)
        assert curve_tag in ds

    def test_curves_removed_when_remove_curves_true(self):
        """Curve elements are removed when remove_curves is True."""
        curve_tag = Tag(0x5000, 0x0005)  # CurveDimensions
        ds = Dataset()
        ds.add_new(curve_tag, "US", 1)
        profile = _minimal_profile(remove_curves=True)
        profile.apply(ds, _PARAMS)
        assert curve_tag not in ds


class TestRemoveUnspecifiedProtection:
    """Group 0x0028, 0x7FE0, and critical UIDs are always protected."""

    def _scrub_profile(self, **overrides):
        defaults = {
            "name": "test-scrub",
            "rules": {},
            "keep_groups": frozenset(),
            "remove_private": True,
            "remove_curves": False,
            "remove_overlays": True,
            "remove_unspecified": True,
        }
        defaults.update(overrides)
        return DeidProfile(**defaults)

    def test_group_0028_protected(self):
        """Group 0x0028 elements survive remove_unspecified without rules."""
        tag = Tag(0x0028, 0x0010)  # Rows
        ds = Dataset()
        ds.add_new(tag, "US", 512)
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag in ds

    def test_group_7fe0_protected(self):
        """Group 0x7FE0 elements survive remove_unspecified without rules."""
        tag = Tag(0x7FE0, 0x0010)  # PixelData
        ds = Dataset()
        ds.add_new(tag, "OB", b"\x00")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag in ds

    def test_sop_class_uid_protected(self):
        """SOPClassUID survives remove_unspecified without a rule."""
        tag = Tag(0x0008, 0x0016)
        ds = Dataset()
        ds.add_new(tag, "UI", "1.2.840.10008.5.1.4.1.1.2")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag in ds

    def test_sop_instance_uid_protected(self):
        """SOPInstanceUID survives remove_unspecified without a rule."""
        tag = Tag(0x0008, 0x0018)
        ds = Dataset()
        ds.add_new(tag, "UI", "1.2.3.4.5")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag in ds

    def test_study_instance_uid_protected(self):
        """StudyInstanceUID survives remove_unspecified without a rule."""
        tag = Tag(0x0020, 0x000D)
        ds = Dataset()
        ds.add_new(tag, "UI", "1.2.3.4")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag in ds

    def test_unscripted_tag_removed(self):
        """A tag with no rule and no hardcoded protection is removed."""
        tag = Tag(0x0010, 0x1030)  # PatientWeight
        ds = Dataset()
        ds.add_new(tag, "DS", "70")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag not in ds

    def test_scripted_tag_preserved(self):
        """A tag with an explicit rule survives remove_unspecified."""
        tag = Tag(0x0010, 0x0040)  # PatientSex
        ds = Dataset()
        ds.add_new(tag, "CS", "M")
        self._scrub_profile(rules={tag: keep()}).apply(ds, _PARAMS)
        assert tag in ds


class TestGroupLengthRemoval:
    """Retired Group Length (xxxx,0000) tags are stripped after de-identification."""

    def test_removes_top_level_group_length(self):
        """A top-level Group Length tag is removed."""
        ds = Dataset()
        ds.add_new(Tag(0x0008, 0x0000), "UL", 100)
        ds.add_new(Tag(0x0008, 0x0060), "CS", "CT")
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)
        assert Tag(0x0008, 0x0000) not in ds
        assert Tag(0x0008, 0x0060) in ds

    def test_removes_group_length_inside_sequence(self):
        """Group Length tags inside sequence items are removed."""
        from pydicom.sequence import Sequence

        item = Dataset()
        item.add_new(Tag(0x0018, 0x0000), "UL", 204)
        item.add_new(Tag(0x0018, 0x0015), "CS", "SHOULDER")
        nested_item = Dataset()
        nested_item.add_new(Tag(0x0008, 0x0000), "UL", 60)
        nested_item.add_new(Tag(0x0008, 0x0100), "SH", "113691")
        item.add_new(Tag(0x0018, 0x9346), "SQ", Sequence([nested_item]))

        ds = Dataset()
        ds.add_new(Tag(0x0040, 0x030E), "SQ", Sequence([item]))
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)

        result_item = ds[Tag(0x0040, 0x030E)].value[0]
        assert Tag(0x0018, 0x0000) not in result_item
        assert Tag(0x0018, 0x0015) in result_item
        nested_result = result_item[Tag(0x0018, 0x9346)].value[0]
        assert Tag(0x0008, 0x0000) not in nested_result
        assert Tag(0x0008, 0x0100) in nested_result

    def test_preserves_file_meta_group_length(self):
        """(0002,0000) File Meta Information Group Length is preserved."""
        ds = Dataset()
        ds.add_new(Tag(0x0002, 0x0000), "UL", 200)
        ds.add_new(Tag(0x0008, 0x0060), "CS", "CT")
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)
        assert Tag(0x0002, 0x0000) in ds


class TestImplicitVRCorrection:
    """Elements read as OB/UN inside sequences get correct VRs."""

    def test_string_vr_corrected(self):
        """OB element with a string VR in the dictionary is decoded."""
        from pydicom.sequence import Sequence

        item = Dataset()
        item.add_new(Tag(0x0018, 0x8151), "OB", b"10000.00")  # Should be DS
        ds = Dataset()
        ds.add_new(Tag(0x0040, 0x030E), "SQ", Sequence([item]))
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)

        result = ds[Tag(0x0040, 0x030E)].value[0]
        elem = result[Tag(0x0018, 0x8151)]
        assert elem.VR == "DS"
        assert elem.value == "10000.00"

    def test_fd_vr_corrected(self):
        """OB element with VR=FD in the dictionary is decoded as float."""
        import struct

        from pydicom.sequence import Sequence

        item = Dataset()
        item.add_new(Tag(0x0018, 0x9306), "OB", struct.pack("<d", 1.25))
        ds = Dataset()
        ds.add_new(Tag(0x0040, 0x030E), "SQ", Sequence([item]))
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)

        result = ds[Tag(0x0040, 0x030E)].value[0]
        elem = result[Tag(0x0018, 0x9306)]
        assert elem.VR == "FD"
        assert elem.value == 1.25

    def test_correct_vr_left_unchanged(self):
        """Elements with correct VRs are not modified."""
        from pydicom.sequence import Sequence

        item = Dataset()
        item.add_new(Tag(0x0018, 0x0015), "CS", "CHEST")
        ds = Dataset()
        ds.add_new(Tag(0x0040, 0x030E), "SQ", Sequence([item]))
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)

        result = ds[Tag(0x0040, 0x030E)].value[0]
        elem = result[Tag(0x0018, 0x0015)]
        assert elem.VR == "CS"
        assert elem.value == "CHEST"


# Specs mirroring the GE SIGNA Premier MR device rule.
_GEMS_ACQU_SPEC = PrivateTagSpec(group=0x0019, creator="GEMS_ACQU_01", offsets=(0xBB, 0xBC, 0xBD))
_GEMS_PARM_SPEC = PrivateTagSpec(group=0x0043, creator="GEMS_PARM_01", offsets=(0x2F,))


def _signa_premier_dataset(block: int = 0x10) -> Dataset:
    """Build a dataset carrying the GE SIGNA Premier private elements.

    Args:
        block: Private-creator block number for both private groups.

    Returns:
        A Dataset with creator elements and the four preserved data elements,
        plus one unrelated private element that should be removed.
    """
    ds = Dataset()
    ds.add_new(Tag(0x0019, block), "LO", "GEMS_ACQU_01")
    ds.add_new(Tag(0x0019, (block << 8) | 0xBB), "DS", "0")
    ds.add_new(Tag(0x0019, (block << 8) | 0xBC), "DS", "0")
    ds.add_new(Tag(0x0019, (block << 8) | 0xBD), "DS", "0")
    ds.add_new(Tag(0x0043, block), "LO", "GEMS_PARM_01")
    ds.add_new(Tag(0x0043, (block << 8) | 0x2F), "SS", 3)
    # Unrelated private element that must be removed by remove_private.
    ds.add_new(Tag(0x0019, (block << 8) | 0xEE), "LO", "vendor junk")
    return ds


class TestPreservedPrivateBlockResolution:
    """_resolve_preserved_tags resolves the creator block dynamically."""

    def test_default_block_resolves(self):
        """Preserved elements in block 0x10 resolve to concrete tags."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC, _GEMS_PARM_SPEC}),
        )
        keep_tags = profile._resolve_preserved_tags(ds)
        assert Tag(0x0019, 0x0010) in keep_tags, "creator (0019,0010) not resolved"
        assert Tag(0x0019, 0x10BB) in keep_tags, "data element (0019,10BB) not resolved"
        assert Tag(0x0043, 0x102F) in keep_tags, "data element (0043,102F) not resolved"

    def test_non_default_block_resolves(self):
        """A creator in block 0x11 resolves to that block's data elements."""
        ds = _signa_premier_dataset(block=0x11)
        profile = _minimal_profile(
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC, _GEMS_PARM_SPEC}),
        )
        keep_tags = profile._resolve_preserved_tags(ds)
        assert Tag(0x0019, 0x0011) in keep_tags, "creator in block 0x11 not resolved"
        assert Tag(0x0019, 0x11BB) in keep_tags, "data element (0019,11BB) not resolved"
        assert Tag(0x0043, 0x112F) in keep_tags, "data element (0043,112F) not resolved"

    def test_multiple_creators_one_group_resolve(self):
        """Two creators in one group resolve to their respective blocks."""
        ds = Dataset()
        ds.add_new(Tag(0x0019, 0x0010), "LO", "GEMS_ACQU_02")
        ds.add_new(Tag(0x0019, 0x10BB), "DS", "5")
        ds.add_new(Tag(0x0019, 0x0011), "LO", "GEMS_ACQU_01")
        ds.add_new(Tag(0x0019, 0x11BB), "DS", "0")
        profile = _minimal_profile(
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        keep_tags = profile._resolve_preserved_tags(ds)
        assert Tag(0x0019, 0x0011) in keep_tags, "GEMS_ACQU_01 creator in block 0x11 not resolved"
        assert Tag(0x0019, 0x11BB) in keep_tags, "data element in block 0x11 not resolved"
        assert Tag(0x0019, 0x10BB) not in keep_tags, "element from the other creator's block wrongly kept"

    def test_missing_creator_yields_no_preservation(self):
        """A spec whose creator is absent contributes no preserved tags."""
        ds = Dataset()
        ds.add_new(Tag(0x0019, 0x0010), "LO", "SOMETHING_ELSE")
        profile = _minimal_profile(
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        assert profile._resolve_preserved_tags(ds) == set(), "absent creator should yield no preserved tags"

    def test_padded_creator_value_matches(self):
        """A space-padded creator value still matches the spec."""
        ds = Dataset()
        ds.add_new(Tag(0x0019, 0x0010), "LO", "GEMS_ACQU_01 ")
        ds.add_new(Tag(0x0019, 0x10BB), "DS", "0")
        profile = _minimal_profile(
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        keep_tags = profile._resolve_preserved_tags(ds)
        assert Tag(0x0019, 0x10BB) in keep_tags, "space-padded creator value should still match"


class TestPreservedPrivateKeepVsRemove:
    """Preserved private elements survive while others are removed."""

    def test_preserved_elements_survive(self):
        """The four preserved elements and creators survive remove_private."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC, _GEMS_PARM_SPEC}),
        )
        profile.apply(ds, _PARAMS)
        assert Tag(0x0019, 0x0010) in ds, "GEMS_ACQU_01 creator removed"
        assert Tag(0x0019, 0x10BB) in ds, "preserved (0019,10BB) removed"
        assert Tag(0x0019, 0x10BC) in ds, "preserved (0019,10BC) removed"
        assert Tag(0x0019, 0x10BD) in ds, "preserved (0019,10BD) removed"
        assert Tag(0x0043, 0x0010) in ds, "GEMS_PARM_01 creator removed"
        assert Tag(0x0043, 0x102F) in ds, "preserved (0043,102F) removed"
        # The unrelated private element is still removed.
        assert Tag(0x0019, 0x10EE) not in ds, "unrelated private element should be removed"

    def test_without_specs_all_private_removed(self):
        """Without specs, every private element is removed (regression guard)."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(remove_private=True)
        profile.apply(ds, _PARAMS)
        assert Tag(0x0019, 0x0010) not in ds, "creator should be removed without specs"
        assert Tag(0x0019, 0x10BB) not in ds, "(0019,10BB) should be removed without specs"
        assert Tag(0x0043, 0x102F) not in ds, "(0043,102F) should be removed without specs"

    def test_preserved_elements_in_process_sequence_survive(self):
        """Preserved private elements nested in a processed sequence item survive."""
        from pydicom.sequence import Sequence

        from dicom_dre.actions import process

        item = Dataset()
        item.add_new(Tag(0x0019, 0x0010), "LO", "GEMS_ACQU_01")
        item.add_new(Tag(0x0019, 0x10BB), "DS", "0")
        item.add_new(Tag(0x0019, 0x10EE), "LO", "vendor junk")
        seq_tag = Tag(0x0040, 0x030E)
        ds = Dataset()
        ds.add_new(seq_tag, "SQ", Sequence([item]))
        profile = _minimal_profile(
            rules={seq_tag: process()},
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        profile.apply(ds, _PARAMS)
        result_item = ds[seq_tag].value[0]
        assert Tag(0x0019, 0x10BB) in result_item, "preserved element in sequence item removed"
        assert Tag(0x0019, 0x10EE) not in result_item, "unrelated private element in sequence item should be removed"


class TestDeidMethodCodeSequence:
    """(0012,0064) emission is gated on preserved private specs."""

    TAG = Tag(0x0012, 0x0064)

    def _code_values(self, ds: Dataset) -> set[str]:
        return {str(item[Tag(0x0008, 0x0100)].value) for item in ds[self.TAG].value}

    def test_absent_without_specs(self):
        """No (0012,0064) sequence when no specs are configured."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(remove_private=True)
        profile.apply(ds, _PARAMS)
        assert self.TAG not in ds, "(0012,0064) should not be emitted without specs"

    def test_base_codes_present_with_specs(self):
        """113100 and 113111 are emitted when specs are present."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC, _GEMS_PARM_SPEC}),
        )
        profile.apply(ds, _PARAMS)
        assert self.TAG in ds, "(0012,0064) should be emitted when specs are present"
        codes = self._code_values(ds)
        assert "113100" in codes, f"113100 missing: {codes}"
        assert "113111" in codes, f"113111 missing: {codes}"

    def test_modified_dates_code_present_for_date_modifying_profile(self):
        """113107 is emitted when the profile modifies (jitters) dates."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(
            remove_private=True,
            modifies_dates=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        profile.apply(ds, _PARAMS)
        assert "113107" in self._code_values(ds), "113107 should be emitted for a date-modifying profile"

    def test_modified_dates_code_absent_for_date_preserving_profile(self):
        """113107 is not emitted when the profile preserves dates (LDS)."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(
            remove_private=True,
            preserve_dates=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        profile.apply(ds, _PARAMS)
        codes = self._code_values(ds)
        assert "113111" in codes, f"113111 missing for date-preserving profile: {codes}"
        assert "113107" not in codes, f"113107 should be absent for date-preserving profile: {codes}"

    def test_modified_dates_code_absent_for_date_removing_profile(self):
        """113107 is not emitted when dates are removed (pixels-only)."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(
            remove_private=True,
            remove_unspecified=True,
            modifies_dates=False,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        profile.apply(ds, _PARAMS)
        codes = self._code_values(ds)
        assert "113111" in codes, f"113111 missing for date-removing profile: {codes}"
        assert "113107" not in codes, f"113107 should be absent for date-removing profile: {codes}"

    def test_coding_scheme_designator_is_dcm(self):
        """Each code item uses the DCM coding scheme designator."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        profile.apply(ds, _PARAMS)
        for item in ds[self.TAG].value:
            assert str(item[Tag(0x0008, 0x0102)].value) == "DCM", "coding scheme designator should be DCM"


class TestJitterValidation:
    """apply() reconciles params.jitter with the profile's date policy."""

    STUDY_DATE_TAG = Tag(0x0008, 0x0020)

    def _date_profile(self, **overrides):
        from dicom_dre.actions import if_exists
        from dicom_dre.actions import jitter_date

        defaults = {
            "name": "date-test",
            "rules": {self.STUDY_DATE_TAG: if_exists(jitter_date())},
            "keep_groups": frozenset(),
            "remove_private": False,
            "remove_curves": False,
            "remove_overlays": False,
            "modifies_dates": True,
            "hash_salt": "test-salt",
        }
        defaults.update(overrides)
        return DeidProfile(**defaults)

    def _dataset(self) -> Dataset:
        ds = Dataset()
        ds.add_new(self.STUDY_DATE_TAG, "DA", "20200110")
        return ds

    def test_explicit_zero_jitter_rejected_for_date_shifting_profile(self):
        """A date-shifting profile rejects an explicit jitter of zero."""
        import pytest

        profile = self._date_profile()
        ds = self._dataset()
        with pytest.raises(ValueError, match="jitter"):
            profile.apply(ds, DeidParameters(jitter=0))

    def test_unset_jitter_shifts_by_stable_amount(self):
        """An unset jitter shifts by the deterministic per-patient/study amount."""
        from dicom_dre.uid_utils import stable_jitter

        profile = self._date_profile()
        ds = self._dataset()
        profile.apply(ds, DeidParameters())
        # No PatientID in the dataset, so the patient key is empty; study_id is UNKNOWN.
        expected_days = stable_jitter("test-salt", "UNKNOWN", "")
        assert expected_days != 0, "derived jitter must be non-zero"
        assert str(ds[self.STUDY_DATE_TAG].value) == "20200120", (
            f"unset jitter should shift by the stable amount ({expected_days} days)"
        )

    def test_unset_jitter_varies_with_patient_id(self):
        """The derived shift depends on the original PatientID for longitudinal consistency."""
        profile = self._date_profile()
        shifts = set()
        for patient_id in ("MRN-1", "MRN-2", "MRN-3", "MRN-4", "MRN-5"):
            ds = self._dataset()
            ds.add_new(Tag(0x0010, 0x0020), "LO", patient_id)  # PatientID
            profile.apply(ds, DeidParameters())
            shifts.add(str(ds[self.STUDY_DATE_TAG].value))
        assert len(shifts) > 1, f"Different PatientIDs should produce different shifts, got {shifts}"

    def test_explicit_jitter_shifts_by_that_amount(self):
        """An explicit jitter shifts a date-shifting profile by that many days."""
        profile = self._date_profile()
        ds = self._dataset()
        profile.apply(ds, DeidParameters(jitter=5))
        assert str(ds[self.STUDY_DATE_TAG].value) == "20200115", "jitter of 5 should shift by 5 days"

    def test_zero_jitter_inert_for_non_shifting_profile(self):
        """A non-shifting profile accepts any jitter and does not shift dates."""
        profile = self._date_profile(modifies_dates=False, preserve_dates=True)
        ds = self._dataset()
        profile.apply(ds, DeidParameters(jitter=0))
        assert str(ds[self.STUDY_DATE_TAG].value) == "20200110", "non-shifting profile should not shift the date"


class TestDefaultProfileJitterSource:
    """The default profile derives its unset jitter from the original PHI PatientID."""

    STUDY_DATE_TAG = Tag(0x0008, 0x0020)
    PATIENT_ID_TAG = Tag(0x0010, 0x0020)

    def _dataset(self, patient_id: str) -> Dataset:
        ds = Dataset()
        ds.add_new(self.STUDY_DATE_TAG, "DA", "20200110")
        ds.add_new(self.PATIENT_ID_TAG, "LO", patient_id)
        return ds

    def test_shift_uses_original_patient_id_not_hashed(self):
        """The shift matches the original PatientID and PatientID is still hashed."""
        from datetime import datetime
        from datetime import timedelta

        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile
        from dicom_dre.uid_utils import stable_jitter

        profile = default_profile(ProfileSettings(hash_salt="pepper"))
        ds = self._dataset("MRN999")
        profile.apply(ds, DeidParameters())

        expected_days = stable_jitter("pepper", "UNKNOWN", "MRN999")
        expected_date = (datetime.strptime("20200110", "%Y%m%d") + timedelta(days=expected_days)).strftime("%Y%m%d")
        assert str(ds[self.STUDY_DATE_TAG].value) == expected_date, (
            "StudyDate should shift by the jitter derived from the original PatientID"
        )
        assert str(ds[self.PATIENT_ID_TAG].value) != "MRN999", "PatientID should still be hashed in the output"

    def test_same_patient_different_study_shifts_differently(self):
        """One patient across two studies receives different shifts."""
        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile

        profile = default_profile(ProfileSettings(hash_salt="pepper"))
        ds_a = self._dataset("MRN999")
        ds_b = self._dataset("MRN999")
        profile.apply(ds_a, DeidParameters(study_id="STUDY_A"))
        profile.apply(ds_b, DeidParameters(study_id="STUDY_B"))
        assert str(ds_a[self.STUDY_DATE_TAG].value) != str(ds_b[self.STUDY_DATE_TAG].value), (
            "The same patient in different studies should shift dates differently"
        )
