"""Tests for the device catalog module."""

import pytest

from dicom_dre.catalog import CatalogDecision
from dicom_dre.catalog import DeviceCatalog
from dicom_dre.catalog import DeviceRule
from dicom_dre.catalog import DicomTags
from dicom_dre.catalog import ExclusionRule
from dicom_dre.catalog import Variant
from dicom_dre.catalog import deny_modalities
from dicom_dre.catalog import deny_when
from dicom_dre.catalog import device
from dicom_dre.catalog import match_string
from dicom_dre.catalog import variant
from dicom_dre.scrub_region import ScrubRegion


# ---------------------------------------------------------------------------
# match_string
# ---------------------------------------------------------------------------


class TestMatchString:
    """String matching engine with prefix-dispatch operators."""

    def test_bare_substring_case_insensitive(self):
        """Bare pattern matches as case-insensitive substring."""
        assert match_string("siemens", "SIEMENS HEALTHINEERS") is True, (
            "Bare pattern should match case-insensitive substring"
        )

    def test_bare_substring_no_match(self):
        """Bare pattern returns False when substring is absent."""
        assert match_string("philips", "SIEMENS") is False, "Bare pattern should not match when substring is absent"

    def test_bare_empty_pattern_matches_everything(self):
        """Empty bare pattern matches any value."""
        assert match_string("", "anything") is True, "Empty bare pattern should match any value"

    def test_exact_match(self):
        """= prefix matches exact value."""
        assert match_string("=CT", "CT") is True, "= prefix should match exact value"

    def test_exact_match_case_insensitive(self):
        """= prefix is case-insensitive."""
        assert match_string("=CT", "ct") is True, "= prefix should be case-insensitive"
        assert match_string("=REVOLUTION CT", "Revolution CT") is True, (
            "= prefix should match multi-word value case-insensitively"
        )
        assert match_string("=REVO_CT_22BC.50", "revo_ct_22bc.50") is True, (
            "= prefix should match value with punctuation case-insensitively"
        )

    def test_exact_empty_matches_blank(self):
        """= alone matches when tag is blank."""
        assert match_string("=", "") is True, "= alone should match blank value"

    def test_exact_empty_rejects_nonempty(self):
        """= alone rejects non-empty values."""
        assert match_string("=", "CT") is False, "= alone should reject non-empty value"

    def test_starts_with(self):
        """^ prefix matches case-insensitive starts-with."""
        assert match_string("^GE", "GE MEDICAL") is True, "^ prefix should match starts-with"

    def test_starts_with_case_insensitive(self):
        """^ prefix is case-insensitive."""
        assert match_string("^ge", "GE MEDICAL") is True, "^ prefix should be case-insensitive"

    def test_starts_with_no_match(self):
        """^ prefix returns False when prefix absent."""
        assert match_string("^GE", "SIEMENS") is False, "^ prefix should not match when prefix is absent"

    def test_regex_match(self):
        """Regex pattern delimited by / slashes."""
        assert match_string("/^CT$|^PT$/", "CT") is True, "Regex should match CT"

    def test_regex_no_match(self):
        """Regex returns False when pattern does not match."""
        assert match_string("/^CT$/", "MR") is False, "Regex should not match MR"

    def test_regex_search_not_fullmatch(self):
        """Regex uses search semantics, not fullmatch."""
        assert match_string("/PRIMARY/", "ORIGINAL\\PRIMARY\\AXIAL") is True, (
            "Regex should use search semantics, not fullmatch"
        )


# ---------------------------------------------------------------------------
# DicomTags
# ---------------------------------------------------------------------------


