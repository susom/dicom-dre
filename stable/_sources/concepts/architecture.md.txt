# Architecture

`dicom-dre` is a pure-Python DICOM de-identification engine. It filters images,
blanks burned-in pixel regions, and rewrites metadata tags. For each input file
it produces one of three outcomes by running three stages in sequence.

## Overview

For each input DICOM file the engine runs three stages:

1. **Filter**: a device catalog decides whether to keep or reject the image.
2. **Pixel scrub**: the engine blanks the burned-in text regions the catalog
   identified. When it blanks a region, it sets `BurnedInAnnotation` (0028,0301)
   to `NO` and records the Clean Pixel Data Option `113101` in the
   De-identification Method Code Sequence for that instance.
3. **Metadata**: the engine rewrites DICOM tags: it removes PHI, re-derives
   UIDs, and shifts or keeps dates.

Each run returns a {py:class}`~dicom_dre.result.DeidentifyResult` whose `outcome`
is one of three {py:class}`~dicom_dre.result.Outcome` values:

| Outcome | Cause |
|---------|-------|
| `DEIDENTIFIED` | The file passed the filter, and the engine wrote it out. |
| `FILTERED` | A device or exclusion rule rejected the file; the result contains the matched reason. |
| `QUARANTINED` | Processing raised an exception; the result contains the error text. |

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

An exception raised in any stage does not propagate to the caller.
`deidentify_file` catches it and returns a `QUARANTINED` result instead.

## Stages

### Filter

`catalog.evaluate(DicomTags.from_file(path))` returns a
{py:class}`~dicom_dre.catalog.CatalogDecision` with an action (`allow`, `deny`, or
`scrub`), a human-readable reason, and a list of scrub regions. A `deny` action
stops the pipeline and produces a `FILTERED` result whose `filter_reason` is the
matched rule. Catalog evaluation reads tags directly with pydicom.

See [Device Catalog](device-catalog.md).

### Pixel scrub

When the decision contains scrub regions,
{py:func}`dicom_dre.pixel_blanker.blank_regions` blanks them. The engine edits
JPEG Baseline images directly in the compressed bitstream with no re-encoding.
For all other transfer syntaxes, it decodes with pydicom and numpy, blanks the
regions, and writes uncompressed Explicit VR Little Endian.

See [JPEG DCT Scrubbing](jpeg-dct.md).

### Metadata

The bound {py:class}`~dicom_dre.profile.DeidProfile` runs its tag rules on the
dataset with `DeidProfile.apply(ds, params)`, where `params` is a
{py:class}`~dicom_dre.parameters.DeidParameters` containing the per-patient values.
Rules are small closures defined in
{py:mod}`dicom_dre.actions` (for example `remove`, `empty`, `hash_uid`,
`jitter_date`, `keep`). The profile factories in {py:mod}`dicom_dre.profiles`
compose the tag sets each profile applies them to.

Each factory in `actions.py` closes over its build-time arguments at
profile-construction time and returns a
`(Dataset, BaseTag, DeidParameters) -> None` callable that reads per-patient
values from the supplied parameters. The available actions:

| Action | Effect |
|--------|--------|
| `keep()` | Leave the element unchanged. |
| `remove()` | Delete the element from the dataset. |
| `empty()` | Replace the value with a zero-length value (empty list for `SQ`). |
| `set_value(value, create_if_missing=False)` | Replace the value with a literal string, optionally creating the element when absent. |
| `set_param(field, default=None, fallback_field=None, create_if_missing=False)` | Write a per-patient value read from `DeidParameters`, with fallbacks. |
| `hash_identifier_param(field, salt, fallback_field=None, source_tag=None)` | Write a caller-supplied identifier verbatim, otherwise hash the original element value (salted with `salt` and the study identifier); write `[REDACTED]` when there is nothing to hash. |
| `hash_uid(root, use_study_salt=False)` | Re-derive a UID as an MD5 hash under `root`, optionally salted with the study identifier. |
| `jitter_date()` | Shift the `DA`/`DT` date component forward by `params.jitter` days, preserving any time/timezone remainder; the profile resolves an unset jitter to a deterministic per-patient, per-study amount before rules run. |
| `append_value(text, create_if_missing=False)` | Append `text` to a multi-valued element using `\` as separator. |
| `cap_age(threshold, replacement)` | Replace an `AS` age when its numeric part exceeds `threshold`. |
| `if_exists(inner)` | Apply `inner` only when the element is present. |

Profiles compose these actions rather than parsing a script.

### Private-tag preservation

By default the engine removes every private data element that has no explicit
tag rule. A profile declares a reviewer-approved set of private elements to
retain verbatim through its `preserved_private_specs` field (a frozenset of
`PrivateTagSpec`), keyed on the private-creator string. At apply time,
`DeidProfile.apply(ds, params)` resolves each spec's private-creator block (the
block is runtime-assigned, not fixed) and keeps both the resolved data elements
and their creator element. The engine removes all other private elements as
usual.

An offset in a spec may be wrapped in `Jitter`. A `Jitter`-flagged offset is
resolved and kept like any preserved offset, and its `DA`/`DT` value is then
shifted by the same per-study jitter applied to standard date tags. The shift
runs after the element rules and recurses into sequence items. For a
date-preserving profile the jitter is unset, so a flagged value is left
unchanged. The `default` profile flags `PulseSequenceDate (0019,xx9D)` in the
`GEMS_ACQU_01` block; `strict` inherits the same specs.

The `default` profile declares the specs; `lds` and `lds-no-dob` inherit
them, and `strict` declares the same set. The engine stamps the
De-identification Method Code Sequence `(0012,0064)` on every de-identified
instance; it adds the Retain Safe Private Option item `113111` only when the
profile removes private groups (`remove_private`) and the instance retains at
least one preserved private element. A profile that keeps all private elements
does not emit `113111`, since that is not the selective safe private option.

See [Profiles](profiles.md).

## Profiles

The `default`, `lds`, `lds-no-dob`, and `strict` profiles each map to a
factory function in {py:mod}`dicom_dre.profiles`. A profile name selects which
tags the engine keeps, removes, or shifts. [Profiles](profiles.md) describes the
behavior of each profile.

## Regression validation

A regression fixture suite guards catalog and metadata behavior against known
inputs. Each fixture pins the expected filter decision, scrub decision, scrub
regions, and de-identified metadata for a representative instance, so the test
run catches a change that alters any of them. The fixtures reside in
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
| {py:mod}`dicom_dre.profiles` | `default`, `lds`, `lds-no-dob`, `strict` factories and the profile builder |
| {py:mod}`dicom_dre.catalog` | Catalog engine: `DeviceCatalog`, `CatalogDecision`, `DicomTags` |
| {py:mod}`dicom_dre.default_catalog` | Device and exclusion rule data |
| {py:mod}`dicom_dre.pixel_blanker` | `blank_regions()` pixel scrub dispatch |
| {py:mod}`dicom_dre.jpeg_dct_scrubber` | DCT-domain JPEG blanking and C accelerator |
