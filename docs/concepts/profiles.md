# De-identification Profiles

A de-identification profile is an immutable set of tag-level rules plus global
flags that `dicom-dre` applies to instance metadata. Selecting a profile
determines which attributes are kept, removed, emptied, date-shifted, or
re-derived, and how free-text description fields are redacted.

`dicom-dre` ships four profiles: `default`, `lds`, `lds-no-dob`, and
`pixels-only`. The live list is returned by
{py:func}`dicom_dre.profiles.builder.list_profiles`.

| Profile | Preserve dates | Use case |
|---------|----------------|----------|
| `default` | No (dates shifted) | Standard full de-identification |
| `lds` | Yes | HIPAA limited data set with date/time retention |
| `lds-no-dob` | Yes, except birth date | Limited data set without patient date of birth |
| `pixels-only` | No (dates removed) | Pixel data only, minimal retained metadata |

A profile is constructed from a profile name and a runtime parameter dict by
{py:func}`dicom_dre.profiles.builder.build_profile`. The parameter dict is
consumed as-is: the library performs no hashing, no settings lookups, and no
free-text lookups. Callers supply already-hashed and already-redacted values.
See [Determinism](determinism.md).

## Default (full de-identification)

Profile name: `default`

The default profile applies DICOM PS3.15E basic de-identification with date
shifting. Date and datetime attributes are shifted by a per-patient jitter value
(the `JITTER` parameter, default 10 days). Patient birth date is shifted,
patient birth time is removed, and patient age is capped at 89 years (values at
or above the cap are replaced with `090Y`). UIDs are re-derived. Free-text
description fields are redacted against the allowlist, which also masks dates,
times, emails, URLs, and hexadecimal numbers. See [Text redaction](text-redaction.md).

| Attribute | Action |
|-----------|--------|
| StudyDate, SeriesDate, AcquisitionDate, ContentDate | Shifted by `JITTER` days |
| StudyTime, SeriesTime, AcquisitionTime, ContentTime | Kept |
| PatientBirthDate | Shifted by `JITTER` days |
| PatientBirthTime | Removed |
| PatientAge | Kept if under 89, otherwise replaced with `090Y` |
| Free-text fields | Dates and times masked by the redactor |

Use the default profile for standard research exports where temporal precision
is not required.

## LDS (limited data set)

Profile name: `lds`

The LDS profile produces a HIPAA limited data set. As used here, "limited data
set" refers to the preservation of dates and times, including birth dates. No
other information that HIPAA permits in a limited data set (such as geographic
data) is preserved; those attributes are removed as in the default profile.

Date, time, and datetime elements are kept unchanged. The profile inspects each
element's value representation at apply time: elements with VR `DA`, `DT`, or
`TM` are skipped and left intact. Patient birth date is kept. Patient age is
kept without the 89-year cap. The redactor is configured with
`preserve_dates=True`, so dates and times embedded in free-text fields are also
kept.

| Attribute | Action |
|-----------|--------|
| StudyDate, SeriesDate, AcquisitionDate, ContentDate | Kept |
| StudyTime, SeriesTime, AcquisitionTime, ContentTime | Kept |
| PatientBirthDate | Kept |
| PatientBirthTime | Kept |
| PatientAge | Kept (no 89-year cap) |
| Free-text fields | Dates and times preserved by the redactor |

Use the LDS profile when the downstream use case requires accurate temporal
information and a Data Use Agreement is in place.

## LDS no DOB

Profile name: `lds-no-dob`

Identical to the `lds` profile except that `PatientBirthDate` and
`PatientBirthTime` are removed instead of kept. These two tags are listed as
date-override tags, so the date-preservation skip does not apply to them and
their removal rule runs. All other date, time, and datetime attributes are kept,
and the redactor is configured with `preserve_dates=True`.

| Attribute | Action |
|-----------|--------|
| StudyDate, SeriesDate, AcquisitionDate, ContentDate | Kept |
| StudyTime, SeriesTime, AcquisitionTime, ContentTime | Kept |
| PatientBirthDate | Removed |
| PatientBirthTime | Removed |
| PatientAge | Kept (no 89-year cap) |
| Free-text fields | Dates and times preserved by the redactor |

Use this profile when the downstream use case requires temporal information but
the patient date of birth must not be included in the output.

## Pixels-only

Profile name: `pixels-only`

The pixels-only profile is the most aggressive metadata reduction that still
yields a file most DICOM viewers and libraries can open. It retains a fixed set
of technical elements, re-derives UIDs (no salt), and removes every element that
has no explicit rule. Groups `0028` (image pixel description) and `7FE0` (pixel
data), plus `SOPClassUID`, `SOPInstanceUID`, and `StudyInstanceUID`, are always
protected from the unspecified-element removal. Private groups, curves, and
overlays are removed.

Dates are removed entirely (they are neither kept nor shifted). Times are kept.
Free-text description fields are redacted with `preserve_dates=False`.

| Attribute | Action |
|-----------|--------|
| StudyTime, SeriesTime, AcquisitionTime, ContentTime | Kept |
| Date and datetime attributes | Removed |
| Free-text fields | Dates and times masked by the redactor |

Because required interchange elements may be removed, output is likely not
conformant to the DICOM specification. Use this profile only when the pixel data
is the sole item of interest.

## Text redaction

Each profile configures the redactor through its `preserve_dates` flag:

- `default` / `pixels-only`: dates, times, emails, URLs, and hexadecimal numbers
  are masked in free-text fields.
- `lds` / `lds-no-dob`: dates and times are kept intact; emails, URLs, and
  hexadecimal numbers are still masked.

The allowlist CSV is a property of each profile (`allowlist_csv`, default
`default.csv`). It controls which tokens are permitted in free-text fields. When
a caller supplies an explicit description value, it is written verbatim and no
redaction runs for that field. See [Text redaction](text-redaction.md).

## De-identification Method Code Sequence

When the pipeline preserves device-approved private tags (see
[Device Catalog](device-catalog.md)), the profile stamps the De-identification
Method Code Sequence `(0012,0064)`. The sequence is emitted only for instances
that actually retain private tags; other instances and profiles do not receive
it. Each item carries a code value `(0008,0100)`, the `DCM` coding scheme
designator `(0008,0102)`, and a code meaning `(0008,0104)`:

| Code value | Code meaning | Emitted |
|------------|--------------|---------|
| `113100` | Basic Application Confidentiality Profile | Whenever preservation is active |
| `113111` | Retain Safe Private Option | Whenever preservation is active |
| `113107` | Retain Longitudinal Temporal Information With Modified Dates | Only for date-shifting profiles (`default`); not for `lds`, `lds-no-dob`, or `pixels-only` |

The existing `DeIdentificationMethod` `(0012,0063)` free-text element is left
intact.

## API reference

The profile builder and its `build_profile` / `list_profiles` entry points are
documented in the [API Reference](../reference/api.md).

```{eval-rst}
.. automodule:: dicom_dre.profiles.builder
   :members:
   :no-index:
```
