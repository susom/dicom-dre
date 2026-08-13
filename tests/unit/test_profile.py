"""Tests for DeidProfile.apply() behavior."""

from pydicom.dataset import Dataset
from pydicom.tag import Tag

from dicom_dre.actions import empty
from dicom_dre.actions import keep
from dicom_dre.actions import set_value
from dicom_dre.parameters import DeidParameters
from dicom_dre.profile import DeidProfile
from dicom_dre.profile import PrivateTagSpec


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
        assert self.TAG in ds, "SpecificCharacterSet should be inserted when absent"
        assert ds[self.TAG].value == "ISO_IR 100", f"expected 'ISO_IR 100', got {ds[self.TAG].value!r}"

    def test_preserves_existing_value(self):
        """SpecificCharacterSet is not overwritten when already present."""
        ds = Dataset()
        ds.add_new(self.TAG, "CS", "ISO_IR 192")
        profile = _minimal_profile(rules={self.TAG: keep()})
        profile.apply(ds, _PARAMS)
        assert ds[self.TAG].value == "ISO_IR 192", (
            f"existing SpecificCharacterSet should be preserved, got {ds[self.TAG].value!r}"
        )

    def test_replaces_empty_value(self):
        """An existing empty SpecificCharacterSet is set to ISO_IR 100."""
        ds = Dataset()
        ds.add_new(self.TAG, "CS", "")
        profile = _minimal_profile(rules={self.TAG: keep()})
        profile.apply(ds, _PARAMS)
        assert ds[self.TAG].value == "ISO_IR 100", (
            f"empty SpecificCharacterSet should become 'ISO_IR 100', got {ds[self.TAG].value!r}"
        )


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
        assert private_tag in ds, "scripted private tag should be preserved under remove_private"
        assert ds[private_tag].value == "VENDOR", f"expected 'VENDOR', got {ds[private_tag].value!r}"

    def test_unscripted_private_tag_removed(self):
        """A private tag without a rule is removed by remove_private."""
        ds = Dataset()
        other_private = Tag(0x0009, 0x0010)
        ds.add_new(other_private, "LO", "vendor data")
        profile = _minimal_profile(remove_private=True)
        profile.apply(ds, _PARAMS)
        assert other_private not in ds, "unscripted private tag should be removed by remove_private"

    def test_private_tags_kept_when_remove_private_false(self):
        """Private tags remain when remove_private is False."""
        ds = Dataset()
        other_private = Tag(0x0009, 0x0010)
        ds.add_new(other_private, "LO", "vendor data")
        profile = _minimal_profile(remove_private=False)
        profile.apply(ds, _PARAMS)
        assert other_private in ds, "private tags should be kept when remove_private is False"


class TestNoActionTagsEmptyValue:
    """Empty-action tags are set to '' rather than removed."""

    def test_existing_tag_set_to_empty(self):
        """A NO_ACTION_TAG present in input is set to empty string."""
        tag = Tag(0x0040, 0x1003)  # RequestedProcedurePriority
        ds = Dataset()
        ds.add_new(tag, "SH", "HIGH")
        profile = _minimal_profile(rules={tag: empty()})
        profile.apply(ds, _PARAMS)
        assert tag in ds, "empty-action tag present in input should be retained"
        assert ds[tag].value == "", f"NO_ACTION_TAG should be set to empty string, got {ds[tag].value!r}"

    def test_absent_tag_not_created(self):
        """A NO_ACTION_TAG absent from input is not created."""
        tag = Tag(0x0040, 0x1003)  # RequestedProcedurePriority
        ds = Dataset()
        profile = _minimal_profile(rules={tag: empty()})
        profile.apply(ds, _PARAMS)
        assert tag not in ds, "absent NO_ACTION_TAG should not be created"


class TestCurveRetention:
    """Curve data (50xx) is not removed despite the remove-curves flag."""

    def test_curves_kept_when_remove_curves_false(self):
        """Curve elements survive when remove_curves is False."""
        curve_tag = Tag(0x5000, 0x0005)  # CurveDimensions
        ds = Dataset()
        ds.add_new(curve_tag, "US", 1)
        profile = _minimal_profile(remove_curves=False)
        profile.apply(ds, _PARAMS)
        assert curve_tag in ds, "curve elements should survive when remove_curves is False"

    def test_curves_removed_when_remove_curves_true(self):
        """Curve elements are removed when remove_curves is True."""
        curve_tag = Tag(0x5000, 0x0005)  # CurveDimensions
        ds = Dataset()
        ds.add_new(curve_tag, "US", 1)
        profile = _minimal_profile(remove_curves=True)
        profile.apply(ds, _PARAMS)
        assert curve_tag not in ds, "curve elements should be removed when remove_curves is True"


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
        assert tag in ds, "group 0x0028 should survive remove_unspecified"

    def test_group_7fe0_protected(self):
        """Group 0x7FE0 elements survive remove_unspecified without rules."""
        tag = Tag(0x7FE0, 0x0010)  # PixelData
        ds = Dataset()
        ds.add_new(tag, "OB", b"\x00")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag in ds, "group 0x7FE0 (PixelData) should survive remove_unspecified"

    def test_sop_class_uid_protected(self):
        """SOPClassUID survives remove_unspecified without a rule."""
        tag = Tag(0x0008, 0x0016)
        ds = Dataset()
        ds.add_new(tag, "UI", "1.2.840.10008.5.1.4.1.1.2")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag in ds, "SOPClassUID should survive remove_unspecified"

    def test_sop_instance_uid_protected(self):
        """SOPInstanceUID survives remove_unspecified without a rule."""
        tag = Tag(0x0008, 0x0018)
        ds = Dataset()
        ds.add_new(tag, "UI", "1.2.3.4.5")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag in ds, "SOPInstanceUID should survive remove_unspecified"

    def test_study_instance_uid_protected(self):
        """StudyInstanceUID survives remove_unspecified without a rule."""
        tag = Tag(0x0020, 0x000D)
        ds = Dataset()
        ds.add_new(tag, "UI", "1.2.3.4")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag in ds, "StudyInstanceUID should survive remove_unspecified"

    def test_unscripted_tag_removed(self):
        """A tag with no rule and no hardcoded protection is removed."""
        tag = Tag(0x0010, 0x1030)  # PatientWeight
        ds = Dataset()
        ds.add_new(tag, "DS", "70")
        self._scrub_profile().apply(ds, _PARAMS)
        assert tag not in ds, "unscripted unprotected tag should be removed by remove_unspecified"

    def test_scripted_tag_preserved(self):
        """A tag with an explicit rule survives remove_unspecified."""
        tag = Tag(0x0010, 0x0040)  # PatientSex
        ds = Dataset()
        ds.add_new(tag, "CS", "M")
        self._scrub_profile(rules={tag: keep()}).apply(ds, _PARAMS)
        assert tag in ds, "tag with an explicit rule should survive remove_unspecified"


class TestGroupLengthRemoval:
    """Retired Group Length (xxxx,0000) tags are stripped after de-identification."""

    def test_removes_top_level_group_length(self):
        """A top-level Group Length tag is removed."""
        ds = Dataset()
        ds.add_new(Tag(0x0008, 0x0000), "UL", 100)
        ds.add_new(Tag(0x0008, 0x0060), "CS", "CT")
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)
        assert Tag(0x0008, 0x0000) not in ds, "top-level Group Length tag should be removed"
        assert Tag(0x0008, 0x0060) in ds, "non-group-length element should be retained"

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
        assert Tag(0x0018, 0x0000) not in result_item, "Group Length inside sequence item should be removed"
        assert Tag(0x0018, 0x0015) in result_item, "non-group-length element in sequence item should be retained"
        nested_result = result_item[Tag(0x0018, 0x9346)].value[0]
        assert Tag(0x0008, 0x0000) not in nested_result, "Group Length in nested sequence item should be removed"
        assert Tag(0x0008, 0x0100) in nested_result, "non-group-length element in nested item should be retained"

    def test_preserves_file_meta_group_length(self):
        """(0002,0000) File Meta Information Group Length is preserved."""
        ds = Dataset()
        ds.add_new(Tag(0x0002, 0x0000), "UL", 200)
        ds.add_new(Tag(0x0008, 0x0060), "CS", "CT")
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)
        assert Tag(0x0002, 0x0000) in ds, "File Meta Information Group Length should be preserved"


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
        assert elem.VR == "DS", f"expected VR 'DS', got {elem.VR!r}"
        assert elem.value == "10000.00", f"expected '10000.00', got {elem.value!r}"

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
        assert elem.VR == "FD", f"expected VR 'FD', got {elem.VR!r}"
        assert elem.value == 1.25, f"expected 1.25, got {elem.value!r}"

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
        assert elem.VR == "CS", f"expected VR 'CS', got {elem.VR!r}"
        assert elem.value == "CHEST", f"expected 'CHEST', got {elem.value!r}"


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
        """Preserved private elements nested in a sequence item survive."""
        from pydicom.sequence import Sequence

        item = Dataset()
        item.add_new(Tag(0x0019, 0x0010), "LO", "GEMS_ACQU_01")
        item.add_new(Tag(0x0019, 0x10BB), "DS", "0")
        item.add_new(Tag(0x0019, 0x10EE), "LO", "vendor junk")
        seq_tag = Tag(0x0040, 0x030E)
        ds = Dataset()
        ds.add_new(seq_tag, "SQ", Sequence([item]))
        profile = _minimal_profile(
            rules={seq_tag: keep()},
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        profile.apply(ds, _PARAMS)
        result_item = ds[seq_tag].value[0]
        assert Tag(0x0019, 0x10BB) in result_item, "preserved element in sequence item removed"
        assert Tag(0x0019, 0x10EE) not in result_item, "unrelated private element in sequence item should be removed"


class TestDeidMethodCodeSequence:
    """(0012,0064) is emitted on every de-identified dataset."""

    TAG = Tag(0x0012, 0x0064)

    def _code_values(self, ds: Dataset) -> set[str]:
        return {str(item[Tag(0x0008, 0x0100)].value) for item in ds[self.TAG].value}

    def test_present_without_specs(self):
        """(0012,0064) is emitted without specs; 113100 present, 113111 absent."""
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(remove_private=True)
        profile.apply(ds, _PARAMS)
        assert self.TAG in ds, "(0012,0064) should be emitted on every dataset"
        codes = self._code_values(ds)
        assert "113100" in codes, f"113100 missing: {codes}"
        assert "113111" not in codes, f"113111 should be absent without preserved specs: {codes}"

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

    def test_113111_absent_when_private_not_removed(self):
        """113111 is not emitted when remove_private is False.

        With private removal disabled, every private element is kept, which is
        not the selective safe private option, so 113111 must not be emitted
        even though the approved creator block is present.
        """
        ds = _signa_premier_dataset(block=0x10)
        profile = _minimal_profile(
            remove_private=False,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC, _GEMS_PARM_SPEC}),
        )
        profile.apply(ds, _PARAMS)
        codes = self._code_values(ds)
        assert "113111" not in codes, f"113111 should be absent when remove_private is False: {codes}"

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
        """113107 is not emitted when dates are removed (strict)."""
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

    def test_explicit_jitter_rejected_for_non_shifting_profile(self):
        """A date-preserving profile rejects an explicit non-zero jitter."""
        import pytest

        profile = self._date_profile(modifies_dates=False, preserve_dates=True)
        ds = self._dataset()
        with pytest.raises(ValueError, match="jitter"):
            profile.apply(ds, DeidParameters(jitter=5))

    def test_zero_jitter_inert_for_non_shifting_profile(self):
        """A non-shifting profile accepts jitter=0 and does not shift dates."""
        profile = self._date_profile(modifies_dates=False, preserve_dates=True)
        ds = self._dataset()
        profile.apply(ds, DeidParameters(jitter=0))
        assert str(ds[self.STUDY_DATE_TAG].value) == "20200110", "non-shifting profile should not shift the date"

    def test_unset_jitter_inert_for_non_shifting_profile(self):
        """A non-shifting profile accepts an unset jitter and does not shift dates."""
        profile = self._date_profile(modifies_dates=False, preserve_dates=True)
        ds = self._dataset()
        profile.apply(ds, DeidParameters())
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