class TestDicomTags:
    """DicomTags wrapper for normalized attribute access."""

    def test_get_returns_value(self):
        """get() returns stored value."""
        tags = DicomTags({"Modality": "CT"})
        assert tags.get("Modality") == "CT", f"Expected 'CT', got {tags.get('Modality')!r}"

    def test_get_missing_returns_empty(self):
        """get() returns empty string for missing keys."""
        tags = DicomTags({})
        assert tags.get("Modality") == "", f"Expected empty string for missing key, got {tags.get('Modality')!r}"

    def test_get_list_splits_backslash(self):
        """get_list() splits on backslash."""
        tags = DicomTags({"ImageType": "ORIGINAL\\PRIMARY\\AXIAL"})
        assert tags.get_list("ImageType") == ["ORIGINAL", "PRIMARY", "AXIAL"], (
            f"Expected split list, got {tags.get_list('ImageType')}"
        )

    def test_get_list_empty_returns_empty_list(self):
        """get_list() returns [] for missing tags."""
        tags = DicomTags({})
        assert tags.get_list("ImageType") == [], (
            f"Expected empty list for missing tag, got {tags.get_list('ImageType')}"
        )

    def test_get_int_valid(self):
        """get_int() parses integer strings."""
        tags = DicomTags({"Rows": "512"})
        assert tags.get_int("Rows") == 512, f"Expected 512, got {tags.get_int('Rows')}"

    def test_get_int_missing(self):
        """get_int() returns None for missing keys."""
        tags = DicomTags({})
        assert tags.get_int("Rows") is None, f"Expected None for missing key, got {tags.get_int('Rows')}"

    def test_get_int_non_numeric(self):
        """get_int() returns None for non-numeric values."""
        tags = DicomTags({"Rows": "abc"})
        assert tags.get_int("Rows") is None, f"Expected None for non-numeric value, got {tags.get_int('Rows')}"

    def test_evidence_with_referenced_instance_marks_present(self):
        """from_dataset marks the evidence sequence present when it nests a SOP instance UID."""
        from pydicom.dataset import Dataset
        from pydicom.sequence import Sequence

        sop_item = Dataset()
        sop_item.ReferencedSOPInstanceUID = "1.2.3.4.5"
        series_item = Dataset()
        series_item.ReferencedSOPSequence = Sequence([sop_item])
        study_item = Dataset()
        study_item.ReferencedSeriesSequence = Sequence([series_item])
        ds = Dataset()
        ds.CurrentRequestedProcedureEvidenceSequence = Sequence([study_item])

        tags = DicomTags.from_dataset(ds)
        assert tags.get("CurrentRequestedProcedureEvidenceSequence") == "present", (
            "evidence sequence with a referenced SOP instance UID should be marked present"
        )

    def test_evidence_without_referenced_instance_absent(self):
        """from_dataset leaves the evidence marker absent when no SOP instance UID nests."""
        from pydicom.dataset import Dataset
        from pydicom.sequence import Sequence

        series_item = Dataset()
        series_item.ReferencedSOPSequence = Sequence([])
        study_item = Dataset()
        study_item.ReferencedSeriesSequence = Sequence([series_item])
        ds = Dataset()
        ds.CurrentRequestedProcedureEvidenceSequence = Sequence([study_item])

        tags = DicomTags.from_dataset(ds)
        assert tags.get("CurrentRequestedProcedureEvidenceSequence") == "", (
            "evidence sequence without a referenced SOP instance UID should not be marked present"
        )


# ---------------------------------------------------------------------------
# device() factory
# ---------------------------------------------------------------------------


class TestDeviceFactory:
    """device() factory function."""

    def test_creates_frozen_rule(self):
        """device() returns a frozen DeviceRule."""
        rule = device("Test", "allow", manufacturer="GE")
        assert isinstance(rule, DeviceRule), f"Expected DeviceRule instance, got {type(rule)}"
        assert rule.name == "Test", f"Expected name 'Test', got {rule.name!r}"
        assert rule.action == "allow", f"Expected action 'allow', got {rule.action!r}"
        assert rule.manufacturer == "GE", f"Expected manufacturer 'GE', got {rule.manufacturer!r}"

    def test_defaults_to_none(self):
        """Unspecified fields default to None."""
        rule = device("Test", "deny")
        assert rule.modality is None, f"Expected modality None, got {rule.modality!r}"
        assert rule.manufacturer_model_name is None, (
            f"Expected manufacturer_model_name None, got {rule.manufacturer_model_name!r}"
        )
        assert rule.variants is None, f"Expected variants None, got {rule.variants!r}"


# ---------------------------------------------------------------------------
# deny_modalities / deny_when factories
# ---------------------------------------------------------------------------


