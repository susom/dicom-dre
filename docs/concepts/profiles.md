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

Reference sequences (Referenced Series Sequence `(0008,1115)`, Referenced
Image Sequence `(0008,1140)`, and Referenced Instance Sequence `(0008,114A)`)
are retained rather than removed. The engine applies the tag rules recursively
into the item datasets of every sequence at every depth, so a nested UID that is
in the UID-hash set (for example `ReferencedSOPInstanceUID` or
`SeriesInstanceUID`) is hashed while a UID that is not (for example
`ReferencedSOPClassUID (0008,1150)` and Transfer Syntax UID) is left unchanged.
Hashing is keyed on the tag, not the VR, so registered class and transfer-syntax
UIDs are never hashed. Recursion into every sequence is engine behavior shared by
all profiles; retaining the reference sequences (omitting them from the removal
set) is a property of the `default`, `lds`, and `lds-no-dob` profiles.

A UID fallback catches identifier UIDs that no explicit rule covers. For a `UI`
element with no more-specific rule, the value is hashed unless it is under the
DICOM root `1.2.840.10008.`, which is reserved for registered values (SOP Class,
Transfer Syntax, coding scheme, well-known SOP instance) and is left unchanged.
The fallback uses the same UID root and study-salt policy as the explicit UID
rules, so a UID that appears both under an explicit rule and an unruled tag maps
to the same replacement and cross-references stay consistent. The `default`,
`lds`, and `lds-no-dob` profiles hash with the study salt; the `pixels-only`
profile hashes without it.

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

Because the profile preserves dates, it rejects a non-zero `JITTER`: supplying
a non-zero `JITTER` with `lds` (or any date-preserving profile) is a usage error
rather than a silently ignored value. `JITTER=0` requests no shift and is
accepted and inert.

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

## Graphic annotation subtree

The `default` profile admits 2D softcopy presentation states and retains their
Graphic Annotation Sequence `(0070,0001)`. The sequence is absent from the
removal set, so the engine keeps it and recurses into its items like any other
sequence. Because the module is fully specified (DICOM PS3.3 C.10.5), every
attribute is handled by an explicit rule or by the bulk rules:

- The two free-text attributes, Unformatted Text Value `(0070,0006)` and Tick
  Label `(0070,0289)`, are redacted against the allowlist. The redaction action
  decodes raw bytes and resolves the dictionary VR for an implicit-VR (`UN`/`OB`)
  element, so redaction is independent of encoding.
- Identifiers are hashed by the bulk rules: Tracking UID `(0062,0021)`,
  Referenced SOP Instance UID `(0008,1155)`, Series Instance UID `(0020,000E)`,
  and any other UID under the UID-hash set. Tracking ID `(0062,0020)` is hashed
  with the study-scoped identifier hash, matching the study-scoped Tracking UID
  hash so the pair links consistently within a study.
- Referenced SOP Class UID `(0008,1150)` and the font names Font Name
  `(0070,0227)` and CSS Font Name `(0070,0229)` are kept. Graphic geometry
  (Graphic Data, Graphic Type) and the technical/styling attributes are kept
  because they carry no identity and have no removal rule.

## Key Object Selection content

The `default` profile admits Key Object Selection (KO) documents that reference
at least one instance and retains and cleans their structured content under the
Clean Structured Content Option (PS3.15 code `113104`). Content Sequence
`(0040,A730)` is absent from the removal set, so the engine keeps it and
recurses into its items like any other sequence:

- Text Value `(0040,A160)`, the KO/SR free-text content attribute, is redacted
  against the allowlist by the same redaction action used for the graphic
  annotation free text.
- Referenced UIDs in Content Sequence, Current Requested Procedure Evidence
  Sequence `(0040,A375)`, Identical Documents Sequence `(0040,A525)`, and
  Referenced Request Sequence `(0040,A370)` are hashed by the bulk UID rules:
  Referenced SOP Instance UID `(0008,1155)`, Series Instance UID `(0020,000E)`,
  and Study Instance UID `(0020,000D)`. Every UID is hashed with the
  study-scoped hash, so a de-identified KO links to the de-identified referenced
  objects included in the same export.
- The document title (Concept Name Code Sequence `(0040,A043)`) and Anatomic
  Region Sequence `(0008,2218)` are retained; their coded triples carry no
  identity.
- Issuer of Accession Number Sequence `(0008,0051)` is removed, so a retained
  Referenced Request Sequence cannot carry an assigning-authority identifier.

Every de-identified instance receives the De-identification Method Code Sequence
`(0012,0064)`. Each item contains a code value `(0008,0100)`, the `DCM` coding
scheme designator `(0008,0102)`, and a code meaning `(0008,0104)`. The items a
profile emits follow from its configuration:

| Code value | Code meaning | Emitted |
|------------|--------------|---------|
| `113100` | Basic Application Confidentiality Profile | When the profile sets `emits_basic_profile` (`default`, `lds`, `lds-no-dob`); not for `pixels-only` |
| `113101` | Clean Pixel Data Option | When the pixel blanker scrubs burned-in text from the instance |
| `113107` | Retain Longitudinal Temporal Information With Modified Dates | For date-shifting profiles (`default`) |
| `113106` | Retain Longitudinal Temporal Information With Full Dates | For date-preserving profiles (`lds`, `lds-no-dob`) |
| `113105` | Clean Descriptors Option | Declared in `deid_options` (`default`, `lds`, `lds-no-dob`) |
| `113108` | Retain Patient Characteristics Option | Declared in `deid_options` (`default`, `lds`, `lds-no-dob`) |
| `113104` | Clean Structured Content Option | Declared in `deid_options` (`default`) |
| `113111` | Retain Safe Private Option | Only when the instance retains device-approved private tags (see [Device Catalog](device-catalog.md)) |

The temporal code is derived from the profile's date policy: `113107` for
modified dates, `113106` for full dates, and neither when dates are removed
(`pixels-only`). A profile emits no sequence when it declares no Basic Profile,
no temporal code, no options, and no preserved private tags.

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