def _iter_elements(ds):
    """Yield every data element in *ds*, descending into sequence items."""
    for elem in ds:
        yield elem
        if elem.VR == "SQ" and elem.value:
            for item in elem.value:
                yield from _iter_elements(item)


def _all_string_values(ds) -> list[str]:
    """Return the string form of every non-sequence element value in the tree."""
    values: list[str] = []
    for elem in _iter_elements(ds):
        if elem.VR == "SQ":
            continue
        value = elem.value
        if isinstance(value, bytes):
            value = value.decode("ascii", errors="replace")
        values.append(str(value))
    return values


class TestGspsProfileDeidentification:
    """default_profile de-identifies a GSPS 2D graphic annotation subtree."""

    GAS_TAG = Tag(0x0070, 0x0001)
    REF_SOP = "1.2.3.4.5.6.7.8.9.10"
    TRACKING_UID = "1.9.8.7.6.5.4.3.2.1"
    SERIES_UID = "1.2.840.113619.2.55.3.1234"
    TRACKING_ID = "track-secret-XYZ"
    TEXT_PHI = "ZZQXPHITEXT"
    SH_PHI = "SHPHIZZZ"

    def _gsps_dataset(self) -> Dataset:
        from pydicom.sequence import Sequence

        text_item = Dataset()
        text_item.add_new(Tag(0x0070, 0x0006), "ST", f"Margin {self.TEXT_PHI} lesion")  # UnformattedTextValue
        text_item.add_new(Tag(0x0008, 0x0100), "SH", "T-D4000")  # CodeValue (no rule, kept)
        text_item.add_new(Tag(0x0070, 0x0289), "SH", self.SH_PHI)  # TickLabel (SH) redacted by rule

        style_item = Dataset()
        style_item.add_new(Tag(0x0070, 0x0227), "LO", "Helvetica")  # FontName
        style_item.add_new(Tag(0x0070, 0x0229), "LO", "Arial")  # CSSFontName
        text_item.add_new(Tag(0x0070, 0x0231), "SQ", Sequence([style_item]))  # TextStyleSequence

        graphic_item = Dataset()
        graphic_item.add_new(Tag(0x0070, 0x0023), "CS", "POLYLINE")  # GraphicType
        graphic_item.add_new(Tag(0x0070, 0x0022), "FL", [1.0, 2.0, 3.0, 4.0])  # GraphicData
        graphic_item.add_new(Tag(0x0062, 0x0020), "UT", self.TRACKING_ID)  # TrackingID
        graphic_item.add_new(Tag(0x0062, 0x0021), "UI", self.TRACKING_UID)  # TrackingUID

        ref_image_item = Dataset()
        ref_image_item.add_new(Tag(0x0008, 0x1150), "UI", "1.2.840.10008.5.1.4.1.1.4")  # ReferencedSOPClassUID
        ref_image_item.add_new(Tag(0x0008, 0x1155), "UI", self.REF_SOP)  # ReferencedSOPInstanceUID

        annotation_item = Dataset()
        annotation_item.add_new(Tag(0x0008, 0x1140), "SQ", Sequence([ref_image_item]))  # ReferencedImageSequence
        annotation_item.add_new(Tag(0x0020, 0x000E), "UI", self.SERIES_UID)  # SeriesInstanceUID
        annotation_item.add_new(Tag(0x0070, 0x0002), "CS", "LAYER1")  # GraphicLayer
        annotation_item.add_new(Tag(0x0070, 0x0008), "SQ", Sequence([text_item]))  # TextObjectSequence
        annotation_item.add_new(Tag(0x0070, 0x0009), "SQ", Sequence([graphic_item]))  # GraphicObjectSequence

        ds = Dataset()
        ds.add_new(Tag(0x0008, 0x0016), "UI", "1.2.840.10008.5.1.4.1.1.11.1")  # SOPClassUID
        ds.add_new(Tag(0x0008, 0x0060), "CS", "PR")  # Modality
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN123")  # PatientID
        ds.add_new(self.GAS_TAG, "SQ", Sequence([annotation_item]))
        return ds

    def _apply(self):
        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile

        profile = default_profile(ProfileSettings(hash_salt="pepper"))
        ds = self._gsps_dataset()
        profile.apply(ds, DeidParameters())
        return ds

    def test_annotation_sequence_retained(self):
        """The graphic annotation sequence survives de-identification."""
        ds = self._apply()
        assert self.GAS_TAG in ds, "GraphicAnnotationSequence should be retained"
        assert len(ds[self.GAS_TAG].value) == 1, "annotation item should be preserved"

    def test_no_source_uid_survives(self):
        """No original UID appears anywhere in the output subtree."""
        ds = self._apply()
        values = _all_string_values(ds)
        for source_uid in (self.REF_SOP, self.TRACKING_UID, self.SERIES_UID):
            assert source_uid not in values, f"source UID {source_uid} leaked into output"

    def test_uids_hashed_to_expected_replacement(self):
        """Each surviving subtree UID equals its deterministic hash_uid replacement."""
        from dicom_dre.uid_utils import hashuid

        ds = self._apply()
        item = ds[self.GAS_TAG].value[0]
        series_uid = item[Tag(0x0020, 0x000E)].value
        tracking_uid = item[Tag(0x0070, 0x0009)].value[0][Tag(0x0062, 0x0021)].value
        ref_sop = item[Tag(0x0008, 0x1140)].value[0][Tag(0x0008, 0x1155)].value
        assert str(series_uid) == hashuid("1.2.840.4267.32.", self.SERIES_UID + "UNKNOWN"), (
            f"SeriesInstanceUID should equal its hashed replacement, got {series_uid!r}"
        )
        assert str(tracking_uid) == hashuid("1.2.840.4267.32.", self.TRACKING_UID + "UNKNOWN"), (
            f"TrackingUID should equal its hashed replacement, got {tracking_uid!r}"
        )
        assert str(ref_sop) == hashuid("1.2.840.4267.32.", self.REF_SOP + "UNKNOWN"), (
            f"ReferencedSOPInstanceUID should equal its hashed replacement, got {ref_sop!r}"
        )

    def test_referenced_image_sequence_retained_and_hashed(self):
        """ReferencedImageSequence is retained; its instance UID is hashed and class UID kept."""
        ds = self._apply()
        item = ds[self.GAS_TAG].value[0]
        assert Tag(0x0008, 0x1140) in item, "ReferencedImageSequence should be retained"
        ref_item = item[Tag(0x0008, 0x1140)].value[0]
        assert str(ref_item[Tag(0x0008, 0x1155)].value) != self.REF_SOP, "ReferencedSOPInstanceUID should be hashed"
        assert str(ref_item[Tag(0x0008, 0x1150)].value) == "1.2.840.10008.5.1.4.1.1.4", (
            "ReferencedSOPClassUID should be kept"
        )

    def test_tracking_id_hashed(self):
        """TrackingID is replaced by its study-scoped identifier hash."""
        from dicom_dre.uid_utils import hash_identifier

        ds = self._apply()
        item = ds[self.GAS_TAG].value[0]
        tracking_id = item[Tag(0x0070, 0x0009)].value[0][Tag(0x0062, 0x0020)].value
        expected = hash_identifier(self.TRACKING_ID, salt="pepper", study_id="UNKNOWN")
        assert str(tracking_id) == expected, "TrackingID should be hashed"

    def test_free_text_redacted(self):
        """Free text in text-VR elements is redacted from the subtree."""
        ds = self._apply()
        joined = "\n".join(_all_string_values(ds))
        assert self.TEXT_PHI not in joined, "ST free text should be redacted"
        assert self.SH_PHI not in joined, "SH free text should be redacted"

    def test_exempt_code_value_preserved(self):
        """A CodeValue with no redaction rule is kept."""
        ds = self._apply()
        item = ds[self.GAS_TAG].value[0]
        text_item = item[Tag(0x0070, 0x0008)].value[0]
        assert str(text_item[Tag(0x0008, 0x0100)].value) == "T-D4000", (
            f"exempt CodeValue should be kept, got {text_item[Tag(0x0008, 0x0100)].value!r}"
        )

    def test_font_names_preserved(self):
        """FontName and CSSFontName are preserved as styling, not PHI."""
        ds = self._apply()
        item = ds[self.GAS_TAG].value[0]
        style_item = item[Tag(0x0070, 0x0008)].value[0][Tag(0x0070, 0x0231)].value[0]
        assert str(style_item[Tag(0x0070, 0x0227)].value) == "Helvetica", (
            f"FontName should be preserved, got {style_item[Tag(0x0070, 0x0227)].value!r}"
        )
        assert str(style_item[Tag(0x0070, 0x0229)].value) == "Arial", (
            f"CSSFontName should be preserved, got {style_item[Tag(0x0070, 0x0229)].value!r}"
        )

    def test_geometry_retained(self):
        """Graphic geometry (GraphicType, GraphicData) is retained."""
        ds = self._apply()
        graphic_item = ds[self.GAS_TAG].value[0][Tag(0x0070, 0x0009)].value[0]
        assert str(graphic_item[Tag(0x0070, 0x0023)].value) == "POLYLINE", (
            f"GraphicType should be retained, got {graphic_item[Tag(0x0070, 0x0023)].value!r}"
        )
        assert list(graphic_item[Tag(0x0070, 0x0022)].value) == [1.0, 2.0, 3.0, 4.0], (
            f"GraphicData should be retained, got {list(graphic_item[Tag(0x0070, 0x0022)].value)!r}"
        )

    def test_implicit_vr_text_redacted(self):
        """An implicit-VR (UN) UnformattedTextValue is decoded and redacted."""
        from pydicom.sequence import Sequence

        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile

        text_item = Dataset()
        text_item.add_new(Tag(0x0070, 0x0006), "UN", b"SECRETUNTEXT")  # UnformattedTextValue, implicit VR
        annotation_item = Dataset()
        annotation_item.add_new(Tag(0x0070, 0x0008), "SQ", Sequence([text_item]))  # TextObjectSequence
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")  # PatientID
        ds.add_new(self.GAS_TAG, "SQ", Sequence([annotation_item]))

        default_profile(ProfileSettings(hash_salt="pepper")).apply(ds, DeidParameters())

        elem = ds[self.GAS_TAG].value[0][Tag(0x0070, 0x0008)].value[0][Tag(0x0070, 0x0006)]
        assert elem.VR == "ST", "UN should resolve to the dictionary VR ST"
        assert "SECRETUNTEXT" not in str(elem.value), "implicit-VR free text should be redacted"