class TestExclusionFactories:
    """Exclusion rule factory functions."""

    def test_deny_modalities_exact(self):
        """deny_modalities creates rule with exact modalities."""
        rule = deny_modalities(exact=["PR", "SR"])
        assert isinstance(rule, ExclusionRule), f"Expected ExclusionRule instance, got {type(rule)}"
        assert rule.exact_modalities == ["PR", "SR"], f"Expected ['PR', 'SR'], got {rule.exact_modalities}"

    def test_deny_modalities_substring(self):
        """deny_modalities creates rule with substring modalities."""
        rule = deny_modalities(substring=["WAVEFORM"])
        assert rule.substring_modalities == ["WAVEFORM"], f"Expected ['WAVEFORM'], got {rule.substring_modalities}"

    def test_deny_when_creates_rule(self):
        """deny_when creates a conditional exclusion rule."""
        rule = deny_when("burned-in YES", burned_in_annotation="=YES", modality="SC")
        assert rule.name == "burned-in YES", f"Expected name 'burned-in YES', got {rule.name!r}"
        assert rule.burned_in_annotation == "=YES", f"Expected '=YES', got {rule.burned_in_annotation!r}"
        assert rule.modality == "SC", f"Expected modality 'SC', got {rule.modality!r}"


# ---------------------------------------------------------------------------
# Device matching
# ---------------------------------------------------------------------------


class TestDeviceMatching:
    """DeviceCatalog device matching and evaluation."""

    @pytest.fixture()
    def ge_ct_device(self):
        """A GE CT device rule with variants."""
        return device(
            "GE CT",
            "allow",
            manufacturer="GE",
            modality="=CT",
            variants=[
                variant(rows=512, cols=512, scrub=[(0, 0, 512, 50)]),
                variant(rows=256, cols=256, scrub=[(0, 0, 256, 25)]),
            ],
        )

    def test_device_matches_all_fields(self):
        """Device with all fields set matches when all match."""
        rule = device(
            "Test",
            "allow",
            manufacturer="GE",
            modality="=CT",
            manufacturer_model_name="LightSpeed",
        )
        tags = DicomTags(
            {
                "Manufacturer": "GE MEDICAL SYSTEMS",
                "Modality": "CT",
                "ManufacturerModelName": "LightSpeed VCT",
            }
        )
        catalog = DeviceCatalog([rule], [])
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"Expected action 'allow', got {decision.action!r}"
        assert decision.reason == "Test", f"Expected reason 'Test', got {decision.reason!r}"

    def test_device_rejects_when_field_mismatches(self):
        """Device does not match when a constrained field mismatches."""
        rule = device("Test", "allow", manufacturer="GE", modality="=CT")
        tags = DicomTags({"Manufacturer": "SIEMENS", "Modality": "CT"})
        catalog = DeviceCatalog([rule], [])
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"Expected deny on field mismatch, got {decision.action!r}"
        assert decision.reason == "No matching device or exclusion rule", (
            f"Expected fall-through reason, got {decision.reason!r}"
        )

    def test_variant_match_returns_scrub_regions(self, ge_ct_device):
        """Matching variant returns its scrub regions."""
        tags = DicomTags(
            {
                "Manufacturer": "GE MEDICAL",
                "Modality": "CT",
                "Rows": "512",
                "Columns": "512",
            }
        )
        catalog = DeviceCatalog([ge_ct_device], [])
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"Expected action 'allow', got {decision.action!r}"
        assert decision.scrub_regions == [ScrubRegion(0, 0, 512, 50)], (
            f"Expected variant scrub region, got {decision.scrub_regions}"
        )

    def test_no_variant_match_skips_device(self, ge_ct_device):
        """When device matches but no variant matches, skip the device."""
        tags = DicomTags(
            {
                "Manufacturer": "GE MEDICAL",
                "Modality": "CT",
                "Rows": "1024",
                "Columns": "1024",
            }
        )
        catalog = DeviceCatalog([ge_ct_device], [])
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"Expected deny when no variant matches, got {decision.action!r}"

    def test_first_match_wins(self):
        """First matching device determines the decision."""
        rule_a = device("First", "deny", manufacturer="GE")
        rule_b = device("Second", "allow", manufacturer="GE")
        tags = DicomTags({"Manufacturer": "GE"})
        catalog = DeviceCatalog([rule_a, rule_b], [])
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"Expected deny from first rule, got {decision.action!r}"
        assert decision.reason == "First", f"Expected reason 'First', got {decision.reason!r}"

    def test_scrub_action_short_circuits(self):
        """Scrub action short-circuits with its own regions, skipping later rules."""
        scrub_rule = device(
            "Scrubber",
            "scrub",
            manufacturer="GE",
            variants=[variant(scrub=[(0, 0, 100, 20)])],
        )
        allow_rule = device("AllowAll", "allow")
        tags = DicomTags({"Manufacturer": "GE"})
        catalog = DeviceCatalog([scrub_rule, allow_rule], [])
        decision = catalog.evaluate(tags)
        assert decision.action == "scrub", f"Expected action 'scrub', got {decision.action!r}"
        assert decision.reason == "Scrubber", f"Expected reason 'Scrubber', got {decision.reason!r}"
        assert decision.scrub_regions == [ScrubRegion(0, 0, 100, 20)], (
            f"Expected scrub region, got {decision.scrub_regions}"
        )

    def test_scrub_action_skips_exclusions(self):
        """A matching scrub device short-circuits and is not denied by exclusions."""
        scrub_rule = device(
            "Scrubber",
            "scrub",
            manufacturer="GE",
            modality="CT",
            variants=[variant(scrub=[(0, 0, 100, 20)])],
        )
        excl = deny_modalities(exact=["CT"])
        tags = DicomTags({"Manufacturer": "GE", "Modality": "CT"})
        catalog = DeviceCatalog([scrub_rule], [excl])
        decision = catalog.evaluate(tags)
        assert decision.action == "scrub", f"Expected action 'scrub', got {decision.action!r}"
        assert decision.reason == "Scrubber", f"Expected reason 'Scrubber', got {decision.reason!r}"
        assert decision.scrub_regions == [ScrubRegion(0, 0, 100, 20)], (
            f"Expected scrub region, got {decision.scrub_regions}"
        )


