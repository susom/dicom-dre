# Architecture

`dicom-dre` is a pure-Python DICOM de-identification engine. It filters images,
blanks burned-in pixel regions, and rewrites metadata tags. For each input file
it produces one of three outcomes by running three stages in sequence.

## Overview

For each input DICOM file the engine runs three stages:

1. **Filter** — a device catalog decides whether the image is kept or rejected.
2. **Pixel scrub** — burned-in text regions identified by the catalog are
   blanked.
3. **Metadata** — DICOM tags are rewritten (PHI removed, UIDs re-derived, dates
   shifted or kept).

Each run returns a {py:class}`~dicom_dre.result.DeidentifyResult` whose `outcome`
is one of three {py:class}`~dicom_dre.result.Outcome` values:

| Outcome | Cause |
|---------|-------|
| `DEIDENTIFIED` | The file passed the filter and was written out. |
| `FILTERED` | A device or exclusion rule rejected the file; the result carries the matched reason. |
| `QUARANTINED` | Processing raised an exception; the result carries the error text. |

## Pipeline

Every de-identification call enters through
{py:func}`dicom_dre.pipeline.deidentify_file`, which composes the three stages and
returns a `DeidentifyResult`.

```{mermaid}
flowchart LR
    A["PHI DICOM"] --> F{"Filter<br>catalog.evaluate()"}
    F -->|deny| X["FILTERED<br>(+ reason)"]
    F -->|allow / scrub| S["Pixel scrub<br>blank_regions()"]
    S --> M["Metadata<br>profile.apply()"]
    M --> O["DEIDENTIFIED"]
    F -.->|exception| Q["QUARANTINED"]
```

An exception raised in any stage is caught by `deidentify_file` and returned as
a `QUARANTINED` result rather than propagating to the caller.

## Stages

### Filter

`catalog.evaluate(DicomTags.from_file(path))` returns a
{py:class}`~dicom_dre.catalog.CatalogDecision` with an action (`allow`, `deny`, or
`scrub`), a human-readable reason, and a list of scrub regions. A `deny` action
stops the pipeline and produces a `FILTERED` result whose `filter_reason` is the
matched rule. Catalog evaluation reads tags directly with pydicom.

See [Device Catalog](device-catalog.md).

### Pixel scrub

When the decision carries scrub regions,
{py:func}`dicom_dre.pixel_blanker.blank_regions` blanks them. JPEG Baseline images
are edited directly in the compressed bitstream with no re-encoding; all other
transfer syntaxes are decoded with pydicom and numpy, blanked, and written as
uncompressed Explicit VR Little Endian.

See [JPEG DCT Scrubbing](jpeg-dct.md).

### Metadata

The bound {py:class}`~dicom_dre.profile.DeidProfile` runs its tag rules on the
dataset with `DeidProfile.apply(ds)`. Rules are small closures defined in
{py:mod}`dicom_dre.actions` (for example `remove`, `empty`, `hash_uid`,
`jitter_date`, `keep`); the tag sets each profile applies them to are composed
by the profile factories in {py:mod}`dicom_dre.profiles`.

Each factory in `actions.py` closes over its arguments at profile-construction
time and returns a `(Dataset, BaseTag) -> None` callable. The available actions:

| Action | Effect |
|--------|--------|
| `keep()` | Leave the element unchanged. |
| `remove()` | Delete the element from the dataset. |
| `empty()` | Replace the value with a zero-length value (empty list for `SQ`). |
| `set_value(value, create_if_missing=False)` | Replace the value with a literal string, optionally creating the element when absent. |
| `redact_text(redactor)` | Redact a free-text element token-by-token against an allowlist. |
| `hash_uid(root, salt="")` | Re-derive a UID as an MD5 hash under `root`, optionally salted. |
| `jitter_date(days)` | Shift the `DA`/`DT` date component forward by `days`, preserving any time/timezone remainder. |
| `append_value(text, create_if_missing=False)` | Append `text` to a multi-valued element using `\` as separator. |
| `cap_age(threshold, replacement)` | Replace an `AS` age when its numeric part exceeds `threshold`. |
| `if_exists(inner)` | Apply `inner` only when the element is present. |
| `process()` | Mark an `SQ` element for recursive rule application by `DeidProfile`. |

Profiles compose these actions rather than parsing a script.

### Device-scoped private-tag preservation

By default the engine removes every private data element that has no explicit
tag rule. A device rule may name a small, reviewer-approved set of private
elements to retain verbatim through its `preserved_private_tags` field (a tuple
of `PrivateTagSpec`). When the catalog decision carries specs, the pipeline
attaches them to the `DeidProfile`, and `DeidProfile.apply(ds)` resolves each
spec's private-creator block at apply time (the block is runtime-assigned, not
fixed) and keeps both the resolved data elements and their creator element. All
other private elements are removed as usual. When preservation is active the
engine also stamps the De-identification Method Code Sequence `(0012,0064)` with
the Retain Safe Private Option; the sequence is emitted only for files that
actually preserve private tags.

See [Device Catalog](device-catalog.md#preserved-private-tags) and
[Profiles](profiles.md).

## Profiles

The `default`, `lds`, `lds-no-dob`, and `pixels-only` profiles each map to a
factory function in {py:mod}`dicom_dre.profiles`. A profile name selects which tags
are kept, removed, or shifted. The behavior of each profile is described in
[Profiles](profiles.md).

## Regression validation

A regression fixture suite guards catalog and metadata behavior against known
inputs. Each fixture pins the expected filter decision, scrub decision, scrub
regions, and de-identified metadata for a representative instance, so a change
that alters any of them is caught in the test run. The fixtures live in
`tests/unit/test_catalog_regression_fixtures.py`.

See [Testing](../about/testing.md).

## Extending

- To allow or deny a new device, or to blank a new pixel region, add a `device()`
  entry to {py:mod}`dicom_dre.default_catalog`. See
  [Extending the catalog](../guides/extending-the-catalog.md).
- To change a tag rule or add a profile, compose actions in
  {py:mod}`dicom_dre.profiles`, deriving from an existing profile with
  `dataclasses.replace`.

## Module reference

| Module | Responsibility |
|--------|----------------|
| {py:mod}`dicom_dre.pipeline` | Orchestrator: composes the three stages into a `DeidentifyResult` |
| {py:mod}`dicom_dre.result` | `DeidentifyResult` and `Outcome` result types |
| {py:mod}`dicom_dre.profile` | `DeidProfile.apply()` metadata rewrite |
| {py:mod}`dicom_dre.actions` | Tag-action factories (`remove`, `hash_uid`, `jitter_date`, ...) |
| {py:mod}`dicom_dre.profiles` | `default`, `lds`, `lds-no-dob`, `pixels-only` factories and the profile builder |
| {py:mod}`dicom_dre.catalog` | Catalog engine: `DeviceCatalog`, `CatalogDecision`, `DicomTags` |
| {py:mod}`dicom_dre.default_catalog` | Device and exclusion rule data |
| {py:mod}`dicom_dre.pixel_blanker` | `blank_regions()` pixel scrub dispatch |
| {py:mod}`dicom_dre.jpeg_dct_scrubber` | DCT-domain JPEG blanking and C accelerator |