class TestReferenceSequenceHashing:
    """The default profile recurses reference sequences and hashes nested UIDs."""

    ORIG_SERIES = "1.2.840.111.222.333"
    ORIG_REF_SOP = "1.2.840.444.555.666"
    ORIG_INSTANCE = "1.2.840.777.888.999"

    def _apply(self) -> Dataset:
        from pydicom.sequence import Sequence

        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile

        ref_image_item = Dataset()
        ref_image_item.add_new(Tag(0x0008, 0x1150), "UI", "1.2.840.10008.5.1.4.1.1.4")  # ReferencedSOPClassUID
        ref_image_item.add_new(Tag(0x0008, 0x1155), "UI", self.ORIG_REF_SOP)  # ReferencedSOPInstanceUID
        series_item = Dataset()
        series_item.add_new(Tag(0x0020, 0x000E), "UI", self.ORIG_SERIES)  # SeriesInstanceUID
        series_item.add_new(Tag(0x0008, 0x1140), "SQ", Sequence([ref_image_item]))  # ReferencedImageSequence

        instance_item = Dataset()
        instance_item.add_new(Tag(0x0008, 0x1150), "UI", "1.2.840.10008.5.1.4.1.1.4")  # ReferencedSOPClassUID
        instance_item.add_new(Tag(0x0008, 0x1155), "UI", self.ORIG_INSTANCE)  # ReferencedSOPInstanceUID

        ds = Dataset()
        ds.add_new(Tag(0x0008, 0x0016), "UI", "1.2.840.10008.5.1.4.1.1.4")  # SOPClassUID
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")  # PatientID
        ds.add_new(Tag(0x0008, 0x1115), "SQ", Sequence([series_item]))  # ReferencedSeriesSequence
        ds.add_new(Tag(0x0008, 0x114A), "SQ", Sequence([instance_item]))  # ReferencedInstanceSequence

        default_profile(ProfileSettings(hash_salt="pepper")).apply(ds, DeidParameters())
        return ds

    def test_referenced_series_sequence_retained(self):
        """ReferencedSeriesSequence and its nested ReferencedImageSequence are retained."""
        ds = self._apply()
        assert Tag(0x0008, 0x1115) in ds, "ReferencedSeriesSequence should be retained"
        series_item = ds[Tag(0x0008, 0x1115)].value[0]
        assert Tag(0x0008, 0x1140) in series_item, "nested ReferencedImageSequence should be retained"

    def test_nested_uids_hashed(self):
        """SeriesInstanceUID and ReferencedSOPInstanceUID nested in the references are hashed."""
        from dicom_dre.uid_utils import hashuid

        ds = self._apply()
        series_item = ds[Tag(0x0008, 0x1115)].value[0]
        series_uid = series_item[Tag(0x0020, 0x000E)].value
        ref_sop = series_item[Tag(0x0008, 0x1140)].value[0][Tag(0x0008, 0x1155)].value
        assert str(series_uid) == hashuid("1.2.840.4267.32.", self.ORIG_SERIES + "UNKNOWN"), (
            f"nested SeriesInstanceUID should be hashed, got {series_uid!r}"
        )
        assert str(ref_sop) == hashuid("1.2.840.4267.32.", self.ORIG_REF_SOP + "UNKNOWN"), (
            f"nested ReferencedSOPInstanceUID should be hashed, got {ref_sop!r}"
        )

    def test_referenced_instance_sequence_retained_and_hashed(self):
        """ReferencedInstanceSequence is retained and its ReferencedSOPInstanceUID is hashed."""
        from dicom_dre.uid_utils import hashuid

        ds = self._apply()
        assert Tag(0x0008, 0x114A) in ds, "ReferencedInstanceSequence should be retained"
        instance_item = ds[Tag(0x0008, 0x114A)].value[0]
        ref_sop = instance_item[Tag(0x0008, 0x1155)].value
        assert str(ref_sop) == hashuid("1.2.840.4267.32.", self.ORIG_INSTANCE + "UNKNOWN"), (
            f"ReferencedSOPInstanceUID should be hashed, got {ref_sop!r}"
        )
        assert str(instance_item[Tag(0x0008, 0x1150)].value) == "1.2.840.10008.5.1.4.1.1.4", (
            "ReferencedSOPClassUID should be kept"
        )

    def test_unmarked_sequence_hashes_instance_uid_keeps_class_uid(self):
        """Recursion into an unmarked nested sequence hashes instance UIDs but keeps class UIDs."""
        from pydicom.sequence import Sequence

        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile
        from dicom_dre.uid_utils import hashuid

        inner = Dataset()
        inner.add_new(Tag(0x0008, 0x1150), "UI", "1.2.840.10008.5.1.4.1.1.4")  # ReferencedSOPClassUID
        inner.add_new(Tag(0x0008, 0x1155), "UI", "ORIG.INST.1")  # ReferencedSOPInstanceUID
        inner.add_new(Tag(0x0020, 0x000E), "UI", "ORIG.SERIES.1")  # SeriesInstanceUID
        outer = Dataset()
        outer.add_new(Tag(0x5200, 0x9230), "SQ", Sequence([inner]))  # PerFrameFunctionalGroupsSequence
        ds = Dataset()
        ds.add_new(Tag(0x0008, 0x0016), "UI", "1.2.840.10008.5.1.4.1.1.4")  # SOPClassUID
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")  # PatientID
        ds.add_new(Tag(0x5200, 0x9229), "SQ", Sequence([outer]))  # SharedFunctionalGroupsSequence

        default_profile(ProfileSettings(hash_salt="pepper")).apply(ds, DeidParameters())

        nested = ds[Tag(0x5200, 0x9229)].value[0][Tag(0x5200, 0x9230)].value[0]
        assert str(ds[Tag(0x0008, 0x0016)].value) == "1.2.840.10008.5.1.4.1.1.4", "top SOPClassUID should be kept"
        assert str(nested[Tag(0x0008, 0x1150)].value) == "1.2.840.10008.5.1.4.1.1.4", (
            "nested ReferencedSOPClassUID should be kept"
        )
        assert str(nested[Tag(0x0020, 0x000E)].value) == hashuid("1.2.840.4267.32.", "ORIG.SERIES.1UNKNOWN"), (
            "nested SeriesInstanceUID should be hashed"
        )
        assert str(nested[Tag(0x0008, 0x1155)].value) == hashuid("1.2.840.4267.32.", "ORIG.INST.1UNKNOWN"), (
            "nested ReferencedSOPInstanceUID should be hashed"
        )