# ---------------------------------------------------------------------------
# Image type matching
# ---------------------------------------------------------------------------


class TestImageTypeMatching:
    """Image type field matching (all, any, exclude)."""

    def test_image_type_all_must_be_present(self):
        """image_type requires all patterns to appear."""
        rule = device(
            "Test",
            "allow",
            image_type=["ORIGINAL", "PRIMARY"],
        )
        tags_match = DicomTags({"ImageType": "ORIGINAL\\PRIMARY\\AXIAL"})
        tags_no = DicomTags({"ImageType": "DERIVED\\PRIMARY\\AXIAL"})
        catalog = DeviceCatalog([rule], [])
        assert catalog.evaluate(tags_match).action == "allow", "image_type with all patterns present should allow"
        assert catalog.evaluate(tags_no).action == "deny", "image_type with a missing pattern should deny"

    def test_image_type_any(self):
        """image_type_any requires at least one pattern to appear."""
        rule = device(
            "Test",
            "allow",
            image_type_any=["LOCALIZER", "SCOUT"],
        )
        tags = DicomTags({"ImageType": "ORIGINAL\\PRIMARY\\LOCALIZER"})
        catalog = DeviceCatalog([rule], [])
        assert catalog.evaluate(tags).action == "allow", "image_type_any should allow when one pattern is present"

    def test_image_type_exclude(self):
        """image_type_exclude rejects when any pattern appears."""
        rule = device(
            "Test",
            "allow",
            image_type_exclude=["SECONDARY"],
        )
        tags_ok = DicomTags({"ImageType": "ORIGINAL\\PRIMARY"})
        tags_bad = DicomTags({"ImageType": "ORIGINAL\\SECONDARY"})
        catalog = DeviceCatalog([rule], [])
        assert catalog.evaluate(tags_ok).action == "allow", "image_type_exclude should allow when pattern absent"
        assert catalog.evaluate(tags_bad).action == "deny", "image_type_exclude should deny when pattern present"


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------


