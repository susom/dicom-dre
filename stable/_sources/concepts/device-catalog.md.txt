# Device Catalog

The device catalog is a Python module that unifies image filtering and pixel
scrubbing into a single, structured representation of known imaging devices.
Each entry identifies a specific hardware device by a set of DICOM attribute
patterns (manufacturer, model, modality, software version, image dimensions)
that match the images that device produces. The engine uses these patterns to
recognize those images and blank the pixel regions where the device burns in
text.

:::{note}
The bundled catalog comes from studies on a single PACS at one medical research
center. Its device rules and pixel scrub regions reflect the scanner fleet seen
there. They are unlikely to be complete or correct for another site. Treat the
included catalog as a starting point that requires local validation. See
[Limitations and portability](../about/limitations.md).
:::

## Goals

The device catalog is built on the following design choices:

1. **Model known devices, not arbitrary expressions.** Each entry matches a
   specific imaging device by manufacturer, model, modality, software version,
   and image dimensions. The rules read as data, not code.

2. **Couple resolution to scrub regions.** Each device entry contains
   resolution-specific variants that bind image dimensions directly to the
   pixel regions to blank. Each device defines its filter decision and its
   scrub regions together.

3. **Return a structured decision with a reason.** Every evaluation returns a
   `CatalogDecision` containing the action (`allow`, `deny`, `scrub`), a
   human-readable reason string, and the list of scrub regions. The reason
   propagates through the pipeline into the `FILTERED` result so callers can
   distinguish why a file was rejected.

4. **Validate at import time.** The catalog is a Python module. The interpreter
   catches syntax errors when it loads the module. It runs no runtime script
   parsing.

## Modules

| Module | Description |
|--------|-------------|
| {py:mod}`dicom_dre.catalog` | Core matching engine, dataclasses, `DeviceCatalog` |
| {py:mod}`dicom_dre.default_catalog` | Device and exclusion rule data |
| {py:mod}`dicom_dre.pixel_blanker` | Python pixel blanking (JPEG DCT + pydicom/numpy) |

## String matching

Pattern strings on device fields use a prefix to select the match operator.
All comparisons are case-insensitive except `/regex/` patterns, which are
case-sensitive unless the pattern includes an inline flag such as `(?i)`.

| Prefix | Operator | Example |
|--------|----------|---------|
| *(none)* | case-insensitive substring | `"KONICA"` |
| `=` | case-insensitive exact | `"=GE MEDICAL SYSTEMS"` |
| `^` | case-insensitive starts-with | `"^GE MEDICAL"` |
| `/regex/` | `re.search` (case-sensitive by default) | `"/[1-9]\\d{3,}/"` |
| `=` (alone) | tag absent or blank | `"="` |

A list of values on any field uses OR semantics: at least one must match.
All fields on a single device rule are AND'd together.

The `=` exact match compares the full value case-insensitively. A `/regex/`
pattern is evaluated with `re.search` and is case-sensitive unless the pattern
includes an inline flag such as `(?i)`. To match an exact value case-insensitively
with a regex (for example when you also need anchoring, alternation, or a
negative lookahead), anchor the pattern and add `(?i)`, as in
`"/(?i)^SIGNA PET\\/MR$/"`. This is why many regex rules in the default catalog
use the `/(?i)^...$/` form.

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
(unconstrained). A field constrains the match only when you specify it. Every
specified field is AND'd together: a device matches only when all of its
fields match. When you give a field a list, the list uses OR semantics.

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
| `variants` | n/a | List of resolution/version variants (see below) |
| `rows` / `cols` / `scrub` | `Rows` / `Columns` / n/a | Shorthand for a single-variant device |

