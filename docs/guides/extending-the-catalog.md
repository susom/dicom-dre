# Extending the Catalog

This guide walks through adding support for a new imaging device to the device
catalog. The catalog data lives in the {py:mod}`dicom_dre.default_catalog` module;
the matching engine and factory functions live in {py:mod}`dicom_dre.catalog`.

:::{note}
This page is the how-to walkthrough. For the reference description of device
rules, variants, scrub-region coordinates, and evaluation order, see
[Device catalog](../concepts/device-catalog.md).
:::

## 1. Inspect a representative DICOM file

Read the tags the catalog matches on from a real instance the device produced.
`pydicom` is available in the project environment:

```python
import pydicom

ds = pydicom.dcmread("sample.dcm", stop_before_pixels=True)
for kw in (
    "Manufacturer", "ManufacturerModelName", "Modality",
    "SoftwareVersions", "ImageType", "Rows", "Columns",
    "SOPClassUID", "BurnedInAnnotation", "SeriesDescription",
):
    print(f"{kw:30} {ds.get(kw, '')!r}")
```

Collect several instances across the resolutions and software versions the
device produces. Devices frequently emit more than one image size, and each size
usually needs its own scrub region.

## 2. Choose the smallest set of identifying fields

Pick the fields that uniquely identify the device without over-constraining.
`manufacturer` + `modality` + `manufacturer_model_name` is the common baseline.
Add `software_versions`, `sop_class_uid`, or `image_type_exclude` only when
needed to separate this device from another rule or to exclude derived and
screenshot images.

Choose a match prefix per field (see
[String matching](../concepts/device-catalog.md#string-matching)):

- Use `^` (starts-with) for model families like `"^AXIOM"`.
- Use `=` (exact) when a substring would collide with another model, for
  example `"=S1000"` versus `"=S2000"`.
- Use a bare substring when you only care that the tag contains a known token
  and the surrounding text varies. For example, `"KONICA"` matches both
  `"KONICA"` and `"KONICA MINOLTA"`, so you do not have to enumerate every
  vendor string variation.
- Use `/regex/` for alternations or negative lookahead, for example
  `"/^(?!YES$)/"` to match any `BurnedInAnnotation` that is not exactly `YES`.

## 3. Determine scrub regions

If the device burns patient text into the pixels, identify the rectangles to
blank. Open a representative image, note the pixel bounds of each text banner,
and express them as `(x, y, width, height)` tuples using the
[coordinate system](../concepts/device-catalog.md#scrub-region-coordinates)
described in the concept page. Bind each set of regions to the resolution it
applies to with a `variant`.

If the device produces clean pixels (no burned-in text), omit `scrub`
entirely — the engine allows the device with no blanking.

## 4. Write the device entry

Add the entry to the modality-appropriate list in `default_catalog.py`
(`_cr_dx_devices`, `_ct_pet_devices`, `_nm_devices`, `_mammo_devices`,
`_breast_mri_devices`, `_us_devices`, or `_scrub_only_devices`). Order matters:
the first matching `allow` or `deny` device wins, so place a specific rule before
a more general one.

Single-resolution device with one scrub banner:

```python
device(
    "Acme UltraView 3000 US",
    "allow",
    manufacturer="Acme",
    modality="US",
    manufacturer_model_name="=UltraView 3000",
    sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
    requires_ultrasound_regions=True,
    rows=768,
    cols=1024,
    scrub=[(0, 0, 1024, 60)],
)
```

The `_US_SOP_SINGLE`, `_US_SOP_MULTI`, and `_US_SOP_SC` module constants are the
SOP Class UID prefixes for single-frame, multi-frame, and secondary-capture
ultrasound images. Ultrasound rules list the frame types they accept; other
modalities usually constrain `sop_class_uid` directly or omit it.

Multi-resolution device — one variant per image size:

```python
device(
    "Acme UltraView 3000 US",
    "allow",
    manufacturer="Acme",
    modality="US",
    manufacturer_model_name="=UltraView 3000",
    sop_class_uid=[f"^{_US_SOP_SINGLE}", f"^{_US_SOP_MULTI}"],
    variants=[
        variant(rows=768, cols=1024, scrub=[(0, 0, 1024, 60)]),
        variant(rows=600, cols=800, scrub=[(0, 0, 800, 48)]),
    ],
)
```

## 5. Handle a new modality

If the device belongs to a modality that the deny-list currently rejects, the
allow rule must be reachable before the exclusion. The engine always evaluates
device rules before exclusion rules, so an `allow` device for a denied modality
takes precedence. Confirm that no `deny_when` condition catches the modality
(for example the `SECONDARY`/`DERIVED` image-type denials) after the device
matches — those only run when no device rule returns `allow`.

To introduce an entirely new modality group, create a new
`list[DeviceRule]` (following the `_us_devices` pattern) and append it to
`default_devices` at the bottom of the file:

```python
default_devices: list[DeviceRule] = (
    _cr_dx_devices
    + _ct_pet_devices
    + ...
    + _new_modality_devices
    + _scrub_only_devices
)
```

## 6. Match a tag without a dedicated field

Every match attribute has a dedicated `device()` parameter; there is no
free-form keyword dict. If an attribute that has no parameter yet identifies the
device, add an explicit field:

1. Add the field to `DeviceRule`, the `device()` factory, and `_match_device()`
   in `catalog.py`, wiring it to the DICOM keyword via `_match_field`.
2. Add the keyword to the `keywords` list in `DicomTags.from_dataset()` so the
   extractor reads the value — otherwise the value is always empty and the match
   never succeeds. The regression fixtures capture exactly this keyword set, so
   an unextracted keyword also carries no regression coverage.

```python
device(
    "Acme Breast US",
    "allow",
    manufacturer="Acme",
    modality="US",
    body_part_examined="/(?i)^BREAST$/",
)
```

## 7. Add a test

Add a unit test to `tests/unit/test_default_catalog.py` that builds a
`DicomTags` from a plain dict and asserts the decision. This does not require a
DICOM file:

```python
def test_acme_ultraview_allows(self, catalog):
    tags = DicomTags(
        {
            "Manufacturer": "Acme",
            "Modality": "US",
            "ManufacturerModelName": "UltraView 3000",
            "SOPClassUID": "1.2.840.10008.5.1.4.1.1.6.1",
            "Rows": "768",
            "Columns": "1024",
            "SequenceOfUltrasoundRegions": "present",
        }
    )
    decision = catalog.evaluate(tags)
    assert decision.action == "allow"
    assert decision.scrub_regions == [ScrubRegion(0, 0, 1024, 60)]
```

Run the catalog tests:

```bash
uv run pytest tests/unit/test_default_catalog.py
```

## 8. Validate against real data

Run the catalog regression suite to confirm the new rule does not change the
recorded decision for any existing fixture:

```bash
uv run pytest tests/unit/test_catalog_regression_fixtures.py
```

The fixtures under `tests/unit/catalog_fixtures/` capture the technical matching
tags and the expected filter and scrub outcomes with no PHI or pixel data. If
the new device intentionally changes an outcome recorded in a fixture, update
the fixture to the corrected decision. Then run the full suite:

```bash
just test
```

For sites validating the shipped catalog against their own devices before
trusting output, see [Local validation](local-validation.md).
