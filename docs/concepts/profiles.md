# De-identification Profiles

A de-identification profile is an immutable set of tag-level rules plus global
flags that `dicom-dre` applies to instance metadata. The profile you select
determines which attributes the engine keeps, removes, empties, date-shifts, or
re-derives, and how it redacts free-text description fields.

`dicom-dre` includes four profiles: `default`, `lds`, `lds-no-dob`, and
`pixels-only`. {py:func}`dicom_dre.profiles.builder.list_profiles` returns the
authoritative list.

| Profile | Preserve dates | Use case |
|---------|----------------|----------|
| `default` | No (dates shifted) | Standard full de-identification |
| `lds` | Yes | HIPAA limited data set with date/time retention |
| `lds-no-dob` | Yes, except birth date | Limited data set without patient date of birth |
| `pixels-only` | No (dates removed) | Pixel data only, minimal retained metadata |

{py:func}`dicom_dre.profiles.builder.build_profile` constructs a
patient-invariant profile from a profile name and an optional
{py:class}`dicom_dre.profiles.config.ProfileSettings` (its `uid_root`,
`allowlist_csv`, and `hash_salt` fields). Per-patient identity values
(PatientID, AccessionNumber, StudyID, PatientName, the free-text description
overrides, and the date jitter) are supplied at apply time via
{py:class}`dicom_dre.parameters.DeidParameters`, not to `build_profile`. A single
profile is reusable across any number of patients. When a caller supplies a
replacement PatientID, PatientName, or AccessionNumber the engine writes it
verbatim. When it does not, the engine derives the replacement by hashing the
original element value (SHA-256, salted with the `ProfileSettings.hash_salt` value
and the study identifier, truncated to 16 uppercase hex characters), reusing the
PatientID hash for PatientName. It falls back to `[REDACTED]` only when there is
no value to hash. It re-derives UIDs by deterministic hashing (the UID root and
the study-ID salt). It performs no identifier-mapping lookups, no settings
lookups, and no network calls, so the same profile and parameters always produce
the same output. See [Reproducibility](reproducibility.md).

## Default (full de-identification)

Profile name: `default`

The default profile applies DICOM PS3.15E basic de-identification with date
shifting. It shifts date and datetime attributes by a per-patient jitter value
(the `JITTER` parameter). When `JITTER` is not supplied, the shift is derived
deterministically from the hash salt, the study identifier, and the original
(PHI) PatientID, yielding a non-zero value in the range -30 to +30 days. The same
patient within a study always shifts by the same amount (longitudinal
consistency), while the same patient in a different study shifts differently. It
shifts patient birth date, removes patient birth time, and caps patient age at 89
years (it replaces values at or above the cap with `090Y`). It re-derives UIDs.
It redacts free-text description fields against the allowlist, which also masks
dates, times, emails, URLs, and hexadecimal numbers. See
[Text redaction](text-redaction.md).

| Attribute | Action |
|-----------|--------|
| StudyDate, SeriesDate, AcquisitionDate, ContentDate | Shifted by the jitter (`JITTER`, or the derived per-patient/study shift) |
| StudyTime, SeriesTime, AcquisitionTime, ContentTime | Kept |
| PatientBirthDate | Shifted by the jitter (`JITTER`, or the derived per-patient/study shift) |
| PatientBirthTime | Removed |
| PatientAge | Kept if under 89, otherwise replaced with `090Y` |
| Free-text fields | Dates and times masked by the redactor |

Use the default profile for standard research exports where temporal precision
is not required.

## LDS (limited data set)

Profile name: `lds`

The LDS profile produces a HIPAA limited data set. Here, "limited data set"
refers to keeping dates and times, including birth dates. The profile preserves
no other information that HIPAA permits in a limited data set (such as geographic
data); it removes those attributes as in the default profile.

The profile keeps date, time, and datetime elements unchanged. At apply time, it
inspects each element's value representation: it skips and leaves intact elements
with VR `DA`, `DT`, or `TM`. It keeps patient birth date. It keeps patient age
without the 89-year cap. It configures the redactor with `preserve_dates=True`,
so dates and times embedded in free-text fields are also kept.

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

Identical to the `lds` profile except that it removes `PatientBirthDate` and
`PatientBirthTime` instead of keeping them. These two tags are date-override
tags, so the date-preservation skip does not apply to them and their removal
rule runs. The profile keeps all other date, time, and datetime attributes and
configures the redactor with `preserve_dates=True`.

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

The pixels-only profile retains the least metadata while still yielding a file
that most DICOM viewers and libraries can open. It retains a fixed set
of technical elements, re-derives UIDs (no salt), and removes every element that
has no explicit rule. It always protects groups `0028` (image pixel description)
and `7FE0` (pixel data), plus `SOPClassUID`, `SOPInstanceUID`, and
`StudyInstanceUID`, from the unspecified-element removal. It removes private
groups, curves, and overlays.

It removes dates entirely (neither kept nor shifted). It keeps times. It redacts
free-text description fields with `preserve_dates=False`.

| Attribute | Action |
|-----------|--------|
| StudyTime, SeriesTime, AcquisitionTime, ContentTime | Kept |
| Date and datetime attributes | Removed |
| Free-text fields | Dates and times masked by the redactor |

Because the profile may remove required interchange elements, the output is
likely not conformant to the DICOM specification. Use this profile only when the
pixel data is the sole item of interest.

## Text redaction

Each profile configures the redactor through its `preserve_dates` flag:

- `default` / `pixels-only`: dates, times, emails, URLs, and hexadecimal numbers
  are masked in free-text fields.
- `lds` / `lds-no-dob`: dates and times are kept intact; emails, URLs, and
  hexadecimal numbers are still masked.

The allowlist CSV is a property of each profile (`allowlist_csv`, default
`default.csv`). It controls which tokens may appear in free-text fields. When a
caller supplies an explicit description value, the engine writes it verbatim and
runs no redaction for that field. See [Text redaction](text-redaction.md).

## De-identification Method Code Sequence

When the pipeline preserves device-approved private tags (see
[Device Catalog](device-catalog.md)), the profile stamps the De-identification
Method Code Sequence `(0012,0064)`. The profile emits the sequence only for
instances that actually retain private tags; other instances and profiles do not
receive it. Each item contains a code value `(0008,0100)`, the `DCM` coding
scheme designator `(0008,0102)`, and a code meaning `(0008,0104)`:

| Code value | Code meaning | Emitted |
|------------|--------------|---------|
| `113100` | Basic Application Confidentiality Profile | Whenever preservation is active |
| `113111` | Retain Safe Private Option | Whenever preservation is active |
| `113107` | Retain Longitudinal Temporal Information With Modified Dates | Only for date-shifting profiles (`default`); not for `lds`, `lds-no-dob`, or `pixels-only` |

The profile leaves the existing `DeIdentificationMethod` `(0012,0063)` free-text
element intact.

## API reference

The profile builder and its `build_profile` / `list_profiles` entry points are
documented in the [API Reference](../reference/api.md).

```{eval-rst}
.. automodule:: dicom_dre.profiles.builder
   :members:
   :no-index:
```
