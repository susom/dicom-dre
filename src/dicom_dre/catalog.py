"""Device catalog for DICOM filtering and pixel scrubbing.

Evaluates DICOM instances against declarative device and exclusion rules to
decide whether an instance is allowed, denied, or scrubbed, and returns the
pixel regions to blank for scrub decisions.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import TYPE_CHECKING
from typing import cast

from dicom_dre.scrub_region import ScrubRegion


if TYPE_CHECKING:
    import pydicom


@dataclass(frozen=True, slots=True)
class Variant:
    """A resolution or version variant within a device rule.

    Attributes:
        rows: Required image row count, or None if unconstrained.
        cols: Required image column count, or None if unconstrained.
        sop_class_uid: SOPClassUID pattern(s) for narrowing, or None if unconstrained.
        software_versions: Software version pattern(s) for narrowing.
        image_type: ImageType component(s) that all must appear.
        image_type_any: ImageType component(s) where at least one must appear.
        image_type_exclude: ImageType component(s) where none may appear.
        scrub_regions: Pixel regions to blank, as ScrubRegion instances.
    """

    rows: int | None = None
    cols: int | None = None
    sop_class_uid: str | list[str] | None = None
    software_versions: str | list[str] | None = None
    image_type: str | list[str] | None = None
    image_type_any: str | list[str] | None = None
    image_type_exclude: str | list[str] | None = None
    scrub_regions: list[ScrubRegion] = field(default_factory=list)


def _normalize_scrub(
    scrub: list[tuple[int, int, int, int] | ScrubRegion] | None,
) -> list[ScrubRegion]:
    """Normalize scrub region inputs to a list of ScrubRegion instances."""
    if not scrub:
        return []
    return [region if isinstance(region, ScrubRegion) else ScrubRegion.from_tuple(region) for region in scrub]


def variant(
    *,
    rows: int | None = None,
    cols: int | None = None,
    sop_class_uid: str | list[str] | None = None,
    software_versions: str | list[str] | None = None,
    image_type: str | list[str] | None = None,
    image_type_any: str | list[str] | None = None,
    image_type_exclude: str | list[str] | None = None,
    scrub: list[tuple[int, int, int, int] | ScrubRegion] | None = None,
) -> Variant:
    """Create a variant for a device rule.

    Args:
        rows: Required image row count.
        cols: Required image column count.
        sop_class_uid: SOPClassUID pattern(s).
        software_versions: Software version pattern(s).
        image_type: ImageType component(s) that all must appear.
        image_type_any: ImageType component(s) where at least one must appear.
        image_type_exclude: ImageType component(s) where none may appear.
        scrub: Pixel regions to blank, as (x, y, width, height) tuples or
            ScrubRegion instances.

    Returns:
        A frozen Variant instance.
    """
    return Variant(
        rows=rows,
        cols=cols,
        sop_class_uid=sop_class_uid,
        software_versions=software_versions,
        image_type=image_type,
        image_type_any=image_type_any,
        image_type_exclude=image_type_exclude,
        scrub_regions=_normalize_scrub(scrub),
    )


@dataclass(frozen=True, slots=True)
class PrivateTagSpec:
    """A device-approved private element to preserve verbatim.

    Attributes:
        group: Private group number (odd), e.g. 0x0019.
        creator: Private creator string, e.g. "GEMS_ACQU_01".
        offsets: Element offsets (low byte) to preserve within the
            creator's resolved block, e.g. (0xBB, 0xBC, 0xBD).
    """

    group: int
    creator: str
    offsets: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CatalogDecision:
    """Result of evaluating a DICOM instance against the device catalog.

    Attributes:
        action: One of "allow", "deny", or "scrub".
        reason: Human-readable explanation for the decision.
        scrub_regions: Pixel regions to blank, as ScrubRegion instances.
        matched_variant: The Variant that matched, if any.
        preserved_private_tags: Private-element specs to preserve verbatim.
    """

    action: str
    reason: str
    scrub_regions: list[ScrubRegion] = field(default_factory=list)
    matched_variant: Variant | None = None
    preserved_private_tags: tuple[PrivateTagSpec, ...] = ()


def match_string(pattern: str, value: str) -> bool:
    """Match a pattern against a DICOM tag value.

    Prefix dispatch:
      - bare string: case-insensitive substring match
      - ``=`` prefix: case-insensitive exact match; ``"="`` alone matches
        when the tag is missing or blank
      - ``^`` prefix: case-insensitive starts-with
      - ``/pattern/``: regex search (``re.search``)

    Args:
        pattern: The match pattern with optional prefix.
        value: The string value of the DICOM tag.

    Returns:
        True when the pattern matches *value*.
    """
    if pattern.startswith("/") and pattern.endswith("/") and len(pattern) > 1:
        regex = pattern[1:-1]
        return re.search(regex, value) is not None

    if pattern.startswith("="):
        expected = pattern[1:]
        if expected == "":
            return value == ""
        return value.casefold() == expected.casefold()

    if pattern.startswith("^"):
        prefix = pattern[1:]
        return value.lower().startswith(prefix.lower())

    # bare string — case-insensitive substring
    return pattern.lower() in value.lower()


class DicomTags:
    """Lightweight wrapper for reading DICOM attributes needed by the catalog.

    Normalizes access so the matching engine does not interact with pydicom
    directly.
    """

    def __init__(self, values: dict[str, str]) -> None:
        """Initialize with a keyword-to-string-value mapping."""
        self._values = values

    def get(self, keyword: str) -> str:
        """Return the string value for *keyword*, or ``""`` if absent."""
        return self._values.get(keyword, "")

    def as_dict(self) -> dict[str, str]:
        """Return the catalog-relevant tag values as a plain dict copy."""
        return dict(self._values)

    def get_list(self, keyword: str) -> list[str]:
        """Return the multi-valued tag as a list of strings.

        Image Type, for example, is stored as ``"ORIGINAL\\PRIMARY\\AXIAL"``.
        """
        raw = self.get(keyword)
        if not raw:
            return []
        return [v.strip() for v in raw.split("\\")]

    def get_int(self, keyword: str) -> int | None:
        """Return the integer value for *keyword*, or None if absent/non-numeric."""
        raw = self.get(keyword)
        if not raw:
            return None
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    @classmethod
    def from_dataset(cls, ds: pydicom.Dataset) -> DicomTags:
        """Build from an existing pydicom Dataset."""
        from pydicom.multival import MultiValue

        keywords = [
            "Manufacturer",
            "ManufacturerModelName",
            "Modality",
            "SoftwareVersions",
            "ImageType",
            "Rows",
            "Columns",
            "BurnedInAnnotation",
            "SOPClassUID",
            "SeriesNumber",
            "ConversionType",
            "SeriesDescription",
            "StudyDescription",
            "BodyPartExamined",
            "PixelSpacing",
            "SecondaryCaptureDeviceManufacturerModelName",
            "CodeMeaning",
            "CommentsOnRadiationDose",
            "SequenceOfUltrasoundRegions",
        ]
        values: dict[str, str] = {}
        for kw in keywords:
            elem = ds.get(kw)
            if elem is None:
                continue
            val = ds[kw].value if hasattr(ds[kw], "value") else ds[kw]
            if val is None:
                continue
            if isinstance(val, (list, MultiValue)):
                parts = list(cast(Iterable, val))
                values[kw] = "\\".join(str(p) for p in parts)
            elif kw == "SequenceOfUltrasoundRegions":
                # Sequence presence: store "present" if the sequence exists
                # and has at least one item with a non-empty RegionDataType.
                try:
                    seq = list(cast(Iterable, val))
                    has_region = any(str(getattr(item, "RegionDataType", "")) != "" for item in seq)
                    if has_region:
                        values[kw] = "present"
                except (TypeError, StopIteration):
                    pass
            else:
                values[kw] = str(val)
        return cls(values)

    @classmethod
    def from_file(cls, path: Path) -> DicomTags:
        """Read a DICOM file and extract catalog-relevant tags."""
        import pydicom

        ds = pydicom.dcmread(str(path), stop_before_pixels=True)
        return cls.from_dataset(ds)


@dataclass(frozen=True, slots=True)
class DeviceRule:
    """A single device entry in the catalog.

    All keyword fields default to ``None`` (unconstrained). Lists use OR
    semantics across elements; all specified fields on a device are AND'd.

    Note:
        Prefer matching on structured tags (manufacturer, model, modality,
        resolution, SOP class, image type) over the free-text
        ``series_description`` and ``study_description``. Matching on those
        description fields should be a last resort: the regression fixtures
        retain a description value only for cases where it currently drives a
        decision, so adding or changing a description-based rule has limited
        regression coverage for values that did not previously match.
    """

    name: str
    action: str

    manufacturer: str | list[str] | None = None
    modality: str | list[str] | None = None
    manufacturer_model_name: str | list[str] | None = None
    software_versions: str | list[str] | None = None
    image_type: str | list[str] | None = None
    image_type_any: str | list[str] | None = None
    image_type_exclude: str | list[str] | None = None
    burned_in_annotation: str | None = None
    sop_class_uid: str | list[str] | None = None
    secondary_capture_device_manufacturer_model_name: str | list[str] | None = None
    # Free-text match; use only as a last resort (see class note on regression coverage).
    series_description: str | list[str] | None = None
    code_meaning: str | list[str] | None = None
    comments_on_radiation_dose: str | list[str] | None = None
    # Free-text match; use only as a last resort (see class note on regression coverage).
    study_description: str | list[str] | None = None
    conversion_type: str | list[str] | None = None
    pixel_spacing: str | list[str] | None = None
    body_part_examined: str | list[str] | None = None
    requires_ultrasound_regions: bool = False
    variants: list[Variant] | None = None
    preserved_private_tags: tuple[PrivateTagSpec, ...] = ()


def device(
    name: str,
    action: str,
    *,
    manufacturer: str | list[str] | None = None,
    modality: str | list[str] | None = None,
    manufacturer_model_name: str | list[str] | None = None,
    software_versions: str | list[str] | None = None,
    image_type: str | list[str] | None = None,
    image_type_any: str | list[str] | None = None,
    image_type_exclude: str | list[str] | None = None,
    burned_in_annotation: str | None = None,
    sop_class_uid: str | list[str] | None = None,
    secondary_capture_device_manufacturer_model_name: str | list[str] | None = None,
    series_description: str | list[str] | None = None,
    code_meaning: str | list[str] | None = None,
    comments_on_radiation_dose: str | list[str] | None = None,
    study_description: str | list[str] | None = None,
    conversion_type: str | list[str] | None = None,
    pixel_spacing: str | list[str] | None = None,
    body_part_examined: str | list[str] | None = None,
    requires_ultrasound_regions: bool = False,
    variants: list[Variant] | None = None,
    preserved_private_tags: tuple[PrivateTagSpec, ...] = (),
    rows: int | None = None,
    cols: int | None = None,
    scrub: list[tuple[int, int, int, int] | ScrubRegion] | None = None,
) -> DeviceRule:
    """Create a device rule for the catalog.

    Args:
        name: Human-readable device identifier.
        action: One of "allow", "deny", or "scrub".
        manufacturer: Manufacturer pattern(s).
        modality: Modality pattern(s).
        manufacturer_model_name: Model name pattern(s).
        software_versions: Software version pattern(s).
        image_type: Required Image Type component(s) — all must appear.
        image_type_any: Image Type component(s) — at least one must appear.
        image_type_exclude: Image Type component(s) — none may appear.
        burned_in_annotation: BurnedInAnnotation value pattern.
        sop_class_uid: SOPClassUID pattern(s).
        secondary_capture_device_manufacturer_model_name: SecondaryCaptureDeviceManufacturerModelName pattern(s).
        series_description: SeriesDescription pattern(s).
        code_meaning: CodeMeaning pattern(s).
        comments_on_radiation_dose: CommentsOnRadiationDose pattern(s).
        study_description: StudyDescription pattern(s).
        conversion_type: ConversionType pattern(s).
        pixel_spacing: PixelSpacing pattern(s).
        body_part_examined: BodyPartExamined pattern(s).
        requires_ultrasound_regions: When True, the image must contain a
            non-empty SequenceOfUltrasoundRegions to match this device.
        variants: Resolution/version variants with optional scrub regions.
        preserved_private_tags: Private-element specs to preserve verbatim.
        rows: Shorthand for a single variant row count.
        cols: Shorthand for a single variant column count.
        scrub: Shorthand for a single variant's scrub regions.

    Returns:
        A frozen DeviceRule instance.
    """
    if variants is not None and (rows is not None or cols is not None or scrub is not None):
        raise ValueError(
            f"Device '{name}': cannot specify both 'variants' and 'rows'/'cols'/'scrub'. Use one or the other."
        )
    if variants is None and (rows is not None or cols is not None or scrub is not None):
        variants = [Variant(rows=rows, cols=cols, scrub_regions=_normalize_scrub(scrub))]
    return DeviceRule(
        name=name,
        action=action,
        manufacturer=manufacturer,
        modality=modality,
        manufacturer_model_name=manufacturer_model_name,
        software_versions=software_versions,
        image_type=image_type,
        image_type_any=image_type_any,
        image_type_exclude=image_type_exclude,
        burned_in_annotation=burned_in_annotation,
        sop_class_uid=sop_class_uid,
        secondary_capture_device_manufacturer_model_name=secondary_capture_device_manufacturer_model_name,
        series_description=series_description,
        code_meaning=code_meaning,
        comments_on_radiation_dose=comments_on_radiation_dose,
        study_description=study_description,
        conversion_type=conversion_type,
        pixel_spacing=pixel_spacing,
        body_part_examined=body_part_examined,
        requires_ultrasound_regions=requires_ultrasound_regions,
        variants=variants,
        preserved_private_tags=preserved_private_tags,
    )


@dataclass(frozen=True, slots=True)
class ExclusionRule:
    """A deny-list rule that rejects DICOM instances by tag criteria."""

    name: str
    reason: str

    # deny_modalities fields
    exact_modalities: list[str] | None = None
    substring_modalities: list[str] | None = None

    # deny_when fields
    sop_class: str | list[str] | None = None
    burned_in_annotation: str | None = None
    image_type_empty: bool | None = None
    image_type_any: str | list[str] | None = None
    manufacturer: str | list[str] | None = None
    manufacturer_model_name: str | list[str] | None = None
    manufacturer_model_name_fallback: str | list[str] | None = None
    modality: str | list[str] | None = None
    modality_not: str | list[str] | None = None
    series_number: str | None = None
    conversion_type_present: bool | None = None
    image_type_exclude: str | list[str] | None = None


def deny_modalities(
    *,
    exact: list[str] | None = None,
    substring: list[str] | None = None,
) -> ExclusionRule:
    """Create a modality-based exclusion rule.

    Args:
        exact: Modalities matched with case-insensitive equality.
        substring: Modalities matched with case-insensitive contains.

    Returns:
        An ExclusionRule that denies matching modalities.
    """
    parts = []
    if exact:
        parts.append(f"modality in [{', '.join(exact)}]")
    if substring:
        parts.append(f"modality contains [{', '.join(substring)}]")
    reason = "Denied modality: " + "; ".join(parts)
    return ExclusionRule(
        name="deny_modalities",
        reason=reason,
        exact_modalities=exact,
        substring_modalities=substring,
    )


def deny_when(
    name: str,
    *,
    sop_class: str | list[str] | None = None,
    burned_in_annotation: str | None = None,
    image_type_empty: bool | None = None,
    image_type_any: str | list[str] | None = None,
    manufacturer: str | list[str] | None = None,
    manufacturer_model_name: str | list[str] | None = None,
    manufacturer_model_name_fallback: str | list[str] | None = None,
    modality: str | list[str] | None = None,
    modality_not: str | list[str] | None = None,
    series_number: str | None = None,
    conversion_type_present: bool | None = None,
    image_type_exclude: str | list[str] | None = None,
) -> ExclusionRule:
    """Create a conditional exclusion rule.

    Args:
        name: Human-readable identifier for the exclusion.
        sop_class: SOP Class UID pattern(s).
        burned_in_annotation: BurnedInAnnotation value pattern.
        image_type_empty: If True, matches when ImageType is absent/empty.
        image_type_any: ImageType component(s) — at least one must appear.
        manufacturer: Manufacturer pattern(s).
        manufacturer_model_name: Model name pattern(s).
        manufacturer_model_name_fallback: Model pattern(s) if primary model field is empty.
        modality: Modality pattern(s) that must match.
        modality_not: Modality pattern(s) that must NOT match.
        series_number: SeriesNumber pattern.
        conversion_type_present: If True, matches when ConversionType is present.
        image_type_exclude: ImageType component(s) — none may appear.

    Returns:
        An ExclusionRule for conditional denial.
    """
    return ExclusionRule(
        name=name,
        reason=f"Denied by rule: {name}",
        sop_class=sop_class,
        burned_in_annotation=burned_in_annotation,
        image_type_empty=image_type_empty,
        image_type_any=image_type_any,
        manufacturer=manufacturer,
        manufacturer_model_name=manufacturer_model_name,
        manufacturer_model_name_fallback=manufacturer_model_name_fallback,
        modality=modality,
        modality_not=modality_not,
        series_number=series_number,
        conversion_type_present=conversion_type_present,
        image_type_exclude=image_type_exclude,
    )


def _match_field(
    patterns: str | list[str] | None,
    value: str,
) -> bool:
    """Match a field constraint against a tag value.

    Returns True when *patterns* is None (unconstrained). Otherwise, OR across
    list elements — at least one pattern must match.
    """
    if patterns is None:
        return True
    if isinstance(patterns, str):
        patterns = [patterns]
    return any(match_string(p, value) for p in patterns)


def _match_image_type_all(
    patterns: str | list[str] | None,
    image_type_parts: list[str],
) -> bool:
    """All patterns must appear somewhere in the ImageType components."""
    if patterns is None:
        return True
    if isinstance(patterns, str):
        patterns = [patterns]
    joined = "\\".join(image_type_parts)
    for p in patterns:
        if not any(match_string(p, part) for part in image_type_parts):
            if not match_string(p, joined):
                return False
    return True


def _match_image_type_any(
    patterns: str | list[str] | None,
    image_type_parts: list[str],
) -> bool:
    """At least one pattern must appear in the ImageType components."""
    if patterns is None:
        return True
    if isinstance(patterns, str):
        patterns = [patterns]
    for p in patterns:
        if any(match_string(p, part) for part in image_type_parts):
            return True
    return False


def _match_image_type_exclude(
    patterns: str | list[str] | None,
    image_type_parts: list[str],
) -> bool:
    """None of the patterns may appear in the ImageType components."""
    if patterns is None:
        return True
    if isinstance(patterns, str):
        patterns = [patterns]
    joined = "\\".join(image_type_parts)
    for p in patterns:
        if any(match_string(p, part) for part in image_type_parts):
            return False
        if match_string(p, joined):
            return False
    return True


def _match_device(rule: DeviceRule, tags: DicomTags) -> bool:
    """Return True when all constrained fields on *rule* match *tags*."""
    if not _match_field(rule.manufacturer, tags.get("Manufacturer")):
        return False
    if not _match_field(rule.modality, tags.get("Modality")):
        return False
    if not _match_field(rule.manufacturer_model_name, tags.get("ManufacturerModelName")):
        return False
    if not _match_field(rule.software_versions, tags.get("SoftwareVersions")):
        return False
    if not _match_field(rule.burned_in_annotation, tags.get("BurnedInAnnotation")):
        return False
    if not _match_field(rule.sop_class_uid, tags.get("SOPClassUID")):
        return False
    if not _match_field(
        rule.secondary_capture_device_manufacturer_model_name,
        tags.get("SecondaryCaptureDeviceManufacturerModelName"),
    ):
        return False
    if not _match_field(rule.series_description, tags.get("SeriesDescription")):
        return False
    if not _match_field(rule.code_meaning, tags.get("CodeMeaning")):
        return False
    if not _match_field(rule.comments_on_radiation_dose, tags.get("CommentsOnRadiationDose")):
        return False
    if not _match_field(rule.study_description, tags.get("StudyDescription")):
        return False
    if not _match_field(rule.conversion_type, tags.get("ConversionType")):
        return False
    if not _match_field(rule.pixel_spacing, tags.get("PixelSpacing")):
        return False
    if not _match_field(rule.body_part_examined, tags.get("BodyPartExamined")):
        return False

    image_type_parts = tags.get_list("ImageType")

    if not _match_image_type_all(rule.image_type, image_type_parts):
        return False
    if not _match_image_type_any(rule.image_type_any, image_type_parts):
        return False
    if not _match_image_type_exclude(rule.image_type_exclude, image_type_parts):
        return False

    if rule.requires_ultrasound_regions:
        if tags.get("SequenceOfUltrasoundRegions") != "present":
            return False

    return True


def _match_variant(v: Variant, tags: DicomTags) -> bool:
    """Return True when a Variant matches *tags*."""
    if v.rows is not None:
        if tags.get_int("Rows") != v.rows:
            return False
    if v.cols is not None:
        if tags.get_int("Columns") != v.cols:
            return False
    if not _match_field(v.sop_class_uid, tags.get("SOPClassUID")):
        return False
    if not _match_field(v.software_versions, tags.get("SoftwareVersions")):
        return False

    image_type_parts = tags.get_list("ImageType")
    if not _match_image_type_all(v.image_type, image_type_parts):
        return False
    if not _match_image_type_any(v.image_type_any, image_type_parts):
        return False
    if not _match_image_type_exclude(v.image_type_exclude, image_type_parts):
        return False
    return True


def _match_exclusion(rule: ExclusionRule, tags: DicomTags) -> bool:
    """Return True when the exclusion rule matches *tags*."""
    # deny_modalities path
    if rule.exact_modalities is not None:
        modality = tags.get("Modality").upper()
        if modality in [m.upper() for m in rule.exact_modalities]:
            return True

    if rule.substring_modalities is not None:
        modality = tags.get("Modality").lower()
        if any(m.lower() in modality for m in rule.substring_modalities):
            return True

    # deny_when path — return True only if ALL specified conditions match
    if rule.exact_modalities is not None or rule.substring_modalities is not None:
        # This was a deny_modalities rule; conditions above were evaluated.
        return False

    # For deny_when, all specified conditions must match.
    if rule.sop_class is not None:
        if not _match_field(rule.sop_class, tags.get("SOPClassUID")):
            return False

    if rule.burned_in_annotation is not None:
        if not _match_field(rule.burned_in_annotation, tags.get("BurnedInAnnotation")):
            return False

    if rule.image_type_empty is not None:
        image_type = tags.get("ImageType")
        is_empty = image_type == ""
        if rule.image_type_empty != is_empty:
            return False

    if rule.image_type_any is not None:
        if not _match_image_type_any(rule.image_type_any, tags.get_list("ImageType")):
            return False

    if rule.manufacturer is not None:
        if not _match_field(rule.manufacturer, tags.get("Manufacturer")):
            return False

    if rule.manufacturer_model_name is not None:
        if not _match_field(rule.manufacturer_model_name, tags.get("ManufacturerModelName")):
            return False

    if rule.manufacturer_model_name_fallback is not None:
        manufacturer_model_name = tags.get("ManufacturerModelName")
        if manufacturer_model_name == "":
            if not _match_field(rule.manufacturer_model_name_fallback, manufacturer_model_name):
                return False

    if rule.modality is not None:
        if not _match_field(rule.modality, tags.get("Modality")):
            return False

    if rule.modality_not is not None:
        if _match_field(rule.modality_not, tags.get("Modality")):
            return False

    if rule.series_number is not None:
        if not _match_field(rule.series_number, tags.get("SeriesNumber")):
            return False

    if rule.conversion_type_present is not None:
        ct = tags.get("ConversionType")
        is_present = ct != ""
        if rule.conversion_type_present != is_present:
            return False

    if rule.image_type_exclude is not None:
        if not _match_image_type_exclude(rule.image_type_exclude, tags.get_list("ImageType")):
            return False

    return True


class DeviceCatalog:
    """Evaluates DICOM instances against a list of device rules and exclusions.

    Devices are checked in declaration order; the first matching rule wins for
    all actions ("allow", "deny", and "scrub"). A matching "allow" or "scrub"
    device short-circuits evaluation and skips the exclusion rules, so its scrub
    regions come only from the device that matched. Exclusion rules act as a
    last-chance filter, applied only to instances that match no device rule.

    Args:
        devices: Ordered list of DeviceRule entries.
        exclusions: List of ExclusionRule entries.
        default_action: Action when no device or exclusion matches.
    """

    def __init__(
        self,
        devices: list[DeviceRule],
        exclusions: list[ExclusionRule],
        default_action: str = "deny",
    ) -> None:
        """Initialize with device rules, exclusions, and a default action."""
        self._devices = devices
        self._exclusions = exclusions
        self._default_action = default_action

    @property
    def devices(self) -> list[DeviceRule]:
        """The ordered device rules."""
        return self._devices

    @property
    def exclusions(self) -> list[ExclusionRule]:
        """The exclusion rules."""
        return self._exclusions

    def _modality_has_devices(self, modality: str) -> bool:
        """Return True when any device rule explicitly targets *modality*.

        Device rules with an unconstrained (None) modality are ignored, so this
        reports whether the catalog has device support keyed to the modality.
        """
        if not modality:
            return False
        return any(rule.modality is not None and _match_field(rule.modality, modality) for rule in self._devices)

    def evaluate(self, tags: DicomTags) -> CatalogDecision:
        """Evaluate a DICOM instance against the catalog.

        Args:
            tags: Extracted DICOM tag values.

        Returns:
            A CatalogDecision with action, reason, and scrub regions.
        """
        near_miss_device: str | None = None

        for rule in self._devices:
            if not _match_device(rule, tags):
                continue

            # Determine the matched variant (if the device has variants)
            matched_variant: Variant | None = None
            variant_scrub: list[ScrubRegion] = []

            if rule.variants is not None:
                found = False
                for v in rule.variants:
                    if _match_variant(v, tags):
                        matched_variant = v
                        variant_scrub = list(v.scrub_regions)
                        found = True
                        break
                if not found:
                    # Device identity matched but no variant matched. When the
                    # device's variants constrain resolution, record the first
                    # such near-miss so a later modality-based denial can report
                    # the specific cause instead of a generic modality reason.
                    if near_miss_device is None and any(
                        v.rows is not None or v.cols is not None for v in rule.variants
                    ):
                        near_miss_device = rule.name
                    continue

            if rule.action == "allow":
                return CatalogDecision(
                    action="allow",
                    reason=rule.name,
                    scrub_regions=variant_scrub,
                    matched_variant=matched_variant,
                    preserved_private_tags=rule.preserved_private_tags,
                )

            if rule.action == "deny":
                return CatalogDecision(
                    action="deny",
                    reason=rule.name,
                    scrub_regions=[],
                    matched_variant=matched_variant,
                    preserved_private_tags=rule.preserved_private_tags,
                )

            if rule.action == "scrub":
                # A scrub device short-circuits like an allow: the instance is
                # kept and only this device's regions are blanked. Exclusion
                # rules are skipped because a device explicitly matched.
                return CatalogDecision(
                    action="scrub",
                    reason=rule.name,
                    scrub_regions=variant_scrub,
                    matched_variant=matched_variant,
                    preserved_private_tags=rule.preserved_private_tags,
                )

        for exclusion in self._exclusions:
            if _match_exclusion(exclusion, tags):
                reason = exclusion.reason
                is_modality_rule = exclusion.exact_modalities is not None or exclusion.substring_modalities is not None
                if is_modality_rule:
                    if near_miss_device is not None:
                        rows = tags.get("Rows") or "?"
                        cols = tags.get("Columns") or "?"
                        reason = f"Unsupported resolution {rows}x{cols} for device '{near_miss_device}'"
                    else:
                        modality = tags.get("Modality") or "(empty)"
                        if self._modality_has_devices(tags.get("Modality")):
                            # The catalog supports this modality family, but no
                            # device rule matched this instance. Surface the
                            # device identity so the cause is actionable.
                            mfr = tags.get("Manufacturer") or "(none)"
                            model = tags.get("ManufacturerModelName") or "(none)"
                            rows = tags.get("Rows") or "?"
                            cols = tags.get("Columns") or "?"
                            reason = (
                                f"Unsupported {modality} device: manufacturer='{mfr}', model='{model}', {rows}x{cols}"
                            )
                        else:
                            reason = f"Denied modality: {modality}"
                return CatalogDecision(
                    action="deny",
                    reason=reason,
                    scrub_regions=[],
                )

        return CatalogDecision(
            action=self._default_action,
            reason="No matching device or exclusion rule",
            scrub_regions=[],
        )