Every match attribute has a dedicated field; there is no free-form keyword dict.
The catalog evaluates each field with the same [string matching](#string-matching)
rules. It matches only the attributes that `DicomTags.from_dataset()` reads.

The three `image_type*` fields match differently depending on whether the
pattern is a single string or a list. `ImageType` is a multi-valued tag stored
as backslash-joined components (for example `ORIGINAL\PRIMARY\AXIAL`). A list
value such as `image_type=["DERIVED", "PRIMARY"]` matches each element against
the individual components. The catalog matches a single string containing
backslashes such as `image_type="DERIVED\\PRIMARY\\DIXON\\WATER"` against the
full joined string, which lets you require a specific component order.

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
    image_type=["DERIVED"],   # ImageType components, all must appear
    scrub=[(x, y, w, h)],     # pixel regions to blank
)
```

A variant with only `scrub` (no rows/cols) applies those regions to all
resolutions. A variant with only rows/cols (no scrub) allows files at that
resolution without blanking.

When a device has variants, the evaluation finds the first variant whose
constraints match the DICOM file. If no variant matches, the engine skips the
device.

Skipping abandons the whole device rule, including its filter decision.
Evaluation continues to later device rules and then the exclusion list, which
commonly denies the file. As a result, every resolution you want allowed needs
its own variant, even one with no `scrub` regions (`variant(rows=780,
cols=800)`). The engine does not implicitly allow a resolution with no matching
variant.

### Scrub region coordinates

Scrub regions are `(x, y, width, height)` tuples in pixel units. The origin
`(0, 0)` is the top-left corner of the image. `x` increases to the right, `y`
increases downward. A region is the rectangle spanning columns `x` to
`x + width` and rows `y` to `y + height`.

Regions may extend past the image bounds; the pixel blanker clips to the actual
dimensions. The default catalog uses a wide sentinel width such as `10000` to
blank a full-width banner regardless of the exact column count (for example,
`scrub=[(0, 0, 10000, 70)]` blanks the top 70 rows). The blanker blanks multiple
regions on one variant independently:
`scrub=[(0, 0, 500, 80), (256, 0, 256, 22)]`.

### Scrub-only devices

A device with `action="scrub"` accumulates scrub regions but does not make a
filter decision. Evaluation continues to subsequent devices and exclusion rules
to determine whether the file is ultimately allowed or denied.

Scrub accumulation is forward-only. An earlier `scrub` device attaches its
regions to a later `allow` (or exclusion `deny`) decision, but not the reverse.
An `allow` or `deny` match returns immediately, so evaluation never reaches a
`scrub` device declared after it. Because `default_devices` appends
`_scrub_only_devices` last, its rules contribute only when no earlier device
returned `allow`. To apply a scrub-only overlay to a file that a specific device
already allows, add the scrub region to that device's variant instead of relying
on a later scrub-only rule.

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

## Exclusion rules

Exclusion rules form the deny-list. The engine checks them after all device
rules.

### `deny_modalities`

```python
deny_modalities(
    exact=["SR", "RTPLAN", "RTDOSE"],  # exact modality match
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
are: `sop_class`, `sop_class_not`, `burned_in_annotation`, `image_type_empty`,
`image_type_any`, `image_type_exclude`, `manufacturer`, `manufacturer_model_name`,
`manufacturer_model_name_fallback`, `modality`, `modality_not`,
`series_number`, `conversion_type_present`, `graphic_annotation_absent`,
`referenced_instance_absent`.

`sop_class_not` matches when the SOP Class UID matches none of its patterns
(an allowlist condition). `graphic_annotation_absent=True` matches when the
Graphic Annotation Sequence `(0070,0001)` is absent or empty.
`referenced_instance_absent=True` matches when the Current Requested Procedure
Evidence Sequence `(0040,A375)` nests no Referenced SOP Instance UID
`(0008,1155)`.

### Presentation state admission

Modality `PR` instances are admitted on the presence of a graphic annotation.
Two ordered `deny_when` rules implement this:

```python
deny_when(
    "unsupported presentation state",
    modality="=PR",
    sop_class_not=[
        "=1.2.840.10008.5.1.4.1.1.11.1",   # Grayscale (GSPS)
        "=1.2.840.10008.5.1.4.1.1.11.2",   # Color
        "=1.2.840.10008.5.1.4.1.1.11.3",   # Pseudo-Color
        "=1.2.840.10008.5.1.4.1.1.11.4",   # Blending
        "=1.2.840.10008.5.1.4.1.1.11.5",   # XA/XRF Grayscale
        "=1.2.840.10008.5.1.4.1.1.11.12",  # Variable Modality LUT
    ],
),
deny_when(
    "no annotation data",
    modality="=PR",
    graphic_annotation_absent=True,
),
```

A `PR` instance whose SOP Class UID is outside the six admitted 2D softcopy
presentation state classes is denied with reason `unsupported presentation
state`. An admitted-class `PR` instance carrying no Graphic Annotation Sequence
is denied with reason `no annotation data`. An admitted-class `PR` instance
with a non-empty Graphic Annotation Sequence reaches the default `allow`
action. The `Empty ImageType` exclusion is scoped with `modality_not=["=PR"]`
so it does not reject presentation states, which carry no Image Type.

### Key Object Selection admission

Key Object Selection (KO) documents, SOP Class
`1.2.840.10008.5.1.4.1.1.88.59`, are admitted on the presence of a referenced
instance. Two ordered `deny_when` rules replace the former single SR/KO deny:

```python
deny_when(
    "unsupported structured report",
    sop_class="^1.2.840.10008.5.1.4.1.1.8",
    sop_class_not=["=1.2.840.10008.5.1.4.1.1.88.59"],
),
deny_when(
    "no referenced instances",
    sop_class="=1.2.840.10008.5.1.4.1.1.88.59",
    referenced_instance_absent=True,
),
```

The first rule denies the SR family and the three non-SR classes caught by the
`^1.2.840.10008.5.1.4.1.1.8` prefix (Ophthalmic Visual Field, Ophthalmic
Thickness Map, Corneal Topography Map), while exempting KO. The second denies a
KO that references no instance with reason `no referenced instances`. A KO that
references at least one instance reaches the default `allow` action. The
`Empty ImageType` exclusion is scoped with `modality_not=["=PR", "=KO"]` so it
does not reject KO, which carries no Image Type.


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
```

The `reason` field receives the device `name` argument for device matches, or
a constructed string for exclusion matches (for example, `"Denied modality: XA"`).

## Default catalog

{py:mod}`dicom_dre.default_catalog` contains the device and exclusion rules. It
groups device rules by modality:

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