class TestExclusionMatching:
    """Exclusion rule evaluation."""

    def test_deny_modalities_exact(self):
        """deny_modalities with exact list denies matching modality."""
        excl = deny_modalities(exact=["PR", "SR"])
        tags = DicomTags({"Modality": "PR"})
        catalog = DeviceCatalog([], [excl])
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"Expected deny for excluded modality, got {decision.action!r}"

    def test_deny_modalities_exact_case_insensitive(self):
        """deny_modalities exact match is case-insensitive."""
        excl = deny_modalities(exact=["pr"])
        tags = DicomTags({"Modality": "PR"})
        catalog = DeviceCatalog([], [excl])
        assert catalog.evaluate(tags).action == "deny", "deny_modalities exact match should be case-insensitive"

    def test_deny_modalities_substring(self):
        """deny_modalities with substring denies containing modality."""
        excl = deny_modalities(substring=["WAVEFORM"])
        tags = DicomTags({"Modality": "ECG WAVEFORM"})
        catalog = DeviceCatalog([], [excl])
        assert catalog.evaluate(tags).action == "deny", "deny_modalities substring should deny containing modality"

    def test_deny_modalities_no_match_falls_through(self):
        """deny_modalities passes non-matching modalities."""
        excl = deny_modalities(exact=["PR"])
        tags = DicomTags({"Modality": "CT"})
        catalog = DeviceCatalog([], [excl])
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"Expected deny by default, got {decision.action!r}"
        assert decision.reason == "No matching device or exclusion rule", (
            f"Expected fall-through reason, got {decision.reason!r}"
        )

    def test_deny_when_burned_in(self):
        """deny_when matches on BurnedInAnnotation."""
        excl = deny_when("burned-in YES", burned_in_annotation="=YES", modality="=SC")
        tags = DicomTags({"BurnedInAnnotation": "YES", "Modality": "SC"})
        catalog = DeviceCatalog([], [excl])
        assert catalog.evaluate(tags).action == "deny", "deny_when should deny on BurnedInAnnotation match"

    def test_deny_when_image_type_empty(self):
        """deny_when with image_type_empty matches absent ImageType."""
        excl = deny_when("no image type", image_type_empty=True)
        tags = DicomTags({"Modality": "OT"})
        catalog = DeviceCatalog([], [excl])
        assert catalog.evaluate(tags).action == "deny", (
            "deny_when image_type_empty should deny when ImageType is absent"
        )

    def test_deny_when_modality_not(self):
        """deny_when with modality_not rejects when modality matches."""
        excl = deny_when("not CT", modality_not="=CT")
        tags_ct = DicomTags({"Modality": "CT"})
        tags_mr = DicomTags({"Modality": "MR"})
        catalog = DeviceCatalog([], [excl])
        # CT is excluded by modality_not, so the exclusion does NOT match.
        assert catalog.evaluate(tags_ct).reason == "No matching device or exclusion rule", (
            "modality_not should exclude CT so the rule does not match"
        )
        # MR is not excluded, so the exclusion matches.
        assert catalog.evaluate(tags_mr).action == "deny", "MR is not excluded so the rule should deny"
        assert catalog.evaluate(tags_mr).reason == "Denied by rule: not CT", (
            f"Expected denial reason for 'not CT', got {catalog.evaluate(tags_mr).reason!r}"
        )

    def test_deny_when_conversion_type_present(self):
        """deny_when with conversion_type_present matches existing ConversionType."""
        excl = deny_when("has conversion type", conversion_type_present=True)
        tags = DicomTags({"ConversionType": "SYN"})
        catalog = DeviceCatalog([], [excl])
        assert catalog.evaluate(tags).action == "deny", "conversion_type_present should deny when ConversionType exists"

    def test_deny_when_conversion_type_not_present(self):
        """conversion_type_present=True does not match absent ConversionType."""
        excl = deny_when("has conversion type", conversion_type_present=True)
        tags = DicomTags({})
        catalog = DeviceCatalog([], [excl])
        assert catalog.evaluate(tags).reason == "No matching device or exclusion rule", (
            "conversion_type_present should not match absent ConversionType"
        )


# ---------------------------------------------------------------------------
# Default action
# ---------------------------------------------------------------------------


class TestDefaultAction:
    """Default action when no device or exclusion matches."""

    def test_default_deny(self):
        """Empty catalog returns deny by default."""
        catalog = DeviceCatalog([], [])
        tags = DicomTags({"Modality": "CT"})
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"Expected default deny, got {decision.action!r}"

    def test_custom_default(self):
        """Custom default_action is used."""
        catalog = DeviceCatalog([], [], default_action="allow")
        tags = DicomTags({"Modality": "CT"})
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"Expected custom default allow, got {decision.action!r}"


# ---------------------------------------------------------------------------
# CatalogDecision
# ---------------------------------------------------------------------------