class TestUidFallback:
    """The default profile hashes unregistered UIDs that have no explicit rule."""

    def _apply(self, ds: Dataset) -> Dataset:
        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile

        default_profile(ProfileSettings(hash_salt="pepper")).apply(ds, DeidParameters())
        return ds

    def test_unruled_vendor_uid_hashed(self):
        """An unruled UI element under a vendor root is hashed."""
        from dicom_dre.uid_utils import hashuid

        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")  # placeholder to force apply
        ds.add_new(Tag(0x0030, 0x0010), "UI", "1.2.840.113619.DEVICE.9")  # unruled UI, vendor root
        self._apply(ds)
        assert str(ds[Tag(0x0030, 0x0010)].value) == hashuid("1.2.840.4267.32.", "1.2.840.113619.DEVICE.9UNKNOWN"), (
            f"unruled vendor UID should be hashed, got {ds[Tag(0x0030, 0x0010)].value!r}"
        )

    def test_registered_uid_preserved(self):
        """An unruled UI element under the DICOM root is left unchanged."""
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x0008, 0x001A), "UI", "1.2.840.10008.5.1.4.1.1.2")  # RelatedGeneralSOPClassUID
        self._apply(ds)
        assert str(ds[Tag(0x0008, 0x001A)].value) == "1.2.840.10008.5.1.4.1.1.2", (
            f"registered DICOM-root UID should be left unchanged, got {ds[Tag(0x0008, 0x001A)].value!r}"
        )

    def test_linkage_matches_explicit_uid_rule(self):
        """A UID shared by an explicit rule and an unruled tag hashes identically."""
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x0020, 0x000D), "UI", "1.2.840.113619.STUDY")  # StudyInstanceUID (UID_TAGS)
        ds.add_new(Tag(0x0030, 0x0010), "UI", "1.2.840.113619.STUDY")  # unruled UI, same value
        self._apply(ds)
        assert str(ds[Tag(0x0020, 0x000D)].value) == str(ds[Tag(0x0030, 0x0010)].value), (
            "shared UID should hash to the same replacement in both places"
        )

    def test_nested_unruled_uid_hashed(self):
        """An unruled UI element nested in a sequence is hashed."""
        from pydicom.sequence import Sequence

        from dicom_dre.uid_utils import hashuid

        item = Dataset()
        item.add_new(Tag(0x0030, 0x0010), "UI", "1.2.840.113619.NESTED.1")  # unruled UI
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x5200, 0x9229), "SQ", Sequence([item]))  # SharedFunctionalGroupsSequence
        self._apply(ds)
        nested = ds[Tag(0x5200, 0x9229)].value[0]
        assert str(nested[Tag(0x0030, 0x0010)].value) == hashuid(
            "1.2.840.4267.32.", "1.2.840.113619.NESTED.1UNKNOWN"
        ), f"nested unruled UID should be hashed, got {nested[Tag(0x0030, 0x0010)].value!r}"

    def test_implicit_vr_uid_decoded_and_hashed(self):
        """An implicit-VR (UN) UID element is decoded via the dictionary VR and hashed."""
        from dicom_dre.uid_utils import hashuid

        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x0008, 0x001A), "UN", b"1.2.840.113619.UNVR.1")  # UI dictionary VR, vendor root
        self._apply(ds)
        elem = ds[Tag(0x0008, 0x001A)]
        assert elem.VR == "UI", "runtime UN should resolve to the dictionary UI VR"
        assert str(elem.value) == hashuid("1.2.840.4267.32.", "1.2.840.113619.UNVR.1UNKNOWN"), (
            f"implicit-VR UID should be decoded and hashed, got {elem.value!r}"
        )

    def test_fallback_disabled_without_uid_root(self):
        """A profile with no UID root leaves unruled UIDs unchanged."""
        ds = Dataset()
        ds.add_new(Tag(0x0030, 0x0010), "UI", "1.2.840.113619.KEEPME")
        profile = _minimal_profile()
        profile.apply(ds, _PARAMS)
        assert str(ds[Tag(0x0030, 0x0010)].value) == "1.2.840.113619.KEEPME", (
            f"UID should be unchanged when the profile has no UID root, got {ds[Tag(0x0030, 0x0010)].value!r}"
        )


class TestBasicProfileTagCoverage:
    """The default profile's tag sets include the PS3.15 Basic Profile additions."""

    def test_phi_remove_additions_present(self):
        """Representative X attributes from each added family are removed."""
        from dicom_dre.profiles.default import PHI_REMOVE_TAGS

        expected = {
            Tag(0x0016, 0x004D),  # Camera Owner Name (EXIF)
            Tag(0x0016, 0x0072),  # GPS Latitude
            Tag(0x0012, 0x0071),  # Clinical Trial Series ID
            Tag(0x300A, 0x0003),  # RT Plan Name
            Tag(0x0040, 0x050A),  # Specimen Accession Number (moved from EMPTY)
            Tag(0x0010, 0x0012),  # Name to Use (2026c)
            Tag(0x0040, 0xB03B),  # Montage Name (2026c)
        }
        missing = expected - PHI_REMOVE_TAGS
        assert not missing, f"PHI_REMOVE_TAGS missing: {missing}"

    def test_empty_additions_present(self):
        """Representative Z attributes are in EMPTY_TAGS."""
        from dicom_dre.profiles.default import EMPTY_TAGS

        expected = {Tag(0x0012, 0x0030), Tag(0x3006, 0x0026), Tag(0x300A, 0x00B2)}
        assert expected <= EMPTY_TAGS, f"EMPTY_TAGS missing: {expected - EMPTY_TAGS}"

    def test_dummy_additions_present_and_graphic_annotation_excluded(self):
        """DUMMY_TAGS holds D attributes but not Graphic Annotation Sequence."""
        from dicom_dre.profiles.default import DUMMY_TAGS

        expected = {Tag(0x0072, 0x0066), Tag(0x300A, 0x0002), Tag(0x0040, 0xB020)}
        assert expected <= DUMMY_TAGS, f"DUMMY_TAGS missing: {expected - DUMMY_TAGS}"
        assert Tag(0x0070, 0x0001) not in DUMMY_TAGS, "Graphic Annotation Sequence must not be cleared as a dummy"

    def test_date_additions_present(self):
        """Representative added dates are jittered (DATE_TAGS)."""
        from dicom_dre.profiles.default import DATE_TAGS

        expected = {Tag(0x0018, 0xA002), Tag(0x3008, 0x0250), Tag(0x0038, 0x0030)}
        assert expected <= DATE_TAGS, f"DATE_TAGS missing: {expected - DATE_TAGS}"

    def test_keep_additions_present(self):
        """Representative time-of-day attributes are kept (KEEP_TAGS)."""
        from dicom_dre.profiles.default import KEEP_TAGS

        expected = {Tag(0x0072, 0x006B), Tag(0x3008, 0x0251)}
        assert expected <= KEEP_TAGS, f"KEEP_TAGS missing: {expected - KEEP_TAGS}"

    def test_uid_additions_present(self):
        """Irradiation Event UID and Table Top Position Alignment UID are hashed."""
        from dicom_dre.profiles.default import UID_TAGS

        assert Tag(0x0008, 0x3010) in UID_TAGS, "Irradiation Event UID should be in UID_TAGS"
        assert Tag(0x300A, 0x0054) in UID_TAGS, "Table Top Position Alignment UID should be in UID_TAGS"


class TestBasicProfileBehavior:
    """The default profile acts on representative leaked attributes."""

    def _apply(self, ds: Dataset) -> Dataset:
        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile

        profile = default_profile(ProfileSettings(hash_salt="pepper"))
        profile.apply(ds, DeidParameters())
        return ds

    def test_exif_and_gps_removed(self):
        """EXIF/GPS attributes are removed."""
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x0016, 0x004D), "UT", "Jane Photographer")  # Camera Owner Name
        ds.add_new(Tag(0x0016, 0x0072), "DS", "37.1")  # GPS Latitude
        self._apply(ds)
        assert Tag(0x0016, 0x004D) not in ds, "Camera Owner Name should be removed"
        assert Tag(0x0016, 0x0072) not in ds, "GPS Latitude should be removed"

    def test_rt_descriptions_removed(self):
        """RT free-text description attributes are removed."""
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x300A, 0x00B2), "SH", "LINAC-7")  # Treatment Machine Name (Z -> empty)
        ds.add_new(Tag(0x3008, 0x0250), "DA", "20200104")  # Treatment Date (jitter)
        self._apply(ds)
        assert str(ds[Tag(0x300A, 0x00B2)].value) == "", "Treatment Machine Name should be emptied"
        assert str(ds[Tag(0x3008, 0x0250)].value) != "20200104", "Treatment Date should be jittered"

    def test_clinical_trial_series_id_removed(self):
        """Clinical Trial Series ID is removed."""
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x0012, 0x0071), "LO", "TRIAL-SERIES-9")
        self._apply(ds)
        assert Tag(0x0012, 0x0071) not in ds, "Clinical Trial Series ID should be removed"

    def test_hanging_protocol_datetime_jittered(self):
        """A DateTime attribute is jittered rather than removed."""
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x0018, 0xA002), "DT", "20200104120000")  # Contribution DateTime
        self._apply(ds)
        assert Tag(0x0018, 0xA002) in ds, "Contribution DateTime should be retained (jittered), not removed"
        assert not str(ds[Tag(0x0018, 0xA002)].value).startswith("20200104"), "Contribution DateTime should be shifted"

    def test_curve_data_removed(self):
        """Curve Data (group 50xx) is removed by remove_curves."""
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x5000, 0x3000), "OW", b"\x00\x01")  # Curve Data
        self._apply(ds)
        assert Tag(0x5000, 0x3000) not in ds, "Curve Data should be removed"

    def test_standard_z_identifiers_deidentified(self):
        """AccessionNumber, PatientName, and PatientBirthDate are de-identified.

        These are Basic Profile Z attributes the default profile handles by
        hashing/jitter rather than emptying, so this asserts the behavior rather
        than membership in a specific tag set.
        """
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x0008, 0x0050), "SH", "ACC-SECRET")  # AccessionNumber (Z -> hashed)
        ds.add_new(Tag(0x0010, 0x0010), "PN", "Doe^John")  # PatientName (Z -> hashed)
        ds.add_new(Tag(0x0010, 0x0030), "DA", "19800101")  # PatientBirthDate (Z -> jittered)
        self._apply(ds)
        assert str(ds[Tag(0x0008, 0x0050)].value) not in ("", "ACC-SECRET"), (
            "AccessionNumber should be hashed, not emptied or left as PHI"
        )
        assert str(ds[Tag(0x0010, 0x0010)].value) not in ("", "Doe^John"), (
            "PatientName should be hashed, not emptied or left as PHI"
        )
        assert str(ds[Tag(0x0010, 0x0030)].value) != "19800101", "PatientBirthDate should be jittered"


