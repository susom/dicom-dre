# Text Redaction

DICOM description fields frequently carry free-text PHI: `SeriesDescription`,
`StudyDescription`, and `ProtocolName` are populated by operators and can
contain names, dates, accession numbers, and other identifiers. `dicom-dre`
redacts these fields token by token against an allowlist, so known clinical
vocabulary passes through while unrecognized tokens are masked.

:::{note}
The bundled free-text allowlist was derived from studies on a single PACS at one
medical research center. Its permitted vocabulary reflects the reporting
conventions observed there and is unlikely to be complete or correct for another
site. Validate and extend the allowlist against your own descriptions before
relying on it, to avoid over-redaction (masking legitimate terms) and
under-redaction (leaking PHI). See
[Provenance and portability](../about/provenance.md) and
[Local validation](../guides/local-validation.md).
:::

## How redaction works

Redaction runs in three passes over each field value:

1. **Pattern masking.** Regular expressions match structured content that is
   assumed to be sensitive regardless of the allowlist: dates, times (unless
   dates are preserved), email addresses, URLs, hexadecimal strings of six or
   more characters, US phone numbers, Social Security numbers, ZIP+4 codes, ZIP
   codes preceded by a US state, and the prefixes `NRP`, `MRN`, and `SSN`
   followed by four or more digits. Matched characters are replaced with `X`,
   leaving separators such as `/`, `-`, `.`, `:`, and whitespace in place so the
   shape of the value is preserved.

2. **Tokenization.** The remaining text is split on a fixed set of delimiters
   (spaces, punctuation, and boundaries between letters and digits).

3. **Allowlist filtering.** Each token is kept when its lowercased form is in
   the allowlist or when it matches an allow pattern (for example a one-to-five
   digit number). Any other token is replaced with a run of `X` characters of
   equal length. Tokens that are already fully masked are left unchanged.

Because masked tokens keep the length of the source token, the redacted value
retains its field width and separator layout while the identifying content is
removed.

## Date preservation

The `preserve_dates` flag controls whether dates and times survive redaction:

- When `preserve_dates` is `False` (`default` and `pixels-only` profiles), date
  and time tokens are masked along with everything else off the allowlist.
- When `preserve_dates` is `True` (`lds` and `lds-no-dob` profiles), the
  date-masking and time-masking passes are skipped, and month names, four-digit
  years, and timezone abbreviations are added to the allow patterns so they pass
  through intact. Emails, URLs, and hexadecimal strings are still masked.

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
`ProtocolName`), a caller-supplied value takes precedence and is written
verbatim with no redaction. When no value is supplied, the field present in the
source dataset is redacted with the profile's allowlist and `preserve_dates`
setting.
