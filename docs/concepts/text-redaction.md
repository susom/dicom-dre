# Text Redaction

DICOM description fields frequently carry free-text PHI. Operators populate
`SeriesDescription`, `StudyDescription`, and `ProtocolName`, which can contain
names, dates, accession numbers, and other identifiers. `dicom-dre` redacts
these fields token by token against an allowlist, so known clinical vocabulary
passes through and the engine masks unrecognized tokens.

:::{important}
**Intended scope.** The redactor targets short, semi-structured description
fields such as `SeriesDescription` and `StudyDescription`. In these fields the
distinct values are overwhelmingly derived from structured entries in the source
PACS (protocol names, modality codes, body parts, view labels), so a finite
allowlist covers the legitimate vocabulary and unrecognized tokens are strong
PHI candidates.

Do not use the redactor on paragraphs of prose, general clinical notes, report
bodies, or any field that is entirely free-form text with no discernible
pattern. The token-allowlist model does not bound the vocabulary of such fields
and cannot provide reliable de-identification for them.
:::

:::{note}
The bundled free-text allowlist comes from studies on a single PACS at one
medical research center. Its vocabulary reflects the reporting conventions seen
there. It is unlikely to be complete or correct for another site. Validate and
extend the allowlist against your own descriptions before relying on it, to
avoid over-redaction (masking legitimate terms) and under-redaction (leaking
PHI). See
[Provenance and portability](../about/provenance.md) and
[Local validation](../guides/local-validation.md).
:::

## How redaction works

Redaction runs in three passes over each field value:

1. **Pattern masking.** Regular expressions match structured content that the
   redactor treats as sensitive regardless of the allowlist: dates, times
   (unless dates are preserved), email addresses, URLs, hexadecimal strings of
   six or more characters, US phone numbers, Social Security numbers, ZIP+4
   codes, ZIP codes preceded by a US state, and the prefixes `NRP`, `MRN`, and
   `SSN` followed by four or more digits. The redactor replaces matched
   characters with `X` and leaves separators such as `/`, `-`, `.`, `:`, and
   whitespace in place, so the value keeps its shape.

2. **Tokenization.** The redactor splits the remaining text on a fixed set of
   delimiters (spaces, punctuation, and boundaries between letters and digits).

3. **Allowlist filtering.** The redactor keeps each token when its lowercased
   form is in the allowlist or when it matches an allow pattern (for example a
   one-to-five digit number). It replaces any other token with a run of `X`
   characters of equal length. It leaves already-masked tokens unchanged.

Because masked tokens keep the length of the source token, the redacted value
retains its field width and separator layout while dropping the identifying
content.

## Date preservation

The `preserve_dates` flag controls whether dates and times survive redaction:

- When `preserve_dates` is `False` (`default` and `pixels-only` profiles), the
  redactor masks date and time tokens along with everything else off the
  allowlist.
- When `preserve_dates` is `True` (`lds` and `lds-no-dob` profiles), the
  redactor skips the date-masking and time-masking passes and adds month names,
  four-digit years, and timezone abbreviations to the allow patterns so they
  pass through intact. It still masks emails, URLs, and hexadecimal strings.

See [De-identification Profiles](profiles.md) for the per-profile flag values.

## Allowlist source

The allowlist is a CSV of permitted tokens loaded from the package resources.
Each profile names its allowlist through the `allowlist_csv` attribute (default
`default.csv`). A caller can substitute a custom allowlist by supplying a
different filename or an absolute path. The `redactor` CLI commands operate on
CSV files using the same allowlist mechanism and support curating the list; see
the [Redactor guide](../guides/redactor.md).

## Description-field behavior

For the description fields (`SeriesDescription`, `StudyDescription`,
`ProtocolName`), a caller-supplied value takes precedence: the engine writes it
verbatim with no redaction. When the caller supplies no value, the engine
redacts the field present in the source dataset with the profile's allowlist and
`preserve_dates` setting.