class TestDummyForVr:
    """dummy_for_vr produces a VR-valid non-empty dummy (or a cleared value)."""

    def test_dummy_per_vr(self):
        """Text and AS VRs receive fixed VR-valid dummy values."""
        from dicom_dre.actions import dummy_for_vr

        action = dummy_for_vr("1.2.840.4267.32.", use_study_salt=True)
        cases = [
            (Tag(0x0072, 0x0066), "LO", "SECRET"),  # Selector LO Value -> text
            (Tag(0x0072, 0x006A), "PN", "Doe^Jane"),  # Selector PN Value -> text
            (Tag(0x0072, 0x005F), "AS", "045Y"),  # Selector AS Value -> 000Y
            (Tag(0x3010, 0x001B), "UC", "device-serial"),  # Device Alternate Identifier -> text
        ]
        ds = Dataset()
        for tag, vr, value in cases:
            ds.add_new(tag, vr, value)
        for tag, _vr, _value in cases:
            action(ds, tag, DeidParameters())
        assert str(ds[Tag(0x0072, 0x0066)].value) == "ANONYMIZED", "Selector LO Value dummy should be ANONYMIZED"
        assert str(ds[Tag(0x0072, 0x006A)].value) == "ANONYMIZED", "Selector PN Value dummy should be ANONYMIZED"
        assert str(ds[Tag(0x0072, 0x005F)].value) == "000Y", "Selector AS Value dummy should be 000Y"
        assert str(ds[Tag(0x3010, 0x001B)].value) == "ANONYMIZED", (
            "Device Alternate Identifier (UC) dummy should be ANONYMIZED"
        )

    def test_dummy_numeric_and_sequence_and_bytes(self):
        """Numeric VRs become \"0\"; SQ and OB values are cleared."""
        from pydicom.sequence import Sequence

        from dicom_dre.actions import dummy_for_vr

        action = dummy_for_vr("1.2.840.4267.32.")
        ds = Dataset()
        ds.add_new(Tag(0x0016, 0x008E), "IS", "5")  # GPS Differential (numeric)
        ds.add_new(Tag(0x0034, 0x0001), "SQ", Sequence([Dataset()]))  # Flow Identifier Sequence
        ds.add_new(Tag(0x0034, 0x0002), "OB", b"secret-bytes")  # Flow Identifier (OB)
        action(ds, Tag(0x0016, 0x008E), DeidParameters())
        action(ds, Tag(0x0034, 0x0001), DeidParameters())
        action(ds, Tag(0x0034, 0x0002), DeidParameters())
        assert str(ds[Tag(0x0016, 0x008E)].value) == "0", "GPS Differential (IS) dummy should be 0"
        assert list(ds[Tag(0x0034, 0x0001)].value) == [], "SQ dummy should be an empty sequence"
        assert ds[Tag(0x0034, 0x0002)].value in (b"", None), "OB dummy should be cleared"

    def test_dummy_ui_hashed(self):
        """A UI dummy is hashed via the profile UID policy."""
        from dicom_dre.actions import dummy_for_vr
        from dicom_dre.uid_utils import hashuid

        action = dummy_for_vr("1.2.840.4267.32.", use_study_salt=True)
        ds = Dataset()
        ds.add_new(Tag(0x0040, 0xA124), "UI", "1.2.3.4.5")  # UID (D)
        action(ds, Tag(0x0040, 0xA124), DeidParameters())
        assert str(ds[Tag(0x0040, 0xA124)].value) == hashuid("1.2.840.4267.32.", "1.2.3.4.5UNKNOWN"), (
            "UI dummy should be the study-salted hash of the original UID"
        )

    def test_dummy_present_only(self):
        """An absent element is left uncreated."""
        from dicom_dre.actions import dummy_for_vr

        action = dummy_for_vr("1.2.840.4267.32.")
        ds = Dataset()
        action(ds, Tag(0x0072, 0x0066), DeidParameters())
        assert Tag(0x0072, 0x0066) not in ds, "dummy_for_vr must not create absent elements"

    def test_dummy_values_are_writable(self):
        """UN and binary-numeric dummies serialize (write as bytes / numbers)."""
        import io

        import pydicom
        from pydicom.dataset import FileMetaDataset
        from pydicom.uid import ExplicitVRLittleEndian
        from pydicom.uid import SecondaryCaptureImageStorage
        from pydicom.uid import generate_uid

        from dicom_dre.actions import dummy_for_vr

        action = dummy_for_vr("1.2.840.4267.32.")
        ds = Dataset()
        ds.add_new(Tag(0x0072, 0x006D), "UN", b"secret")  # Selector UN Value
        ds.add_new(Tag(0x0072, 0x0072), "US", 5)  # Selector US Value
        ds.add_new(Tag(0x0072, 0x0074), "FD", 1.5)  # Selector FD Value
        for tag in (Tag(0x0072, 0x006D), Tag(0x0072, 0x0072), Tag(0x0072, 0x0074)):
            action(ds, tag, DeidParameters())
        assert ds[Tag(0x0072, 0x006D)].value == b"ANONYMIZED", "UN dummy should be bytes"
        assert ds[Tag(0x0072, 0x0072)].value == 0, "US dummy should be an int"
        assert ds[Tag(0x0072, 0x0074)].value == 0.0, "FD dummy should be a float"

        ds.add_new(Tag(0x0008, 0x0016), "UI", SecondaryCaptureImageStorage)
        ds.add_new(Tag(0x0008, 0x0018), "UI", generate_uid())
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
        file_meta.MediaStorageSOPInstanceUID = ds[Tag(0x0008, 0x0018)].value
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta = file_meta
        buffer = io.BytesIO()
        ds.save_as(buffer, enforce_file_format=True)
        buffer.seek(0)
        reread = pydicom.dcmread(buffer, force=True)
        assert reread[Tag(0x0072, 0x006D)].value == b"ANONYMIZED", "UN dummy should round-trip"


class TestMethodCodeSequenceContents:
    """(0012,0064) contents reflect the profile's declared options and dates."""

    TAG = Tag(0x0012, 0x0064)

    def _codes(self, ds: Dataset) -> set[str]:
        return {str(item[Tag(0x0008, 0x0100)].value) for item in ds[self.TAG].value}

    def _minimal_ds(self) -> Dataset:
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        return ds

    def test_default_profile_codes(self):
        """Default emits 113100, 113105, 113107, 113108; not 113106/113111."""
        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile

        ds = self._minimal_ds()
        default_profile(ProfileSettings(hash_salt="pepper")).apply(ds, DeidParameters())
        codes = self._codes(ds)
        assert {"113100", "113105", "113107", "113108"} <= codes, f"missing codes: {codes}"
        assert "113106" not in codes, f"113106 should be absent for modified dates: {codes}"
        assert "113111" not in codes, f"113111 should be absent without preserved specs: {codes}"

    def test_private_preserving_adds_retain_safe_private(self):
        """A profile with preserved private specs emits 113111."""
        profile = _minimal_profile(
            emits_basic_profile=True,
            modifies_dates=True,
            remove_private=True,
            preserved_private_specs=frozenset({_GEMS_ACQU_SPEC}),
        )
        ds = _signa_premier_dataset(block=0x10)
        profile.apply(ds, _PARAMS)
        assert "113111" in self._codes(ds), "113111 should be emitted when private specs are preserved"

    def test_lds_full_dates_code(self):
        """An LDS-style profile (preserve_dates) emits 113106, not 113107."""
        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.lds import lds_profile

        ds = self._minimal_ds()
        lds_profile(ProfileSettings(hash_salt="pepper")).apply(ds, DeidParameters())
        codes = self._codes(ds)
        assert "113106" in codes, f"113106 (full dates) should be emitted for LDS: {codes}"
        assert "113107" not in codes, f"113107 should be absent for LDS: {codes}"

    def test_emits_basic_profile_false_omits_113100(self):
        """A profile with emits_basic_profile=False does not emit 113100."""
        profile = _minimal_profile(emits_basic_profile=False, deid_options=frozenset({"113105"}))
        ds = self._minimal_ds()
        profile.apply(ds, _PARAMS)
        codes = self._codes(ds)
        assert "113100" not in codes, f"113100 should be absent when emits_basic_profile is False: {codes}"
        assert "113105" in codes, f"declared option 113105 should be emitted: {codes}"

    def test_applied_options_merged_into_sequence(self):
        """apply(applied_options=...) adds per-instance codes alongside deid_options."""
        profile = _minimal_profile(emits_basic_profile=True, deid_options=frozenset({"113105"}))
        ds = self._minimal_ds()
        profile.apply(ds, _PARAMS, applied_options=frozenset({"113101"}))
        codes = self._codes(ds)
        assert {"113100", "113105", "113101"} <= codes, f"applied option not merged: {codes}"


