"""DeidProfile dataclass and apply() logic."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import TYPE_CHECKING

from pydicom.datadict import dictionary_VR
from pydicom.errors import BytesLengthException
from pydicom.tag import BaseTag
from pydicom.tag import Tag


if TYPE_CHECKING:
    from pydicom.dataset import Dataset

    from dicom_dre.actions import TagAction
    from dicom_dre.catalog import PrivateTagSpec

# File Meta Information group is always preserved.
_PRESERVED_GROUPS: frozenset[int] = frozenset({0x0002})

# These groups and tags are unconditionally protected from global removal,
# regardless of whether an explicit rule exists. Without this,
# remove_unspecified=True creates invalid DICOM files missing image-critical
# elements (pixel data description and the identifying UIDs).
_PROTECTED_GROUPS: frozenset[int] = frozenset({0x0028, 0x7FE0})
_PROTECTED_TAGS: frozenset[BaseTag] = frozenset(
    {
        Tag(0x0008, 0x0016),  # SOPClassUID
        Tag(0x0008, 0x0018),  # SOPInstanceUID
        Tag(0x0020, 0x000D),  # StudyInstanceUID
    }
)


@dataclass(frozen=True)
class DeidProfile:
    """Immutable de-identification profile binding tag rules and global flags."""

    name: str
    rules: dict[BaseTag, TagAction]
    keep_groups: frozenset[int]
    remove_private: bool
    remove_curves: bool
    remove_overlays: bool
    remove_unspecified: bool = False
    preserve_dates: bool = False
    modifies_dates: bool = False
    allowlist_csv: str = "default.csv"
    date_override_tags: frozenset[BaseTag] = field(default_factory=frozenset)
    preserved_private_specs: frozenset[PrivateTagSpec] = field(default_factory=frozenset)

    def apply(self, ds: Dataset) -> None:
        """Apply all de-identification rules to a pydicom Dataset in place.

        Phase 1: Insert a default SpecificCharacterSet when absent.
        Phase 2: Apply element-level rules.
        Phase 3: Apply global removal rules (private, curves, overlays, unspecified).
        Phase 4: Remove retired Group Length tags from all datasets.
        Phase 5: Correct VRs for elements read as OB/UN inside sequences.
        """
        self._ensure_specific_character_set(ds)
        self._apply_element_rules(ds)
        self._apply_global_rules(ds)
        self._emit_deid_method_code_sequence(ds)
        _remove_group_length_tags(ds)
        _correct_implicit_vr_elements(ds)

    def _ensure_specific_character_set(self, ds: Dataset) -> None:
        """Insert a default SpecificCharacterSet when absent or empty.

        Mandatory de-identification evidence attributes (PatientIdentityRemoved,
        DeIdentificationMethod, etc.) are created by their own set_value/
        append_value rules using create_if_missing=True, so they do not need a
        create pass here.
        """
        specific_charset_tag = Tag(0x0008, 0x0005)
        if specific_charset_tag not in ds or not ds[specific_charset_tag].value:
            ds.add_new(specific_charset_tag, "CS", "ISO_IR 100")

    def _should_skip_for_date_preservation(self, ds: Dataset, tag: BaseTag) -> bool:
        """Return True if this tag should be skipped due to date preservation.

        In LDS profiles, preserve_dates=True causes all rules for elements
        with VR=DA or VR=DT to be skipped (the element is kept unchanged). Tags
        in date_override_tags are exempted from this skip, so their rules
        are applied normally (used by LDS-No-DOB to remove PatientBirthDate).
        """
        if not self.preserve_dates:
            return False
        if tag in self.date_override_tags:
            return False
        if tag in ds:
            try:
                vr = ds[tag].VR
            except (ValueError, NotImplementedError):
                return False
            if vr in ("DA", "DT", "TM"):
                return True
        return False

    def _apply_element_rules(self, ds: Dataset) -> None:
        """Apply per-tag rules to the dataset, then recurse into processed sequence items.

        The top-level dataset receives every rule (a set_value/append_value rule
        with create_if_missing=True may create a missing element here). Item
        datasets of any processed sequence then receive the same rules, applied
        only to elements already present; no new elements are created inside
        sequence items.
        """
        for tag, action in self.rules.items():
            if self._should_skip_for_date_preservation(ds, tag):
                continue
            action(ds, tag)
        self._apply_element_rules_to_process_items(ds)

    def _apply_element_rules_to_process_items(self, ds: Dataset) -> None:
        """Recurse element rules into the item datasets of processed sequences.

        The full rule set is applied to each item dataset, but only to elements
        already present so no new elements are created inside sequence items.
        Sequences are traversed only when their rule is a process action, and
        nested processed sequences inside items are handled by recursion.
        """
        for tag, action in self.rules.items():
            if not getattr(action, "is_process_action", False) or tag not in ds:
                continue
            elem = ds[tag]
            try:
                is_sq = elem.VR == "SQ" and bool(elem.value)
            except (ValueError, NotImplementedError):
                continue
            if not is_sq:
                continue
            for item in elem.value:
                for item_tag, item_action in self.rules.items():
                    if item_tag not in item:
                        continue
                    if self._should_skip_for_date_preservation(item, item_tag):
                        continue
                    item_action(item, item_tag)
                self._apply_element_rules_to_process_items(item)

    def _apply_global_rules(self, ds: Dataset) -> None:
        """Remove private groups, curves, overlays, and unspecified elements.

        The rules are applied to the top-level dataset and, recursively, to the
        item datasets of any processed sequence.
        """
        self._apply_global_rules_to_dataset(ds)

    def _apply_global_rules_to_dataset(self, ds: Dataset) -> None:
        """Apply global removal rules to a single dataset.

        After removing elements at this level, recurse into the item datasets
        of any processed sequence so private groups, overlays, and unspecified
        elements nested inside a processed sequence are removed the same way.
        """
        tags_to_remove: list[BaseTag] = []

        preserved = self._resolve_preserved_tags(ds)

        for tag in list(ds.keys()):
            group = tag.group

            # Preserve File Meta Information
            if group in _PRESERVED_GROUPS:
                continue

            # Remove private tags (odd group numbers).
            # Tags with explicit rules are exempt, so a scripted element
            # overrides removal of the private group it belongs to.
            if self.remove_private and tag.is_private:
                if tag in preserved:
                    continue
                if tag not in self.rules:
                    tags_to_remove.append(tag)
                continue

            # Remove curve data (groups 50xx)
            if self.remove_curves and 0x5000 <= group <= 0x50FF:
                tags_to_remove.append(tag)
                continue

            # Remove overlay data (groups 60xx)
            if self.remove_overlays and 0x6000 <= group <= 0x60FF:
                tags_to_remove.append(tag)
                continue

            # Remove unspecified elements (pixels-only profile).
            # Groups 0x0028 and 0x7FE0 plus SOPClassUID, SOPInstanceUID, and
            # StudyInstanceUID are always protected from this removal.
            if self.remove_unspecified:
                if tag in _PROTECTED_TAGS or group in _PROTECTED_GROUPS:
                    continue
                if tag not in self.rules:
                    tags_to_remove.append(tag)

        for tag in tags_to_remove:
            del ds[tag]

        # Recurse into processed sequences. The same global removal rules are
        # applied to each item dataset of a sequence carrying a process action.
        # Only sequences whose rule is a process action are traversed,
        # descending exclusively into explicitly processed sequences.
        for proc_tag, action in self.rules.items():
            if not getattr(action, "is_process_action", False):
                continue
            if proc_tag not in ds:
                continue
            elem = ds[proc_tag]
            try:
                is_sq = elem.VR == "SQ" and bool(elem.value)
            except (ValueError, NotImplementedError):
                continue
            if is_sq:
                for item in elem.value:
                    self._apply_global_rules_to_dataset(item)

    def _resolve_preserved_tags(self, ds: Dataset) -> set[BaseTag]:
        """Resolve preserved private specs to concrete tags in this dataset.

        Returns the set of data-element tags plus their private-creator tags
        that must survive global private-group removal. The creator block is
        resolved from the creator value, since a group may host multiple
        creators.
        """
        keep: set[BaseTag] = set()
        if not self.preserved_private_specs:
            return keep
        for spec in self.preserved_private_specs:
            for block in range(0x10, 0x100):
                creator_tag = Tag(spec.group, block)
                if creator_tag not in ds:
                    continue
                # Private-creator LO values may be space/null padded; normalize
                # before comparing so a padded "GEMS_ACQU_01 " still matches.
                if str(ds[creator_tag].value).strip() != spec.creator:
                    continue
                keep.add(creator_tag)
                for offset in spec.offsets:
                    data_tag = Tag(spec.group, (block << 8) | offset)
                    if data_tag in ds:
                        keep.add(data_tag)
                break
        return keep

    def _emit_deid_method_code_sequence(self, ds: Dataset) -> None:
        """Add De-identification Method Code Sequence (0012,0064) when active.

        Emitted only when private tags are preserved, so the sequence appears
        solely on files that retain private elements (SIGNA Premier MR) and
        never on other files or profiles. Must run after global rules, since
        the pixels-only profile removes any element without an explicit rule.
        """
        if not self.preserved_private_specs:
            return

        from pydicom.dataset import Dataset as PydicomDataset

        codes = [
            ("113100", "Basic Application Confidentiality Profile"),
            ("113111", "Retain Safe Private Option"),
        ]
        # 113107 applies only when dates are shifted (retained but modified),
        # i.e. the jitter/default profile. Date-preserving profiles (LDS) keep
        # full dates, and the pixels-only profile removes dates entirely; neither
        # retains modified longitudinal temporal information.
        if self.modifies_dates:
            codes.append(("113107", "Retain Longitudinal Temporal Information With Modified Dates"))

        items = []
        for code_value, code_meaning in codes:
            item = PydicomDataset()
            item.add_new(Tag(0x0008, 0x0100), "SH", code_value)
            item.add_new(Tag(0x0008, 0x0102), "SH", "DCM")
            item.add_new(Tag(0x0008, 0x0104), "LO", code_meaning)
            items.append(item)

        ds.add_new(Tag(0x0012, 0x0064), "SQ", items)


def _remove_group_length_tags(ds: Dataset) -> None:
    """Remove retired Group Length (xxxx,0000) tags from a dataset recursively.

    DICOM PS3.5 Section 7.1 retired Group Length elements for all groups
    except (0002,0000). These are stripped here; pydicom preserves them when
    write_like_original=True. Removing them produces standard-compliant
    output and eliminates false comparison mismatches.
    """
    file_meta_group_length = Tag(0x0002, 0x0000)
    tags_to_remove = [tag for tag in ds.keys() if tag.element == 0x0000 and tag != file_meta_group_length]
    for tag in tags_to_remove:
        del ds[tag]

    for tag in ds.keys():
        try:
            is_sq = ds[tag].VR == "SQ" and ds[tag].value
        except (ValueError, NotImplementedError, BytesLengthException):
            continue
        if is_sq:
            for item in ds[tag].value:
                _remove_group_length_tags(item)


# VR types that can be decoded from raw bytes when pydicom falls back
# to OB or UN for implicit-VR-encoded sequence items.
_STRING_VRS = frozenset({"CS", "DS", "IS", "LO", "SH", "PN", "UI", "AE", "AS", "DA", "DT", "TM", "LT", "ST", "UT"})


def _correct_implicit_vr_elements(ds: Dataset) -> None:
    """Correct VRs for elements pydicom decoded as OB or UN inside sequences.

    Some DICOM files use implicit VR encoding inside explicit VR sequences.
    pydicom assigns VR=OB or VR=UN to these elements because the byte
    stream lacks VR information. This function resolves the correct VR
    from the DICOM data dictionary and re-decodes the raw bytes.
    """
    import struct

    for tag in list(ds.keys()):
        try:
            elem = ds[tag]
            vr = elem.VR
        except (ValueError, NotImplementedError, BytesLengthException):
            continue

        if vr == "SQ" and elem.value:
            for item in elem.value:
                _correct_implicit_vr_elements(item)
            continue

        if vr not in ("OB", "UN"):
            continue

        try:
            correct_vr = dictionary_VR(elem.tag)
        except KeyError:
            continue

        if correct_vr == elem.VR:
            continue

        raw_val = elem.value
        if not isinstance(raw_val, bytes):
            continue

        if correct_vr in _STRING_VRS:
            elem.VR = correct_vr
            elem.value = raw_val.decode("ascii", errors="replace").strip().rstrip("\x00")
        elif correct_vr == "FD" and len(raw_val) == 8:
            elem.VR = correct_vr
            elem.value = struct.unpack("<d", raw_val)[0]
        elif correct_vr == "FL" and len(raw_val) == 4:
            elem.VR = correct_vr
            elem.value = struct.unpack("<f", raw_val)[0]
        elif correct_vr == "UL" and len(raw_val) == 4:
            elem.VR = correct_vr
            elem.value = struct.unpack("<I", raw_val)[0]
        elif correct_vr == "US" and len(raw_val) == 2:
            elem.VR = correct_vr
            elem.value = struct.unpack("<H", raw_val)[0]
        elif correct_vr == "SL" and len(raw_val) == 4:
            elem.VR = correct_vr
            elem.value = struct.unpack("<i", raw_val)[0]
        elif correct_vr == "SS" and len(raw_val) == 2:
            elem.VR = correct_vr
            elem.value = struct.unpack("<h", raw_val)[0]