class TestCatalogDecision:
    """CatalogDecision dataclass construction."""

    def test_frozen(self):
        """CatalogDecision is frozen."""
        d = CatalogDecision(action="allow", reason="test")
        with pytest.raises(AttributeError):
            d.action = "deny"  # type: ignore[misc]

    def test_default_scrub_regions(self):
        """scrub_regions defaults to empty list."""
        d = CatalogDecision(action="allow", reason="test")
        assert d.scrub_regions == [], f"Expected empty scrub_regions, got {d.scrub_regions}"

    def test_fields(self):
        """All fields stored correctly."""
        regions = [ScrubRegion(0, 0, 100, 20)]
        v = Variant(rows=512)
        d = CatalogDecision(
            action="allow",
            reason="GE CT",
            scrub_regions=regions,
            matched_variant=v,
        )
        assert d.action == "allow", f"Expected action 'allow', got {d.action!r}"
        assert d.reason == "GE CT", f"Expected reason 'GE CT', got {d.reason!r}"
        assert d.scrub_regions == regions, f"Expected stored regions, got {d.scrub_regions}"
        assert d.matched_variant == v, f"Expected stored variant, got {d.matched_variant}"


# ---------------------------------------------------------------------------
# Variant matching
# ---------------------------------------------------------------------------


class TestVariantMatching:
    """Variant-level matching within devices."""

    def test_variant_version_narrowing(self):
        """Variant narrows by software version."""
        rule = device(
            "Versioned",
            "allow",
            manufacturer="GE",
            variants=[
                variant(software_versions="^V1", scrub=[(0, 0, 50, 10)]),
                variant(software_versions="^V2", scrub=[(0, 0, 100, 20)]),
            ],
        )
        tags = DicomTags({"Manufacturer": "GE", "SoftwareVersions": "V2.1"})
        catalog = DeviceCatalog([rule], [])
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"Expected action 'allow', got {decision.action!r}"
        assert decision.scrub_regions == [ScrubRegion(0, 0, 100, 20)], (
            f"Expected V2 variant scrub region, got {decision.scrub_regions}"
        )

    def test_variant_image_type_narrowing(self):
        """Variant narrows by image type."""
        rule = device(
            "ImageTyped",
            "allow",
            manufacturer="GE",
            variants=[
                variant(image_type=["DERIVED"], scrub=[(0, 0, 50, 10)]),
                variant(image_type=["ORIGINAL"], scrub=[(0, 0, 100, 20)]),
            ],
        )
        tags = DicomTags({"Manufacturer": "GE", "ImageType": "ORIGINAL\\PRIMARY"})
        catalog = DeviceCatalog([rule], [])
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"Expected action 'allow', got {decision.action!r}"
        assert decision.scrub_regions == [ScrubRegion(0, 0, 100, 20)], (
            f"Expected ORIGINAL variant scrub region, got {decision.scrub_regions}"
        )

    def test_variant_no_scrub_key(self):
        """Variant without scrub key yields empty scrub regions."""
        rule = device(
            "NoScrub",
            "allow",
            manufacturer="GE",
            variants=[variant(rows=512, cols=512)],
        )
        tags = DicomTags(
            {
                "Manufacturer": "GE",
                "Rows": "512",
                "Columns": "512",
            }
        )
        catalog = DeviceCatalog([rule], [])
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"Expected action 'allow', got {decision.action!r}"
        assert decision.scrub_regions == [], f"Expected empty scrub_regions, got {decision.scrub_regions}"


# ---------------------------------------------------------------------------
# Explicit dedicated-field matching
# ---------------------------------------------------------------------------


class TestExplicitFieldMatching:
    """Device matching with dedicated fields for structured tags."""

    def test_body_part_examined_match(self):
        """body_part_examined matches against DicomTags values."""
        rule = device(
            "Custom",
            "allow",
            body_part_examined="/(?i)^BREAST$/",
        )
        tags = DicomTags({"BodyPartExamined": "BREAST"})
        catalog = DeviceCatalog([rule], [])
        assert catalog.evaluate(tags).action == "allow", "body_part_examined regex should match and allow"

    def test_conversion_type_no_match(self):
        """conversion_type rejects when value mismatches."""
        rule = device(
            "Custom",
            "allow",
            conversion_type="=",
        )
        tags = DicomTags({"ConversionType": "WSD"})
        catalog = DeviceCatalog([rule], [])
        assert catalog.evaluate(tags).action == "deny", "conversion_type mismatch should deny"