class TestBasicProfileDivergences:
    """The three recorded intentional deviations behave as specified."""

    def _apply(self, ds: Dataset) -> Dataset:
        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile

        default_profile(ProfileSettings(hash_salt="pepper")).apply(ds, DeidParameters())
        return ds

    def test_patient_sex_and_contrast_agent_survive(self):
        """Patient's Sex and Contrast/Bolus Agent are kept unchanged."""
        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x0010, 0x0040), "CS", "F")  # PatientSex
        ds.add_new(Tag(0x0018, 0x0010), "LO", "GADOLINIUM")  # ContrastBolusAgent
        self._apply(ds)
        assert str(ds[Tag(0x0010, 0x0040)].value) == "F", "Patient's Sex should be kept unchanged"
        assert str(ds[Tag(0x0018, 0x0010)].value) == "GADOLINIUM", "Contrast/Bolus Agent should be kept unchanged"

    def test_irradiation_event_uid_hashed(self):
        """Irradiation Event UID is hashed, not removed."""
        from dicom_dre.uid_utils import hashuid

        ds = Dataset()
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN1")
        ds.add_new(Tag(0x0008, 0x3010), "UI", "1.2.840.113619.EVENT.1")
        self._apply(ds)
        assert Tag(0x0008, 0x3010) in ds, "Irradiation Event UID should be retained"
        assert str(ds[Tag(0x0008, 0x3010)].value) == hashuid("1.2.840.4267.32.", "1.2.840.113619.EVENT.1UNKNOWN"), (
            "Irradiation Event UID should be hashed, not removed"
        )


class TestTagSetInvariants:
    """Structural invariants over the default profile's rule tag sets."""

    def _sets(self) -> dict:
        from dicom_dre.profiles import default as d

        return {
            "PHI_REMOVE_TAGS": d.PHI_REMOVE_TAGS,
            "KEEP_TAGS": d.KEEP_TAGS,
            "EMPTY_TAGS": d.EMPTY_TAGS,
            "UID_TAGS": d.UID_TAGS,
            "DATE_TAGS": d.DATE_TAGS,
            "DUMMY_TAGS": d.DUMMY_TAGS,
        }

    def test_rule_families_are_disjoint(self):
        """No tag appears in two rule families, so its handling is unambiguous."""
        from itertools import combinations

        sets = self._sets()
        for (name_a, set_a), (name_b, set_b) in combinations(sets.items(), 2):
            overlap = set_a & set_b
            assert not overlap, f"{name_a} and {name_b} overlap: {sorted(str(t) for t in overlap)}"

    def test_uid_tags_have_ui_vr(self):
        """Every UID_TAGS entry is a UI element, catching a tag pasted into the wrong set."""
        from pydicom.datadict import dictionary_VR

        from dicom_dre.profiles.default import UID_TAGS

        wrong = {str(t): dictionary_VR(t) for t in UID_TAGS if dictionary_VR(t) != "UI"}
        assert not wrong, f"UID_TAGS entries with non-UI VR: {wrong}"

    def test_date_tags_have_date_vr(self):
        """Every DATE_TAGS entry is a DA or DT element."""
        from pydicom.datadict import dictionary_VR

        from dicom_dre.profiles.default import DATE_TAGS

        wrong = {str(t): dictionary_VR(t) for t in DATE_TAGS if dictionary_VR(t) not in ("DA", "DT")}
        assert not wrong, f"DATE_TAGS entries with non-DA/DT VR: {wrong}"

    def test_no_duplicate_tag_literals(self):
        """Each frozenset literal has no duplicate Tag(...) entries.

        frozenset silently dedupes, so a duplicated literal reduces coverage with
        no error. Parsing the source catches that at the literal level, which a
        runtime membership check cannot.
        """
        import ast
        import pathlib
        from collections import Counter

        from dicom_dre.profiles import default as d

        tree = ast.parse(pathlib.Path(d.__file__).read_text())
        targets = set(self._sets())
        checked = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                name, value = node.target.id, node.value
            else:
                continue
            if name not in targets:
                continue
            tags = [
                (sub.args[0].value, sub.args[1].value)
                for sub in ast.walk(value)
                if isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "Tag"
                and len(sub.args) == 2
                and isinstance(sub.args[0], ast.Constant)
                and isinstance(sub.args[1], ast.Constant)
            ]
            dupes = sorted(f"{g:04X},{e:04X}" for (g, e), count in Counter(tags).items() if count > 1)
            assert not dupes, f"{name} has duplicate Tag literals: {dupes}"
            checked.add(name)
        assert checked == targets, f"did not scan all sets; missing {targets - checked}"


