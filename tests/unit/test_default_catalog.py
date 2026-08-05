"""Tests for the default device catalog data.

Validates that the default catalog loads correctly and that representative
device rules and exclusion rules produce expected decisions.
"""

import pytest

from dicom_dre.catalog import CatalogDecision
from dicom_dre.catalog import DicomTags
from dicom_dre.default_catalog import default_devices
from dicom_dre.default_catalog import default_exclusions
from dicom_dre.default_catalog import get_default_catalog
from dicom_dre.scrub_region import ScrubRegion


@pytest.fixture()
def catalog():
    """Return the default catalog instance."""
    return get_default_catalog()


class TestCatalogLoading:
    """Verify module-level data structures load without errors."""

    def test_devices_list_non_empty(self):
        """Verify devices list contains entries."""
        assert len(default_devices) > 100, f"expected more than 100 devices, got {len(default_devices)}"

    def test_exclusions_list_non_empty(self):
        """Verify exclusions list contains entries."""
        assert len(default_exclusions) > 20, f"expected more than 20 exclusions, got {len(default_exclusions)}"

    def test_get_default_catalog_returns_catalog(self, catalog):
        """Verify factory returns a catalog with expected counts."""
        assert catalog is not None, "get_default_catalog should return a catalog instance"
        assert len(catalog.devices) == len(default_devices), (
            f"expected {len(default_devices)} devices, got {len(catalog.devices)}"
        )
        assert len(catalog.exclusions) == len(default_exclusions), (
            f"expected {len(default_exclusions)} exclusions, got {len(catalog.exclusions)}"
        )

    def test_all_devices_have_valid_action(self):
        """Verify every device has allow, deny, or scrub action."""
        for d in default_devices:
            assert d.action in ("allow", "deny", "scrub"), f"Device {d.name!r} has invalid action {d.action!r}"

    def test_all_devices_have_name(self):
        """Verify every device has a non-empty name."""
        for d in default_devices:
            assert d.name, f"Device with action {d.action!r} has empty name"


