# Device Catalog

The device catalog is a Python module that unifies image filtering and pixel
scrubbing into a single, structured representation of known imaging devices.
Each entry acts as a fingerprint for a specific hardware device: a set of DICOM
attribute patterns (manufacturer, model, modality, software version, image
dimensions) that together identify images produced by that device, so the
engine can recognize them and blank the pixel regions where that device burns
in text.

:::{note}
The bundled catalog was derived from studies on a single PACS at one medical
research center. Its device rules and pixel scrub regions reflect the scanner
fleet observed there and are unlikely to be complete or correct for another
site. Treat the shipped catalog as a starting point that requires local
validation. See [Provenance and portability](../about/provenance.md).
:::

## Goals

The device catalog is built on the following design choices:

1. **Model known devices, not arbitrary expressions.** Each entry is a
   fingerprint for a specific imaging device, described by manufacturer, model,
   modality, software version, and image dimensions. The rules read as data,
   not code.

2. **Couple resolution to scrub regions.** Each device entry contains
   resolution-specific variants that bind image dimensions directly to the
   pixel regions that must be blanked. A device's filter decision and its
   scrub regions are defined together.

3. **Return a structured decision with a reason.** Every evaluation returns a
   `CatalogDecision` carrying the action (`allow`, `deny`, `scrub`), a
   human-readable reason string, and the list of scrub regions. The reason
   propagates through the pipeline into the `FILTERED` result so callers can
   distinguish why a file was rejected.

4. **Validate at import time.** The catalog is a Python module. Syntax errors
   are caught when the interpreter loads it. No runtime script parsing is
   involved.

## Modules

| Module | Description |
|--------|-------------|
| {py:mod}`dicom_dre.catalog` | Core matching engine, dataclasses, `DeviceCatalog` |
| {py:mod}`dicom_dre.default_catalog` | Device and exclusion rule data |
| {py:mod}`dicom_dre.pixel_blanker` | Python pixel blanking (JPEG DCT + pydicom/numpy) |

## String matching

Pattern strings on device fields use a prefix to select the match operator.
All comparisons are case-insensitive unless the `=` prefix is used.

| Prefix | Operator | Example |
|--------|----------|---------|
| *(none)* | case-insensitive substring | `"KONICA"` |
| `=` | case-sensitive exact | `"=GE MEDICAL SYSTEMS"` |
| `^` | case-insensitive starts-with | `"^GE MEDICAL"` |
| `/regex/` | `re.search` | `"/[1-9]\\d{3,}/"` |
| `=` (alone) | tag absent or blank | `"="` |

A list of values on any field uses OR semantics — at least one must match.
All fields on a single device rule are AND'd together.

The `=` exact match is case-sensitive. Use it only when the device writes the
tag with stable casing. To match an exact value case-insensitively, use an
anchored regex with the `(?i)` flag instead — for example
`"/(?i)^SIGNA PET\\/MR$/"`. This is why many rules in the default catalog use
`/(?i)^...$/` rather than `=`.

## Device rules

Each device entry is created with the `device()` factory function:

```python
device(
    "KONICA 0402 CR",
    "allow",
    manufacturer="KONICA",
    modality="^CR",
    manufacturer_model_name="0402",
    variants=[
        variant(software_versions="^6.", rows=2446, cols=2446, scrub=[(0, 2308, 2446, 137)]),
        variant(software_versions="^2.", rows=2010, cols=2446, scrub=[(0, 0, 2446, 115)]),
    ],
)
```

The first positional argument is the device name, which becomes the `reason`
field of the returned `CatalogDecision`. The second positional argument is the
action: `"allow"`, `"deny"`, or `"scrub"`.

### Device rule fields

All keyword fields on `device()` are optional and default to `None`
(unconstrained). A field constrains the match only when specified. Every
specified field is AND'd together — a device matches only when all of its
fields match. When a field is given a list, the list uses OR semantics.