class TestKeyObjectSelectionProfile:
    """Default profile retention and cleaning of Key Object Selection content."""

    _ORIG_SOP_INSTANCE = "1.2.826.0.1.3680043.REF.9001"
    _ORIG_SERIES = "1.2.826.0.1.3680043.SER.9002"
    _ORIG_STUDY = "1.2.826.0.1.3680043.STU.9003"
    _ORIG_IDENTICAL_STUDY = "1.2.826.0.1.3680043.IDS.9101"
    _ORIG_IDENTICAL_SERIES = "1.2.826.0.1.3680043.IDS.9102"
    _ORIG_IDENTICAL_SOP = "1.2.826.0.1.3680043.IDS.9103"
    _STUDY_ID = "STUDY_KO"

    def _ko_dataset(self) -> Dataset:
        """Build a synthetic KO dataset with content, evidence, and PHI."""
        from pydicom.sequence import Sequence

        ds = Dataset()
        ds.add_new(Tag(0x0008, 0x0060), "CS", "KO")  # Modality
        ds.add_new(Tag(0x0008, 0x0016), "UI", "1.2.840.10008.5.1.4.1.1.88.59")  # SOPClassUID
        ds.add_new(Tag(0x0008, 0x0018), "UI", "1.2.826.0.1.3680043.KO.1")  # SOPInstanceUID
        ds.add_new(Tag(0x0010, 0x0010), "PN", "DOE^JANE")  # PatientName
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN-KO-1")  # PatientID
        ds.add_new(Tag(0x0008, 0x0050), "SH", "ACC-KO-1")  # AccessionNumber
        ds.add_new(Tag(0x0008, 0x0090), "PN", "REFER^DOC")  # ReferringPhysicianName
        ds.add_new(Tag(0x0008, 0x0080), "LO", "SOME HOSPITAL")  # InstitutionName
        ds.add_new(Tag(0x0008, 0x1010), "SH", "STATION-7")  # StationName
        ds.add_new(Tag(0x0020, 0x000D), "UI", self._ORIG_STUDY)  # StudyInstanceUID

        # Document Title: Concept Name Code Sequence (0040,A043)
        title = Dataset()
        title.add_new(Tag(0x0008, 0x0100), "SH", "113000")  # CodeValue
        title.add_new(Tag(0x0008, 0x0102), "SH", "DCM")  # CodingSchemeDesignator
        title.add_new(Tag(0x0008, 0x0104), "LO", "Of Interest")  # CodeMeaning
        ds.add_new(Tag(0x0040, 0xA043), "SQ", Sequence([title]))

        # Anatomic Region Sequence (0008,2218) coded label
        region = Dataset()
        region.add_new(Tag(0x0008, 0x0100), "SH", "T-A0100")
        region.add_new(Tag(0x0008, 0x0102), "SH", "SRT")
        region.add_new(Tag(0x0008, 0x0104), "LO", "Brain")
        ds.add_new(Tag(0x0008, 0x2218), "SQ", Sequence([region]))

        # Current Requested Procedure Evidence Sequence -> Series -> SOP
        sop_item = Dataset()
        sop_item.add_new(Tag(0x0008, 0x1150), "UI", "1.2.840.10008.5.1.4.1.1.2")  # RefSOPClassUID
        sop_item.add_new(Tag(0x0008, 0x1155), "UI", self._ORIG_SOP_INSTANCE)  # RefSOPInstanceUID
        series_item = Dataset()
        series_item.add_new(Tag(0x0020, 0x000E), "UI", self._ORIG_SERIES)  # SeriesInstanceUID
        series_item.add_new(Tag(0x0008, 0x1199), "SQ", Sequence([sop_item]))  # RefSOPSequence
        study_item = Dataset()
        study_item.add_new(Tag(0x0020, 0x000D), "UI", self._ORIG_STUDY)  # StudyInstanceUID
        study_item.add_new(Tag(0x0008, 0x1115), "SQ", Sequence([series_item]))  # RefSeriesSequence
        ds.add_new(Tag(0x0040, 0xA375), "SQ", Sequence([study_item]))  # EvidenceSequence

        # Content Sequence: a TEXT item with free-text and an IMAGE item.
        text_item = Dataset()
        text_item.add_new(Tag(0x0040, 0xA040), "CS", "TEXT")  # ValueType
        text_item.add_new(Tag(0x0040, 0xA160), "UT", "Malignant lesion noted by Dr Smith")  # TextValue
        image_sop = Dataset()
        image_sop.add_new(Tag(0x0008, 0x1150), "UI", "1.2.840.10008.5.1.4.1.1.2")
        image_sop.add_new(Tag(0x0008, 0x1155), "UI", self._ORIG_SOP_INSTANCE)
        image_item = Dataset()
        image_item.add_new(Tag(0x0040, 0xA040), "CS", "IMAGE")  # ValueType
        image_item.add_new(Tag(0x0008, 0x1199), "SQ", Sequence([image_sop]))  # RefSOPSequence
        ds.add_new(Tag(0x0040, 0xA730), "SQ", Sequence([text_item, image_item]))  # ContentSequence

        # Identical Documents Sequence (0040,A525) with nested Study/Series/SOP UIDs
        ids_sop = Dataset()
        ids_sop.add_new(Tag(0x0008, 0x1150), "UI", "1.2.840.10008.5.1.4.1.1.88.59")
        ids_sop.add_new(Tag(0x0008, 0x1155), "UI", self._ORIG_IDENTICAL_SOP)
        ids_series = Dataset()
        ids_series.add_new(Tag(0x0020, 0x000E), "UI", self._ORIG_IDENTICAL_SERIES)
        ids_series.add_new(Tag(0x0008, 0x1199), "SQ", Sequence([ids_sop]))
        ids_study = Dataset()
        ids_study.add_new(Tag(0x0020, 0x000D), "UI", self._ORIG_IDENTICAL_STUDY)
        ids_study.add_new(Tag(0x0008, 0x1115), "SQ", Sequence([ids_series]))
        ds.add_new(Tag(0x0040, 0xA525), "SQ", Sequence([ids_study]))  # IdenticalDocumentsSequence

        # Referenced Request Sequence with a nested Issuer of Accession Number
        # Sequence and free-text order/procedure members.
        issuer = Dataset()
        issuer.add_new(Tag(0x0040, 0x0031), "UT", "SITE-A")  # LocalNamespaceEntityID
        request_item = Dataset()
        request_item.add_new(Tag(0x0008, 0x0050), "SH", "ACC-KO-1")  # AccessionNumber
        request_item.add_new(Tag(0x0040, 0x1001), "SH", "RP-0001")  # RequestedProcedureID
        request_item.add_new(Tag(0x0032, 0x1060), "LO", "MRI BRAIN W CONTRAST")  # RequestedProcedureDescription
        request_item.add_new(Tag(0x0008, 0x0051), "SQ", Sequence([issuer]))  # IssuerOfAccessionNumberSeq
        ds.add_new(Tag(0x0040, 0xA370), "SQ", Sequence([request_item]))  # RefRequestSequence

        # Private group, removed by remove_private=True.
        ds.add_new(Tag(0x0009, 0x0010), "LO", "ACME PRIVATE")  # PrivateCreator
        ds.add_new(Tag(0x0009, 0x1001), "LO", "PRIVATE-PHI-VALUE")  # private element
        return ds

    def _apply(self, ds: Dataset) -> None:
        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.default import default_profile

        default_profile(ProfileSettings(hash_salt="pepper")).apply(ds, DeidParameters(study_id=self._STUDY_ID))

    def _expected_uid(self, original: str) -> str:
        from dicom_dre.uid_utils import hashuid

        return hashuid("1.2.840.4267.32.", original + self._STUDY_ID)

    def test_content_sequence_retained(self):
        """Content Sequence is retained after de-identification."""
        ds = self._ko_dataset()
        self._apply(ds)
        assert Tag(0x0040, 0xA730) in ds, "Content Sequence should be retained"

    def test_referenced_uids_hashed_to_pipeline_value(self):
        """Referenced SOP/Series/Study UIDs hash to the study-scoped pipeline value."""
        ds = self._ko_dataset()
        self._apply(ds)
        study_item = ds[Tag(0x0040, 0xA375)].value[0]
        series_item = study_item[Tag(0x0008, 0x1115)].value[0]
        sop_item = series_item[Tag(0x0008, 0x1199)].value[0]
        assert str(sop_item[Tag(0x0008, 0x1155)].value) == self._expected_uid(self._ORIG_SOP_INSTANCE), (
            "Referenced SOP Instance UID should equal the study-scoped hash"
        )
        assert str(series_item[Tag(0x0020, 0x000E)].value) == self._expected_uid(self._ORIG_SERIES), (
            "Series Instance UID should equal the study-scoped hash"
        )
        assert str(study_item[Tag(0x0020, 0x000D)].value) == self._expected_uid(self._ORIG_STUDY), (
            "Study Instance UID should equal the study-scoped hash"
        )

    def test_no_original_uid_survives(self):
        """No original referenced UID survives anywhere in the output tree."""
        ds = self._ko_dataset()
        self._apply(ds)
        values = _all_string_values(ds)
        for original in (self._ORIG_SOP_INSTANCE, self._ORIG_SERIES, self._ORIG_STUDY):
            assert original not in values, f"original UID {original} should not survive in output"

    def test_text_value_redacted(self):
        """Text Value free text is redacted against the allowlist."""
        ds = self._ko_dataset()
        self._apply(ds)
        text_item = ds[Tag(0x0040, 0xA730)].value[0]
        redacted = str(text_item[Tag(0x0040, 0xA160)].value)
        assert "Smith" not in redacted, f"operator name should be redacted from Text Value: {redacted!r}"

    def test_document_title_retained(self):
        """The Concept Name Code Sequence document title is retained unchanged."""
        ds = self._ko_dataset()
        self._apply(ds)
        title = ds[Tag(0x0040, 0xA043)].value[0]
        assert str(title[Tag(0x0008, 0x0100)].value) == "113000", "code value should be retained"
        assert str(title[Tag(0x0008, 0x0102)].value) == "DCM", "coding scheme designator should be retained"
        assert str(title[Tag(0x0008, 0x0104)].value) == "Of Interest", "code meaning should be retained"

    def test_anatomic_region_sequence_retained(self):
        """Anatomic Region Sequence coded label is retained."""
        ds = self._ko_dataset()
        self._apply(ds)
        assert Tag(0x0008, 0x2218) in ds, "Anatomic Region Sequence should be retained"
        region = ds[Tag(0x0008, 0x2218)].value[0]
        assert str(region[Tag(0x0008, 0x0104)].value) == "Brain", "coded anatomy meaning should be retained"

    def test_issuer_of_accession_number_sequence_removed(self):
        """Issuer of Accession Number Sequence nested in a retained sequence is removed."""
        ds = self._ko_dataset()
        self._apply(ds)
        request_item = ds[Tag(0x0040, 0xA370)].value[0]
        assert Tag(0x0008, 0x0051) not in request_item, "Issuer of Accession Number Sequence should be removed"

    def test_identity_elements_deidentified(self):
        """Patient, physician, institution, and station identity elements are de-identified."""
        ds = self._ko_dataset()
        self._apply(ds)
        assert str(ds[Tag(0x0010, 0x0020)].value) != "MRN-KO-1", "PatientID should be hashed"
        assert str(ds[Tag(0x0010, 0x0010)].value) != "DOE^JANE", "PatientName should be hashed"
        assert Tag(0x0008, 0x0080) not in ds, "InstitutionName should be removed"
        assert Tag(0x0008, 0x1010) not in ds, "StationName should be removed"

    def test_clean_structured_content_option_emitted(self):
        """The De-identification Method Code Sequence includes 113104."""
        ds = self._ko_dataset()
        self._apply(ds)
        codes = {str(item[Tag(0x0008, 0x0100)].value) for item in ds[Tag(0x0012, 0x0064)].value}
        assert "113104" in codes, f"Clean Structured Content Option should be emitted: {codes}"

    def test_identical_documents_sequence_retained_and_hashed(self):
        """Identical Documents Sequence is retained with nested UIDs hashed."""
        ds = self._ko_dataset()
        self._apply(ds)
        assert Tag(0x0040, 0xA525) in ds, "Identical Documents Sequence should be retained"
        study_item = ds[Tag(0x0040, 0xA525)].value[0]
        series_item = study_item[Tag(0x0008, 0x1115)].value[0]
        sop_item = series_item[Tag(0x0008, 0x1199)].value[0]
        assert str(study_item[Tag(0x0020, 0x000D)].value) == self._expected_uid(self._ORIG_IDENTICAL_STUDY), (
            "Identical Documents Study Instance UID should be study-scoped hashed"
        )
        assert str(series_item[Tag(0x0020, 0x000E)].value) == self._expected_uid(self._ORIG_IDENTICAL_SERIES), (
            "Identical Documents Series Instance UID should be study-scoped hashed"
        )
        assert str(sop_item[Tag(0x0008, 0x1155)].value) == self._expected_uid(self._ORIG_IDENTICAL_SOP), (
            "Identical Documents Referenced SOP Instance UID should be study-scoped hashed"
        )
        values = _all_string_values(ds)
        for original in (self._ORIG_IDENTICAL_STUDY, self._ORIG_IDENTICAL_SERIES, self._ORIG_IDENTICAL_SOP):
            assert original not in values, f"original identical-documents UID {original} should not survive"

    def test_referenced_request_sequence_accession_hashed_and_free_text_removed(self):
        """Referenced Request Sequence keeps a hashed accession and drops free-text members."""
        ds = self._ko_dataset()
        self._apply(ds)
        request_item = ds[Tag(0x0040, 0xA370)].value[0]
        assert str(request_item[Tag(0x0008, 0x0050)].value) != "ACC-KO-1", "nested Accession Number should be hashed"
        assert Tag(0x0032, 0x1060) not in request_item, "Requested Procedure Description should be removed"
        assert Tag(0x0040, 0x1001) not in request_item, "Requested Procedure ID should be removed"

    def test_private_group_removed(self):
        """Private group elements are removed by the default profile."""
        ds = self._ko_dataset()
        self._apply(ds)
        assert Tag(0x0009, 0x0010) not in ds, "private creator should be removed"
        assert Tag(0x0009, 0x1001) not in ds, "private element should be removed"
        assert "PRIVATE-PHI-VALUE" not in _all_string_values(ds), "private value should not survive"

    def test_brainlab_private_scheme_title_retained(self):
        """A document title using a private coding scheme is retained verbatim."""
        from pydicom.sequence import Sequence

        ds = self._ko_dataset()
        title = Dataset()
        title.add_new(Tag(0x0008, 0x0100), "SH", "Plan")  # CodeValue
        title.add_new(Tag(0x0008, 0x0102), "SH", "BL-S17-1")  # CodingSchemeDesignator
        title.add_new(Tag(0x0008, 0x0104), "LO", "Plan")  # CodeMeaning
        ds[Tag(0x0040, 0xA043)].value = Sequence([title])
        self._apply(ds)
        retained = ds[Tag(0x0040, 0xA043)].value[0]
        assert str(retained[Tag(0x0008, 0x0100)].value) == "Plan", "private-scheme code value should be retained"
        assert str(retained[Tag(0x0008, 0x0102)].value) == "BL-S17-1", "private coding scheme should be retained"


