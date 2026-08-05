"""DeidProfile dataclass and apply() logic."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from typing import TYPE_CHECKING

from pydicom.datadict import dictionary_VR
from pydicom.errors import BytesLengthException
from pydicom.tag import BaseTag
from pydicom.tag import Tag

from dicom_dre.parameters import DEFAULT_STUDY_ID
from dicom_dre.uid_utils import hashuid
from dicom_dre.uid_utils import stable_jitter


if TYPE_CHECKING:
    from pydicom.dataset import Dataset

    from dicom_dre.actions import TagAction
    from dicom_dre.catalog import PrivateTagSpec
    from dicom_dre.parameters import DeidParameters

# File Meta Information group is always preserved.
_PRESERVED_GROUPS: frozenset[int] = frozenset({0x0002})

# CID 7050 code meanings for the non-temporal de-identification option codes a
# profile may declare in deid_options. The temporal codes 113106/113107 and the
# Basic Profile code 113100 are emitted separately, not from this map.
_DEID_OPTION_MEANINGS: dict[str, str] = {
    "113101": "Clean Pixel Data Option",
    "113102": "Clean Recognizable Visual Features Option",
    "113103": "Clean Graphics Option",
    "113104": "Clean Structured Content Option",
    "113105": "Clean Descriptors Option",
    "113108": "Retain Patient Characteristics Option",
    "113109": "Retain Device Identity Option",
    "113110": "Retain UIDs Option",
}

# UIDs under the DICOM root are registered values (SOP Class, Transfer Syntax,
# coding scheme, well-known SOP instance) and must not be hashed. Per-object
# identifier UIDs are generated under organization roots, never this root, so the
# prefix reliably separates the two.
_DICOM_UID_ROOT = "1.2.840.10008."

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
    hash_salt: str = ""
    uid_root: str | None = None
    uid_use_study_salt: bool = False
    date_override_tags: frozenset[BaseTag] = field(default_factory=frozenset)
    preserved_private_specs: frozenset[PrivateTagSpec] = field(default_factory=frozenset)
    emits_basic_profile: bool = True
    deid_options: frozenset[str] = field(default_factory=frozenset)

    def apply(self, ds: Dataset, params: DeidParameters, *, applied_options: frozenset[str] = frozenset()) -> None:
        """Apply all de-identification rules to a pydicom Dataset in place.

        Per-patient values are read from ``params`` at apply time. ``applied_options``
        carries per-instance de-identification option codes the caller applied
        outside the profile rules (for example ``113101`` when the pipeline
        scrubbed burned-in pixel text); they are merged into the method code
        sequence alongside the profile-declared ``deid_options``.

        Phase 0: Validate the jitter and resolve a per-patient shift when unset.
        Phase 1: Insert a default SpecificCharacterSet when absent.
        Phase 2: Apply element-level rules.
        Phase 3: Apply global removal rules (private, curves, overlays, unspecified).
        Phase 4: Remove retired Group Length tags from all datasets.
        Phase 5: Correct VRs for elements read as OB/UN inside sequences.
        """
        self._validate_jitter(params)
        params = self._resolve_jitter(ds, params)
        self._ensure_specific_character_set(ds)
        self._apply_element_rules(ds, params)
        self._apply_global_rules(ds)
        self._emit_deid_method_code_sequence(ds, applied_options)
        _remove_group_length_tags(ds)
        correct_implicit_vr_elements(ds)

    def _validate_jitter(self, params: DeidParameters) -> None:
        """Reject a jitter inconsistent with this profile's date policy.

        A date-shifting profile (``modifies_dates=True``) must never emit an
        unshifted (zero-day) result, so an explicit ``jitter == 0`` is rejected;
        an unset jitter resolves to a deterministic per-study shift derived from
        the hash salt and study identifier. A date-preserving profile
        (``modifies_dates=False``) keeps dates verbatim, so an explicit non-zero
        jitter contradicts the profile and is rejected; ``jitter == 0`` and an
        unset jitter request no shift and are accepted and inert.
        """
        if not self.modifies_dates:
            if params.jitter:
                raise ValueError(f"jitter must not be supplied for the non-date-shifting profile {self.name!r}")
            return
        if params.jitter == 0:
            raise ValueError("jitter must be non-zero for a date-shifting profile")

    def _resolve_jitter(self, ds: Dataset, params: DeidParameters) -> DeidParameters:
        """Return params with a derived jitter when the caller supplied none.

        For a date-shifting profile with no explicit jitter, the shift is derived
        once from the profile salt, the study identifier, and the original (PHI)
        PatientID read from the top-level dataset. Resolving here -- before any
        rule mutates PatientID -- keeps every date in the instance shifted by the
        same per-patient, per-study amount. Non-shifting profiles and an explicit
        jitter are returned unchanged.
        """
        if not self.modifies_dates or params.jitter is not None:
            return params
        study_id = params.study_id if params.study_id is not None else DEFAULT_STUDY_ID
        patient_id_tag = Tag(0x0010, 0x0020)
        original_patient_id = ds[patient_id_tag].value if patient_id_tag in ds else None
        patient_key = str(original_patient_id) if original_patient_id else ""
        days = stable_jitter(self.hash_salt, study_id, patient_key)
        return replace(params, jitter=days)

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

    def _apply_element_rules(self, ds: Dataset, params: DeidParameters) -> None:
        """Apply per-tag rules to the dataset, then recurse into every sequence.

        The top-level dataset receives every rule (a set_value/append_value rule
        with create_if_missing=True may create a missing element here). Item
        datasets of every nested sequence then receive the same rules, applied
        only to elements already present; no new elements are created inside
        sequence items.
        """
        for tag, action in self.rules.items():
            if self._should_skip_for_date_preservation(ds, tag):
                continue
            action(ds, tag, params)
        self._apply_uid_fallback(ds, params)
        self._apply_element_rules_to_sequence_items(ds, params)

    def _apply_element_rules_to_sequence_items(self, ds: Dataset, params: DeidParameters) -> None:
        """Recurse element rules into the item datasets of every sequence.

        The full rule set is applied to each item dataset, but only to elements
        already present so no new elements are created inside sequence items.
        Every nested SQ element is traversed, so tag-based rules (UID hashing,
        date jitter, PHI removal, keep, free-text redaction) reach every nesting
        level. UIDs are hashed by tag membership in the UID-hash rule set, so SOP
        Class and transfer-syntax UIDs are left unchanged; the UID fallback
        hashes any other UID not under the DICOM root.
        """
        for tag in list(ds.keys()):
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
                    item_action(item, item_tag, params)
                self._apply_uid_fallback(item, params)
                self._apply_element_rules_to_sequence_items(item, params)

    def _apply_uid_fallback(self, ds: Dataset, params: DeidParameters) -> None:
        """Hash unregistered UID values that have no more-specific rule.

        For each UI element with no explicit rule, the value is hashed unless it
        is a DICOM-registered UID (under the 1.2.840.10008 root: SOP Class,
        Transfer Syntax, coding scheme, well-known SOP instance), which is left
        unchanged. Hashing uses the profile UID root and salt policy, so a UID
        that also appears under an explicit UID rule maps to the same
        replacement and cross-references stay consistent. Disabled when the
        profile sets no UID root.
        """
        if self.uid_root is None:
            return
        for elem in list(ds):
            tag = elem.tag
            if tag.group == 0x0002 or tag in self.rules:
                continue
            if self._resolve_effective_vr(elem) != "UI":
                continue
            self._hash_unregistered_uid(elem, params)

    def _hash_unregistered_uid(self, elem: object, params: DeidParameters) -> None:
        """Hash a single unregistered UID element in place.

        Decodes raw bytes for an implicit-VR (UN/OB) element and sets VR to UI so
        Phase 5 does not re-decode it. Empty and multi-valued values are left
        unchanged, as is a value under the DICOM root. Hashing matches the
        profile UID rule (root and study-salt policy) so shared UIDs align.
        """
        root = self.uid_root
        if root is None:
            return
        value = elem.value  # type: ignore[attr-defined]
        if isinstance(value, bytes):
            value = value.decode("ascii", errors="replace").strip().rstrip("\x00")
            elem.VR = "UI"  # type: ignore[attr-defined]
        if not value or not isinstance(value, str):
            return
        if value.startswith(_DICOM_UID_ROOT):
            return
        if self.uid_use_study_salt:
            salt = params.study_id if params.study_id is not None else DEFAULT_STUDY_ID
            combined = value + salt
        else:
            combined = value
        elem.value = hashuid(root, combined)  # type: ignore[attr-defined]

    @staticmethod
    def _resolve_effective_vr(elem: object) -> str:
        """Resolve an element's VR, mapping a runtime UN/OB to its dictionary VR.

        An element read from an implicit-VR-encoded sequence item carries VR UN
        or OB until Phase 5 corrects it. Resolving the dictionary VR here makes
        the UID fallback independent of encoding. An unknown tag keeps its
        runtime VR.
        """
        try:
            vr = elem.VR  # type: ignore[attr-defined]
        except (ValueError, NotImplementedError):
            return ""
        if vr in ("UN", "OB"):
            try:
                return dictionary_VR(elem.tag)  # type: ignore[attr-defined]
            except KeyError:
                return vr
        return vr

    def _apply_global_rules(self, ds: Dataset) -> None:
        """Remove private groups, curves, overlays, and unspecified elements.

        The rules are applied to the top-level dataset and, recursively, to the
        item datasets of every nested sequence.
        """
        self._apply_global_rules_to_dataset(ds)

    def _apply_global_rules_to_dataset(self, ds: Dataset) -> None:
        """Apply global removal rules to a single dataset.

        After removing elements at this level, recurse into the item datasets
        of every nested sequence so private groups, overlays, and unspecified
        elements nested at any depth are removed the same way.
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

        # Recurse into every sequence so private groups, curves, overlays, and
        # unspecified elements nested at any depth are removed the same way.
        for seq_tag in list(ds.keys()):
            if seq_tag not in ds:
                continue
            elem = ds[seq_tag]
            try:
                is_sq = elem.VR == "SQ" and bool(elem.value)
            except (ValueError, NotImplementedError):
                continue
            if not is_sq:
                continue
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

    def _emit_deid_method_code_sequence(self, ds: Dataset, applied_options: frozenset[str] = frozenset()) -> None:
        """Add De-identification Method Code Sequence (0012,0064).

        Emitted on every de-identified dataset. Items are added in this order:
        the Basic Application Confidentiality Profile (113100) when this profile
        implements it; the derived longitudinal temporal code (113107 for
        modified dates, 113106 for full dates, none when dates are removed); one
        item per code in ``deid_options`` unioned with ``applied_options`` (the
        per-instance codes the caller applied outside the rules); and 113111
        (Retain Safe Private Option) when private elements are preserved. Codes
        are de-duplicated before writing. Runs after global rules, since the
        pixels-only profile removes any element without an explicit rule.
        """
        from pydicom.dataset import Dataset as PydicomDataset

        codes: list[tuple[str, str]] = []
        if self.emits_basic_profile:
            codes.append(("113100", "Basic Application Confidentiality Profile"))
        if self.modifies_dates:
            codes.append(("113107", "Retain Longitudinal Temporal Information With Modified Dates"))
        elif self.preserve_dates:
            codes.append(("113106", "Retain Longitudinal Temporal Information With Full Dates"))
        for code_value in sorted(self.deid_options | applied_options):
            codes.append((code_value, _DEID_OPTION_MEANINGS.get(code_value, code_value)))
        if self.preserved_private_specs:
            codes.append(("113111", "Retain Safe Private Option"))

        seen: set[str] = set()
        unique: list[tuple[str, str]] = []
        for code_value, code_meaning in codes:
            if code_value in seen:
                continue
            seen.add(code_value)
            unique.append((code_value, code_meaning))

        if not unique:
            return

        items = []
        for code_value, code_meaning in unique:
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


def correct_implicit_vr_elements(ds: Dataset) -> None:
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
                correct_implicit_vr_elements(item)
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


# Backward-compatible alias for the former private name. Internal callers and
# existing imports continue to resolve to the public function object.
_correct_implicit_vr_elements = correct_implicit_vr_elements