| Field | DICOM tag | Purpose |
|-------|-----------|---------|
| `manufacturer` | `Manufacturer` (0008,0070) | Vendor name |
| `modality` | `Modality` (0008,0060) | `CT`, `CR`, `DX`, `MR`, `US`, etc. |
| `manufacturer_model_name` | `ManufacturerModelName` (0008,1090) | Device model |
| `software_versions` | `SoftwareVersions` (0018,1020) | Firmware/software revision |
| `image_type` | `ImageType` (0008,0008) | All listed components must appear |
| `image_type_any` | `ImageType` (0008,0008) | At least one component must appear |
| `image_type_exclude` | `ImageType` (0008,0008) | None of the components may appear |
| `burned_in_annotation` | `BurnedInAnnotation` (0028,0301) | `YES`/`NO` flag |
| `sop_class_uid` | `SOPClassUID` (0008,0016) | SOP class UID pattern |
| `secondary_capture_device_manufacturer_model_name` | `SecondaryCaptureDeviceManufacturerModelName` (0018,1018) | SC device model (used by GE workstations) |
| `series_description` | `SeriesDescription` (0008,103E) | Free-text series label |
| `code_meaning` | `CodeMeaning` (0008,0104) | Coded concept meaning |
| `comments_on_radiation_dose` | `CommentsOnRadiationDose` (0040,0310) | Dose report text |
| `study_description` | `StudyDescription` (0008,1030) | Free-text study label |
| `conversion_type` | `ConversionType` (0008,0064) | Secondary-capture conversion type |
| `pixel_spacing` | `PixelSpacing` (0028,0030) | Physical pixel spacing |
| `body_part_examined` | `BodyPartExamined` (0018,0015) | Anatomic region |
| `requires_ultrasound_regions` | `SequenceOfUltrasoundRegions` (0018,6011) | When `True`, a non-empty regions sequence must be present |
| `variants` | — | List of resolution/version variants (see below) |
| `preserved_private_tags` | private data elements | Tuple of `PrivateTagSpec` for device-approved private elements to preserve verbatim (see below) |
| `rows` / `cols` / `scrub` | `Rows` / `Columns` / — | Shorthand for a single-variant device |