class TestStrictContentRetention:
    """strict_profile retains and cleans KO/PR label subtrees.

    remove_unspecified is disabled below the content-root sequences, so the
    labels survive while the shared PHI, date, and free-text rules de-identify
    every element inside them. UIDs are hashed without the study salt.
    """

    _ORIG_SOP = "1.2.826.0.1.3680043.SOP.1"
    _ORIG_SERIES = "1.2.826.0.1.3680043.SERIES.1"
    _ORIG_STUDY = "1.2.826.0.1.3680043.STUDY.1"

    def _apply(self, ds: Dataset) -> None:
        from dicom_dre.profiles.config import ProfileSettings
        from dicom_dre.profiles.strict import strict_profile

        strict_profile(ProfileSettings(hash_salt="pepper")).apply(ds, DeidParameters(study_id="COHORT_A"))

    def _ko_dataset(self) -> Dataset:
        from pydicom.sequence import Sequence

        ds = Dataset()
        ds.add_new(Tag(0x0008, 0x0060), "CS", "KO")  # Modality
        ds.add_new(Tag(0x0008, 0x0016), "UI", "1.2.840.10008.5.1.4.1.1.88.59")  # SOPClassUID
        ds.add_new(Tag(0x0008, 0x0018), "UI", "1.2.826.0.1.3680043.KO.1")  # SOPInstanceUID
        ds.add_new(Tag(0x0010, 0x0010), "PN", "DOE^JANE")  # PatientName
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN-KO-1")  # PatientID
        ds.add_new(Tag(0x0020, 0x000D), "UI", self._ORIG_STUDY)  # StudyInstanceUID

        title = Dataset()
        title.add_new(Tag(0x0008, 0x0100), "SH", "113000")  # CodeValue
        title.add_new(Tag(0x0008, 0x0102), "SH", "DCM")  # CodingSchemeDesignator
        title.add_new(Tag(0x0008, 0x0104), "LO", "Of Interest")  # CodeMeaning
        ds.add_new(Tag(0x0040, 0xA043), "SQ", Sequence([title]))  # ConceptNameCodeSequence

        sop_item = Dataset()
        sop_item.add_new(Tag(0x0008, 0x1150), "UI", "1.2.840.10008.5.1.4.1.1.2")  # RefSOPClassUID
        sop_item.add_new(Tag(0x0008, 0x1155), "UI", self._ORIG_SOP)  # RefSOPInstanceUID
        series_item = Dataset()
        series_item.add_new(Tag(0x0020, 0x000E), "UI", self._ORIG_SERIES)  # SeriesInstanceUID
        series_item.add_new(Tag(0x0008, 0x1199), "SQ", Sequence([sop_item]))  # RefSOPSequence
        study_item = Dataset()
        study_item.add_new(Tag(0x0020, 0x000D), "UI", self._ORIG_STUDY)  # StudyInstanceUID
        study_item.add_new(Tag(0x0008, 0x1115), "SQ", Sequence([series_item]))  # RefSeriesSequence
        ds.add_new(Tag(0x0040, 0xA375), "SQ", Sequence([study_item]))  # EvidenceSequence

        text_item = Dataset()
        text_item.add_new(Tag(0x0040, 0xA040), "CS", "TEXT")  # ValueType
        text_item.add_new(Tag(0x0040, 0xA160), "UT", "Key Image")  # TextValue
        text_item.add_new(Tag(0x0040, 0xA123), "PN", "SMITH^JOHN")  # PersonName (PHI)
        text_item.add_new(Tag(0x0040, 0xA032), "DT", "20240101120000")  # ObservationDateTime (PHI)
        image_sop = Dataset()
        image_sop.add_new(Tag(0x0008, 0x1150), "UI", "1.2.840.10008.5.1.4.1.1.2")
        image_sop.add_new(Tag(0x0008, 0x1155), "UI", self._ORIG_SOP)
        image_item = Dataset()
        image_item.add_new(Tag(0x0040, 0xA040), "CS", "IMAGE")
        image_item.add_new(Tag(0x0008, 0x1199), "SQ", Sequence([image_sop]))
        ds.add_new(Tag(0x0040, 0xA730), "SQ", Sequence([text_item, image_item]))  # ContentSequence

        ds.add_new(Tag(0x0009, 0x0010), "LO", "ACME PRIVATE")  # PrivateCreator
        ds.add_new(Tag(0x0009, 0x1001), "LO", "PRIVATE-PHI-VALUE")  # private element
        return ds

    def _gsps_dataset(self) -> Dataset:
        from pydicom.sequence import Sequence

        text_item = Dataset()
        text_item.add_new(Tag(0x0070, 0x0006), "ST", "Margin ZZQXPHITEXT lesion")  # UnformattedTextValue
        graphic_item = Dataset()
        graphic_item.add_new(Tag(0x0070, 0x0023), "CS", "POLYLINE")  # GraphicType
        graphic_item.add_new(Tag(0x0070, 0x0022), "FL", [1.0, 2.0, 3.0, 4.0])  # GraphicData
        graphic_item.add_new(Tag(0x0062, 0x0020), "UT", "track-secret-XYZ")  # TrackingID
        graphic_item.add_new(Tag(0x0062, 0x0021), "UI", "1.9.8.7.6.5.4.3.2.1")  # TrackingUID
        annotation_item = Dataset()
        annotation_item.add_new(Tag(0x0020, 0x000E), "UI", self._ORIG_SERIES)  # SeriesInstanceUID
        annotation_item.add_new(Tag(0x0070, 0x0008), "SQ", Sequence([text_item]))  # TextObjectSequence
        annotation_item.add_new(Tag(0x0070, 0x0009), "SQ", Sequence([graphic_item]))  # GraphicObjectSequence
        ds = Dataset()
        ds.add_new(Tag(0x0008, 0x0016), "UI", "1.2.840.10008.5.1.4.1.1.11.1")  # SOPClassUID
        ds.add_new(Tag(0x0008, 0x0018), "UI", "1.2.826.0.1.3680043.PR.1")  # SOPInstanceUID
        ds.add_new(Tag(0x0008, 0x0060), "CS", "PR")  # Modality
        ds.add_new(Tag(0x0010, 0x0020), "LO", "MRN123")  # PatientID
        ds.add_new(Tag(0x0070, 0x0001), "SQ", Sequence([annotation_item]))  # GraphicAnnotationSequence
        return ds

    def _no_salt_uid(self, original: str) -> str:
        from dicom_dre.uid_utils import hashuid

        return hashuid("1.2.840.4267.32.", original)

    def test_ko_content_and_label_retained(self):
        """Content Sequence, Evidence Sequence, and the coded title survive."""
        ds = self._ko_dataset()
        self._apply(ds)
        assert Tag(0x0040, 0xA730) in ds, "Content Sequence should be retained"
        assert Tag(0x0040, 0xA375) in ds, "Evidence Sequence should be retained"
        title = ds[Tag(0x0040, 0xA043)].value[0]
        assert str(title[Tag(0x0008, 0x0100)].value) == "113000", "document title code value retained"
        assert str(title[Tag(0x0008, 0x0104)].value) == "Of Interest", "document title meaning retained"

    def test_ko_phi_inside_content_removed(self):
        """PersonName, ObservationDateTime, and private data do not survive."""
        ds = self._ko_dataset()
        self._apply(ds)
        values = _all_string_values(ds)
        assert "SMITH^JOHN" not in values, "PersonName in content should be removed"
        assert "20240101120000" not in values, "ObservationDateTime in content should be removed"
        assert "PRIVATE-PHI-VALUE" not in values, "private value should not survive"

    def test_ko_referenced_uids_hashed_without_salt(self):
        """Referenced UIDs are hashed with the no-salt strict function."""
        ds = self._ko_dataset()
        self._apply(ds)
        values = _all_string_values(ds)
        assert self._ORIG_SOP not in values, "original referenced SOP UID should not survive"
        study_item = ds[Tag(0x0040, 0xA375)].value[0]
        series_item = study_item[Tag(0x0008, 0x1115)].value[0]
        sop_item = series_item[Tag(0x0008, 0x1199)].value[0]
        assert str(sop_item[Tag(0x0008, 0x1155)].value) == self._no_salt_uid(self._ORIG_SOP), (
            "referenced SOP UID should equal the no-salt hash"
        )

    def test_gsps_annotation_retained_and_cleaned(self):
        """Graphic Annotation Sequence survives and its identifiers are hashed."""
        ds = self._gsps_dataset()
        self._apply(ds)
        assert Tag(0x0070, 0x0001) in ds, "GraphicAnnotationSequence should be retained"
        values = _all_string_values(ds)
        for leaked in ("1.9.8.7.6.5.4.3.2.1", self._ORIG_SERIES, "track-secret-XYZ"):
            assert leaked not in values, f"{leaked} should not survive"
        item = ds[Tag(0x0070, 0x0001)].value[0]
        graphic = item[Tag(0x0070, 0x0009)].value[0]
        assert str(graphic[Tag(0x0070, 0x0023)].value) == "POLYLINE", "GraphicType should be retained"
        assert list(graphic[Tag(0x0070, 0x0022)].value) == [1.0, 2.0, 3.0, 4.0], "GraphicData should be retained"

    def test_method_code_sequence_declares_clean_options(self):
        """The method code sequence declares Clean Graphics and Clean Structured Content."""
        ds = self._ko_dataset()
        self._apply(ds)
        codes = {str(item[Tag(0x0008, 0x0100)].value) for item in ds[Tag(0x0012, 0x0064)].value}
        assert "113103" in codes, "Clean Graphics Option should be declared"
        assert "113104" in codes, "Clean Structured Content Option should be declared"