class TestCRDXDevices:
    """CR/DX device rules evaluation."""

    def test_konica_0402_cr_v6_allows(self, catalog):
        """KONICA 0402 CR version 6 variant allows with scrub."""
        tags = DicomTags(
            {
                "Manufacturer": "KONICA MINOLTA",
                "Modality": "CR",
                "ManufacturerModelName": "0402",
                "SoftwareVersions": "6.1.2",
                "Rows": "2446",
                "Columns": "2446",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert decision.scrub_regions == [ScrubRegion(0, 2308, 2446, 137)], (
            f"unexpected scrub regions: {decision.scrub_regions}"
        )

    def test_konica_0402_cr_v2_allows(self, catalog):
        """KONICA 0402 CR version 2 variant allows with scrub."""
        tags = DicomTags(
            {
                "Manufacturer": "KONICA",
                "Modality": "CR",
                "ManufacturerModelName": "0402",
                "SoftwareVersions": "2.0",
                "Rows": "2010",
                "Columns": "2446",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert decision.scrub_regions == [ScrubRegion(0, 0, 2446, 115)], (
            f"unexpected scrub regions: {decision.scrub_regions}"
        )

    def test_medicatech_krystalrad_allows(self, catalog):
        """MedicaTechUSA KrystalRad 660 allows with scrub."""
        tags = DicomTags(
            {
                "Manufacturer": "MedicaTechUSA",
                "Modality": "DX",
                "ManufacturerModelName": "KrystalRad 660",
                "SoftwareVersions": "1.5",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert len(decision.scrub_regions) > 0, "expected at least one scrub region"

    def test_cuattro_clouddr_allows(self, catalog):
        """Cuattro CloudDR allows with scrub region."""
        tags = DicomTags(
            {
                "Manufacturer": "Cuattro Medical",
                "Modality": "DX",
                "ManufacturerModelName": "CloudDR",
                "SoftwareVersions": "3.0",
                "Rows": "3072",
                "Columns": "3072",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert ScrubRegion(2500, 0, 572, 400) in decision.scrub_regions, (
            f"expected scrub region not present in {decision.scrub_regions}"
        )


class TestCTPETDevices:
    """CT/PET device rules evaluation."""

    def test_ge_discovery_512x512_allows(self, catalog):
        """GE Discovery PET 512x512 allows with scrub."""
        tags = DicomTags(
            {
                "Manufacturer": "GE MEDICAL SYSTEMS",
                "Modality": "PT",
                "ManufacturerModelName": "Discovery ST",
                "SecondaryCaptureDeviceManufacturerModelName": "Volume Viewer 5",
                "SoftwareVersions": "5.0",
                "ImageType": "ORIGINAL\\PRIMARY",
                "Rows": "512",
                "Columns": "512",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert len(decision.scrub_regions) > 0, "expected at least one scrub region"

    def test_ge_revolution_ct_allows(self, catalog):
        """GE Revolution CT allows."""
        tags = DicomTags(
            {
                "Manufacturer": "GE MEDICAL SYSTEMS",
                "Modality": "CT",
                "ManufacturerModelName": "REVOLUTION CT",
                "SoftwareVersions": "REVO_CT_22BC.50",
                "Rows": "512",
                "Columns": "512",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"

    def test_ge_revolution_ct_derived_reformat_mixed_case_allows(self, catalog):
        """GE Revolution CT DERIVED reformat with mixed-case identifiers allows.

        Reproduces a STETSON study series ("2mm Coronal"/"2mm Sagittal") whose
        ManufacturerModelName ("Revolution CT") and SoftwareVersions
        ("revo_ct_22bc.50") differ in case from the device rule literals. The
        The device rule must match case-insensitively; otherwise these
        DERIVED\\SECONDARY\\REFORMATTED\\AVERAGE images
        fall through to the "Non-CR/DR/DX/MR DERIVED" exclusion and are dropped.
        """
        tags = DicomTags(
            {
                "Manufacturer": "GE MEDICAL SYSTEMS",
                "Modality": "CT",
                "ManufacturerModelName": "Revolution CT",
                "SoftwareVersions": "revo_ct_22bc.50",
                "ImageType": "DERIVED\\SECONDARY\\REFORMATTED\\AVERAGE",
                "SeriesDescription": "2mm Sagittal",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.2",
                "Rows": "512",
                "Columns": "512",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action} ({decision.reason})"
        assert decision.reason == "GE REVOLUTION CT", f"unexpected matching rule: {decision.reason}"

    def test_mimvista_standalone_allows(self, catalog):
        """MIMvista standalone CT allows."""
        tags = DicomTags(
            {
                "Manufacturer": "MIMvista Corp",
                "Modality": "CT",
                "SoftwareVersions": "",
                "Rows": "512",
                "Columns": "512",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"


class TestSiemensCT:
    """Siemens CT device rules."""

    def test_siemens_emotion_allows(self, catalog):
        """Siemens Emotion CT allows without burned-in."""
        tags = DicomTags(
            {
                "Manufacturer": "SIEMENS",
                "Modality": "CT",
                "ManufacturerModelName": "Emotion 16",
                "ImageType": "ORIGINAL\\PRIMARY\\AXIAL",
                "BurnedInAnnotation": "NO",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"

    def test_siemens_ct_with_burned_in_denies(self, catalog):
        """Siemens CT with BurnedInAnnotation YES is denied."""
        tags = DicomTags(
            {
                "Manufacturer": "SIEMENS",
                "Modality": "CT",
                "ManufacturerModelName": "Emotion 16",
                "ImageType": "ORIGINAL\\PRIMARY\\AXIAL",
                "BurnedInAnnotation": "YES",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"


class TestUltrasoundDevices:
    """US device rules evaluation."""

    def test_acuson_sequoia_768x1024_allows(self, catalog):
        """ACUSON SEQUOIA 768x1024 allows with scrub."""
        tags = DicomTags(
            {
                "Manufacturer": "ACUSON",
                "Modality": "US",
                "ManufacturerModelName": "SEQUOIA 512",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.6.1",
                "ImageType": "ORIGINAL\\PRIMARY",
                "Rows": "768",
                "Columns": "1024",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert ScrubRegion(0, 0, 1024, 40) in decision.scrub_regions, (
            f"expected scrub region not present in {decision.scrub_regions}"
        )

    def test_philips_epiq_1080x1920_allows(self, catalog):
        """Philips EPIQ 1080x1920 allows with scrub."""
        tags = DicomTags(
            {
                "Manufacturer": "Philips Medical Systems",
                "Modality": "US",
                "ManufacturerModelName": "EPIQ 7G",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.6.1",
                "ImageType": "ORIGINAL\\PRIMARY",
                "Rows": "1080",
                "Columns": "1920",
                "SequenceOfUltrasoundRegions": "present",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert ScrubRegion(0, 0, 1920, 32) in decision.scrub_regions, (
            f"expected scrub region not present in {decision.scrub_regions}"
        )

    def test_ge_logiq_e9_970x1552_allows(self, catalog):
        """GE LOGIQE9 970x1552 allows with scrub."""
        tags = DicomTags(
            {
                "Manufacturer": "GE Healthcare",
                "Modality": "US",
                "ManufacturerModelName": "LOGIQE9",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.6.1",
                "ImageType": "ORIGINAL\\PRIMARY",
                "Rows": "970",
                "Columns": "1552",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert ScrubRegion(0, 0, 1174, 68) in decision.scrub_regions, (
            f"expected scrub region not present in {decision.scrub_regions}"
        )

    def test_ge_v830_852x1136_allows(self, catalog):
        """GE V830 852x1136 allows with scrub."""
        tags = DicomTags(
            {
                "Manufacturer": "GE Vingmed Ultrasound",
                "Modality": "US",
                "ManufacturerModelName": "V830",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.3.1",
                "ImageType": "ORIGINAL\\PRIMARY",
                "Rows": "852",
                "Columns": "1136",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert ScrubRegion(0, 0, 1136, 64) in decision.scrub_regions, (
            f"expected scrub region not present in {decision.scrub_regions}"
        )

    def test_sonosite_turbo_480x640_allows(self, catalog):
        """SonoSite Turbo 480x640 allows with scrub."""
        tags = DicomTags(
            {
                "Manufacturer": "SonoSite, Inc.",
                "Modality": "US",
                "ManufacturerModelName": "M-Turbo",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.6.1",
                "ImageType": "ORIGINAL\\PRIMARY",
                "Rows": "480",
                "Columns": "640",
                "SequenceOfUltrasoundRegions": "present",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"
        assert ScrubRegion(0, 0, 640, 24) in decision.scrub_regions, (
            f"expected scrub region not present in {decision.scrub_regions}"
        )


class TestMammography:
    """Mammography device rules."""

    def test_hologic_selenia_allows(self, catalog):
        """Hologic Selenia mammography allows."""
        tags = DicomTags(
            {
                "Manufacturer": "Hologic, Inc.",
                "Modality": "MG",
                "ManufacturerModelName": "Selenia Dimensions",
                "ImageType": "ORIGINAL\\PRIMARY",
                "BurnedInAnnotation": "NO",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"

    def test_hologic_selenia_secondary_allows(self, catalog):
        """Hologic Selenia allows SECONDARY images."""
        tags = DicomTags(
            {
                "Manufacturer": "Hologic, Inc.",
                "Modality": "MG",
                "ManufacturerModelName": "Selenia Dimensions",
                "ImageType": "SECONDARY\\DERIVED",
                "BurnedInAnnotation": "NO",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"

    def test_mammography_with_burned_in_denies(self, catalog):
        """Mammography with BurnedInAnnotation YES is denied."""
        tags = DicomTags(
            {
                "Manufacturer": "Hologic, Inc.",
                "Modality": "MG",
                "ManufacturerModelName": "Selenia Dimensions",
                "ImageType": "ORIGINAL\\PRIMARY",
                "BurnedInAnnotation": "YES",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"


class TestExclusionRules:
    """Exclusion/deny-list rules."""

    def test_deny_pr_modality(self, catalog):
        """PR modality is denied."""
        tags = DicomTags({"Modality": "PR"})
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"

    def test_deny_sr_modality(self, catalog):
        """SR modality is denied."""
        tags = DicomTags({"Modality": "SR"})
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"

    def test_deny_secondary_capture_sop(self, catalog):
        """Secondary Capture SOP class is denied."""
        tags = DicomTags(
            {
                "Modality": "CT",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.7",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"

    def test_deny_encapsulated_pdf(self, catalog):
        """Encapsulated PDF SOP class is denied."""
        tags = DicomTags(
            {
                "Modality": "OT",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.104.1",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"

    def test_deny_empty_image_type(self, catalog):
        """Empty ImageType is denied."""
        tags = DicomTags(
            {
                "Modality": "CT",
                "ImageType": "",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"

    def test_deny_burned_in_yes(self, catalog):
        """BurnedInAnnotation YES is denied."""
        tags = DicomTags(
            {
                "Modality": "CT",
                "BurnedInAnnotation": "YES",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"

    def test_deny_vidar(self, catalog):
        """Vidar manufacturer is denied."""
        tags = DicomTags(
            {
                "Modality": "CR",
                "Manufacturer": "Vidar Systems Corporation",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"

    def test_deny_icad(self, catalog):
        """Verify iCAD manufacturer is denied."""
        tags = DicomTags(
            {
                "Modality": "MG",
                "Manufacturer": "iCAD Inc.",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"

    def test_deny_xa_modality(self, catalog):
        """XA modality is denied."""
        tags = DicomTags({"Modality": "XA"})
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"

    def test_deny_rf_modality(self, catalog):
        """RF modality is denied."""
        tags = DicomTags({"Modality": "RF"})
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"


class TestDefaultAccept:
    """Unknown devices should be accepted by default."""

    def test_unknown_device_accepted(self, catalog):
        """Unrecognized device is accepted by default."""
        tags = DicomTags(
            {
                "Manufacturer": "Unknown Corp",
                "Modality": "CT",
                "ManufacturerModelName": "Unknown Model",
                "ImageType": "ORIGINAL\\PRIMARY\\AXIAL",
                "BurnedInAnnotation": "NO",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"expected allow, got {decision.action}"

    def test_empty_tags_denied(self, catalog):
        """Empty tags produce a deny decision."""
        tags = DicomTags({})
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"expected deny, got {decision.action}"


class TestScrubOnlyDevices:
    """Scrub-only devices short-circuit and keep the instance with scrub regions."""

    def test_ge_ct_dose_report_accumulates_scrub(self, catalog):
        """GE CT dose report scrub rule produces a CatalogDecision."""
        tags = DicomTags(
            {
                "Manufacturer": "GE MEDICAL SYSTEMS",
                "Modality": "CT",
                "SeriesDescription": "Dose Report",
                "ImageType": "ORIGINAL\\PRIMARY",
                "BurnedInAnnotation": "NO",
            }
        )
        decision = catalog.evaluate(tags)
        # The scrub device matches and short-circuits, keeping the instance
        # with its own scrub regions instead of falling through to exclusions.
        assert isinstance(decision, CatalogDecision), f"expected CatalogDecision, got {type(decision).__name__}"


class TestSignaPremierPreservedPrivateTags:
    """GE SIGNA Premier MR rule carries preserved private-tag specs."""

    def _base_tags(self, **overrides):
        """Build a qualifying SIGNA Premier MR instance, allowing overrides."""
        values = {
            "Manufacturer": "GE MEDICAL SYSTEMS",
            "Modality": "MR",
            "ManufacturerModelName": "SIGNA Premier",
            "ImageType": "ORIGINAL\\PRIMARY\\OTHER",
            "SOPClassUID": "1.2.840.10008.5.1.4.1.1.4",
            "BurnedInAnnotation": "NO",
        }
        values.update(overrides)
        return DicomTags(values)

    def test_sample_allows_with_specs(self, catalog):
        """The qualifying sample allows and carries the two specs."""
        decision = catalog.evaluate(self._base_tags())
        assert decision.action == "allow", f"expected allow, got {decision.action} ({decision.reason})"
        assert decision.reason == "GE SIGNA Premier MR - preserved private tags", (
            f"unexpected matching rule: {decision.reason}"
        )
        creators = {spec.creator for spec in decision.preserved_private_tags}
        assert creators == {"GEMS_ACQU_01", "GEMS_PARM_01"}, f"unexpected preserved creators: {creators}"

    def test_non_ge_sample_has_no_specs(self, catalog):
        """A non-GE MR instance yields no preserved specs."""
        tags = DicomTags(
            {
                "Manufacturer": "SIEMENS",
                "Modality": "MR",
                "ManufacturerModelName": "Skyra",
                "ImageType": "ORIGINAL\\PRIMARY",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.4",
                "BurnedInAnnotation": "NO",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.preserved_private_tags == (), (
            f"non-GE MR instance should carry no specs, got {decision.preserved_private_tags}"
        )

    def test_burned_in_annotation_denied(self, catalog):
        """A burned-in-annotation instance is denied, not admitted."""
        decision = catalog.evaluate(self._base_tags(BurnedInAnnotation="YES"))
        assert decision.action == "deny", f"burned-in annotation should deny, got {decision.action}"

    def test_mrsc_image_type_denied(self, catalog):
        """An MRSC ImageType component is denied."""
        decision = catalog.evaluate(self._base_tags(ImageType="ORIGINAL\\PRIMARY\\MRSC"))
        assert decision.action == "deny", f"MRSC image type should deny, got {decision.action}"

    def test_secondary_capture_sop_denied(self, catalog):
        """A Secondary Capture SOP class is denied."""
        decision = catalog.evaluate(self._base_tags(SOPClassUID="1.2.840.10008.5.1.4.1.1.7"))
        assert decision.action == "deny", f"secondary capture SOP class should deny, got {decision.action}"

    def test_conversion_type_present_denied(self, catalog):
        """A populated ConversionType is denied."""
        decision = catalog.evaluate(self._base_tags(ConversionType="WSD"))
        assert decision.action == "deny", f"populated ConversionType should deny, got {decision.action}"

    def test_derived_secondary_denied(self, catalog):
        """DERIVED\\SECONDARY without ORIGINAL/PRIMARY is denied."""
        decision = catalog.evaluate(self._base_tags(ImageType="DERIVED\\SECONDARY\\OTHER"))
        assert decision.action == "deny", (
            f"DERIVED/SECONDARY without ORIGINAL/PRIMARY should deny, got {decision.action}"
        )


class TestPresentationStateAdmission:
    """GSPS 2D softcopy presentation state admission and denial rules."""

    def test_annotated_admitted_class_allowed(self, catalog):
        """An admitted-class PR with a graphic annotation sequence is allowed."""
        tags = DicomTags(
            {
                "Modality": "PR",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.11.1",
                "GraphicAnnotationSequence": "present",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"annotated GSPS should allow, got {decision.action}"

    def test_unannotated_admitted_class_denied(self, catalog):
        """An admitted-class PR without an annotation sequence is denied."""
        tags = DicomTags(
            {
                "Modality": "PR",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.11.1",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"un-annotated GSPS should deny, got {decision.action}"
        assert "no annotation data" in decision.reason, f"unexpected reason: {decision.reason}"

    def test_volumetric_presentation_state_denied(self, catalog):
        """A volumetric presentation state SOP class is denied as unsupported."""
        tags = DicomTags(
            {
                "Modality": "PR",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.11.6",
                "GraphicAnnotationSequence": "present",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "deny", f"volumetric PR should deny, got {decision.action}"
        assert "unsupported presentation state" in decision.reason, f"unexpected reason: {decision.reason}"

    def test_non_pr_instance_unaffected(self, catalog):
        """A non-PR CT instance is not denied by the presentation-state rules."""
        tags = DicomTags(
            {
                "Manufacturer": "GE MEDICAL SYSTEMS",
                "Modality": "CT",
                "ManufacturerModelName": "REVOLUTION CT",
                "SOPClassUID": "1.2.840.10008.5.1.4.1.1.2",
                "SoftwareVersions": "REVO_CT_22BC.50",
                "ImageType": "ORIGINAL\\PRIMARY\\AXIAL",
                "Rows": "512",
                "Columns": "512",
            }
        )
        decision = catalog.evaluate(tags)
        assert decision.action == "allow", f"CT instance should allow, got {decision.action}"
        assert "presentation state" not in decision.reason, (
            f"CT instance should not match presentation-state rules, got reason: {decision.reason}"
        )