Every match attribute has a dedicated field; there is no free-form keyword dict.
Each field is evaluated with the same [string matching](#string-matching) rules.
Matching is limited to the attributes read by `DicomTags.from_dataset()`.

The three `image_type*` fields match differently depending on whether the
pattern is a single string or a list. `ImageType` is a multi-valued tag stored
as backslash-joined components (for example `ORIGINAL\PRIMARY\AXIAL`). A list
value such as `image_type=["DERIVED", "PRIMARY"]` matches each element against
the individual components. A single string containing backslashes such as
`image_type="DERIVED\\PRIMARY\\DIXON\\WATER"` is matched against the full joined
string, which lets you require a specific component order.

The `rows`, `cols`, and `scrub` shorthand parameters are mutually exclusive with
`variants`. Supplying both raises `ValueError` at import time. Use the shorthand
for a device with a single resolution; use `variants` for a device with multiple
resolutions or software versions.

### Variants

A variant binds a resolution (rows, cols) or software version to a set of scrub
regions. All fields in a variant are optional. A device with no variants has no
dimension constraint.

```python
variant(
    rows=2446,           # exact Rows match
    cols=2446,           # exact Columns match
    software_versions="^6.",  # further narrows the device-level version
    image_type=["DERIVED"],   # ImageType components — all must appear
    scrub=[(x, y, w, h)],     # pixel regions to blank
)
```

A variant with only `scrub` (no rows/cols) applies those regions to all
resolutions. A variant with only rows/cols (no scrub) allows files at that
resolution without blanking.

When a device has variants, the evaluation finds the first variant whose
constraints match the DICOM file. If no variant matches, the device is skipped.

Skipping means the whole device rule is abandoned, including its filter
decision — evaluation continues to later device rules and then the exclusion
list, where the file is commonly denied. As a result, every resolution you want
allowed needs its own variant, even one with no `scrub` regions
(`variant(rows=780, cols=800)`). A resolution with no matching variant is not
implicitly allowed.

### Scrub region coordinates

Scrub regions are `(x, y, width, height)` tuples in pixel units. The origin
`(0, 0)` is the top-left corner of the image. `x` increases to the right, `y`
increases downward. A region is the rectangle spanning columns `x` to
`x + width` and rows `y` to `y + height`.

```
   (0,0) ─────────── x increases ──────────▶  Columns
     ┌──────────────────────────────────────┐
     │  (x, y)                               │
     │    ┌───── width ─────┐                │
   y │    │                 │ height         │
     │    └─────────────────┘                │
     ▼                                       │
  Rows └──────────────────────────────────────┘
```

Regions may extend past the image bounds; the pixel blanker clips to the actual
dimensions. A wide sentinel width such as `10000` is used in the default catalog
to blank a full-width banner regardless of the exact column count (for example,
`scrub=[(0, 0, 10000, 70)]` blanks the top 70 rows). Multiple regions on one
variant are blanked independently:
`scrub=[(0, 0, 500, 80), (256, 0, 256, 22)]`.

### Scrub-only devices

A device with `action="scrub"` accumulates scrub regions but does not make a
filter decision. Evaluation continues to subsequent devices and exclusion rules
to determine whether the file is ultimately allowed or denied.

Scrub accumulation is forward-only: regions collected by an earlier `scrub`
device are attached to a later `allow` (or exclusion `deny`) decision, but not
the reverse. An `allow` or `deny` match returns immediately, so any `scrub`
device declared after it is never reached. Because `_scrub_only_devices` is
appended last in `default_devices`, its rules only contribute when no earlier
device returned `allow`. If a scrub-only overlay needs to apply to a file that a
specific device already allows, add the scrub region to that device's variant
instead of relying on a later scrub-only rule.

```python
device(
    "Siemens CT Dose overlay",
    "scrub",
    manufacturer="SIEMENS",
    modality="CT",
    image_type_any=["DOSE"],
    scrub=[(0, 0, 512, 30)],
)
```

### Preserved private tags

Some devices carry private data elements that a reviewer has approved as safe to
retain verbatim. The `preserved_private_tags` field on `device()` takes a tuple
of `PrivateTagSpec` entries. Each spec names a private group, a private-creator
string, and the element offsets (low byte) to keep within that creator's block:

```python
from dicom_dre.catalog import PrivateTagSpec

device(
    "GE SIGNA Premier MR - preserved private tags",
    "allow",
    manufacturer="=GE MEDICAL SYSTEMS",
    modality="=MR",
    manufacturer_model_name="/(?i)^SIGNA Premier$/",
    burned_in_annotation="/^(?!YES$)/",
    image_type=["ORIGINAL", "PRIMARY"],
    image_type_exclude="MRSC",
    sop_class_uid="^1.2.840.10008.5.1.4.1.1.4",
    conversion_type="=",
    preserved_private_tags=(
        PrivateTagSpec(group=0x0019, creator="GEMS_ACQU_01", offsets=(0xBB, 0xBC, 0xBD)),
        PrivateTagSpec(group=0x0043, creator="GEMS_PARM_01", offsets=(0x2F,)),
    ),
)
```

The private-creator block (`xx` in `(gggg,xxnn)`) is not fixed. At de-identify
time the engine resolves the block by locating the creator element in the group
whose value equals the spec's `creator`, then keeps both the resolved data
elements and their creator element. Every other private element is removed as
usual.

Because a device match short-circuits the entire exclusion pass, a rule that
carries `preserved_private_tags` acts as an admission gate and must reproduce
inline the guards that the bypassed exclusions would otherwise enforce
(`burned_in_annotation`, `image_type`, `image_type_exclude`, `sop_class_uid`,
and `ConversionType` above). When preservation is active the engine also emits
the De-identification Method Code Sequence `(0012,0064)` with the Retain Safe
Private Option; see [Profiles](profiles.md).

## Exclusion rules

Exclusion rules form the deny-list. They are checked after all device rules.

### `deny_modalities`

```python
deny_modalities(
    exact=["PR", "KO", "SR"],          # exact modality match
    substring=["XA", "MG", "US"],      # substring modality match
)
```

### `deny_when`

```python
deny_when("Burned-in annotation", burned_in_annotation="=YES")
deny_when("Encapsulated PDF", sop_class="=1.2.840.10008.5.1.4.1.1.104.1")
deny_when("INFINITT PACS", manufacturer="INFINITT", series_number="/[1-9]\\d{3,}/")
```

All keyword arguments to `deny_when` are AND'd together. Available parameters
are: `sop_class`, `burned_in_annotation`, `image_type_empty`, `image_type_any`,
`image_type_exclude`, `manufacturer`, `manufacturer_model_name`,
`manufacturer_model_name_fallback`, `modality`, `modality_not`,
`series_number`, `conversion_type_present`.

## Evaluation order

1. Iterate device rules top-to-bottom. For each rule, check device-level fields,
   then check variants.
2. On first match:
    - `"allow"`: return allow decision with accumulated scrub regions, stop.
    - `"deny"`: return deny decision, stop.
    - `"scrub"`: accumulate scrub regions, continue.
3. After all devices, iterate exclusion rules top-to-bottom.
4. On first exclusion match, return deny decision.
5. If nothing matched, return the default action (`"allow"` for the default catalog).

## CatalogDecision

Every call to `DeviceCatalog.evaluate()` returns a frozen `CatalogDecision`:

```python
@dataclass(frozen=True, slots=True)
class CatalogDecision:
    action: str                              # "allow", "deny", or "scrub"
    reason: str                              # matched rule name or exclusion reason
    scrub_regions: list[ScrubRegion]         # (x, y, w, h) regions to blank
    matched_variant: Variant | None          # the variant that matched, if any
    preserved_private_tags: tuple[PrivateTagSpec, ...]  # private specs to preserve
```

The `reason` field receives the device `name` argument for device matches, or
a constructed string for exclusion matches (for example, `"Denied modality: XA"`).

## Default catalog

{py:mod}`dicom_dre.default_catalog` contains the device and exclusion rules. Device
rules are grouped by modality:

- CR/DX (computed radiography and digital radiography)
- CT, CT/PET, PET/MR
- NM (nuclear medicine)
- Mammography
- Breast MRI
- Ultrasound
- Scrub-only devices (dose overlays and workstation-generated images)

The exclusion list covers denied modalities, SOP classes, burned-in annotations,
empty ImageType, specific vendors (INFINITT, Vidar, iCAD, biopsy equipment),
and image type combinations (`DERIVED`, `SECONDARY`, `MRSC`).

`get_default_catalog()` assembles all device lists and the exclusion list into a
`DeviceCatalog` with `default_action="allow"`.

For a step-by-step walkthrough of adding support for a new device, see
[Extending the catalog](../guides/extending-the-catalog.md).
