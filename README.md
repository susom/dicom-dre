# dicom-dre

DICOM de-identification for both metadata and burned-in pixel text.

Burned-in text is the more difficult case. The engine blanks it from rules you
define rather than from OCR or heuristic text detection: you specify which
scanner models burn text into which regions of the frame, and the engine blanks
those regions. That rule set is the device catalog.

- **Rule-based pixel blanking.** The device catalog identifies an instance by
  its scanner and acquisition settings and blanks the fixed regions recorded for
  it. Coverage is exactly what you put in the catalog: it only blanks devices
  and regions you have mapped and validated, and unmatched devices pass through
  untouched.

- **Lossless redaction.** Editing a JPEG normally means decompressing it and
  recompressing it, which slightly degrades the whole image. For JPEG Baseline
  images the engine instead edits the compressed data directly and blanks only
  the masked blocks, so every pixel outside those blocks stays bit-for-bit
  identical.

- **Deterministic and offline.** No lookups and no network calls. UIDs and
  replacement identifiers are re-derived by hashing, so the same input plus the
  same parameters always produces the same output.

- **Simple, embeddable API.** Call it from your own DICOM pipeline in a few
  lines, and supply your own identifiers (PatientID, AccessionNumber, date
  jitter) or let it derive them for you.

Metadata is handled alongside the pixels: description fields such as
`SeriesDescription` and `StudyDescription` are redacted to remove likely PHI
while preserving clinical meaning, and every attribute is scrubbed against a
configurable de-identification profile.

Tailoring the device catalog and allowlist to the scanners in your PACS and the
vocabulary your site uses is the substantive work of adopting `dicom-dre`. Once
that investment is made, the result is a repeatable, auditable pipeline you can
trust to process DICOM at your site.

> **Note:** Output is **not** de-identified under HIPAA Safe Harbor or Expert
> Determination and must be validated by a qualified person before sharing. The
> bundled catalog and allowlist were derived from a single PACS at one site and
> are unlikely to be complete elsewhere. It also does not address
> re-identification vectors in the image content itself, such as facial
> reconstruction from volumetric imaging. Always treat output as retaining
> residual PHI risk. See
> [Limitations and portability](https://susom.github.io/dicom-dre/stable/about/limitations.html).

## Install

Requires Python 3.12.

```bash
uv pip install dicom-dre    # or: pip install dicom-dre
```

## Quick start

```bash
# De-identify a file or a directory tree into out/
dicom-dre deidentify scan.dcm -o out/
dicom-dre deidentify studies/ -o out/ -r

# Choose a profile, set parameters, run in parallel (-j sets worker count)
dicom-dre deidentify studies/ -o out/ \
    --profile default -p PATIENT_ID=TEST -p ACCESSION_NUMBER=TESTING -j 8
```

Sources are read but never modified. The command exits non-zero if any instance
is quarantined.

```python
from dicom_dre import DeidParameters, ProfileSpec, deidentify_paths

for item in deidentify_paths(
    sources=["studies/"],
    output_dir="out/",
    recursive=True,
    profile_spec=ProfileSpec(name="default"),
    parameters=DeidParameters(patient_id="TEST"),
):
    print(item.input_file, item.result.outcome)
```

## Outcomes

Each instance resolves to exactly one outcome:

| Outcome | Meaning |
| --- | --- |
| `DEIDENTIFIED` | Metadata scrubbed, pixels blanked as required, written to output. |
| `FILTERED` | Matched a deny rule (e.g. unsupported modality/device); not emitted. |
| `QUARANTINED` | Processing failed; not emitted. |

## Profiles

Each profile applies the DICOM PS3.15 Basic Application Confidentiality Profile
(strict is allow-list based) plus a set of PS3.15 options, recorded in
DeidentificationMethodCodeSequence `(0012,0064)`.

| Profile | PS3.15 method | Options applied | Dates |
| --- | --- | --- | --- |
| `default` | `DICOM-PS3.15E-Basic` | Clean Structured Content (113104), Clean Descriptors (113105), Retain Patient Characteristics (113108) | Shifted per study by a derived jitter |
| `lds` | `DICOM-PS3.15E-Basic-LDS` | Clean Descriptors (113105), Retain Patient Characteristics (113108) | Retained unchanged (limited data set) |
| `lds-no-dob` | `DICOM-PS3.15E-Basic-LDS-No-DOB` | Clean Descriptors (113105), Retain Patient Characteristics (113108) | Retained unchanged except PatientBirthDate/Time, which are removed |
| `strict` | Allow-list (Basic Profile not emitted) | Clean Graphics (113103), Clean Structured Content (113104) | Removed; a minimal set of technical time elements is retained |

`default`, `lds`, and `lds-no-dob` re-derive UIDs by hashing; `strict` retains a
fixed allow-list of elements and discards the rest.

See [De-identification Profiles](https://susom.github.io/dicom-dre/stable/concepts/profiles.html).

## Free-text redaction tools

Description attributes such as `SeriesDescription` and `StudyDescription` are
among the most useful fields for understanding what a study contains, yet
because a technologist can type into them freely at the imaging device, they
frequently pick up PHI. Redaction keeps the useful vocabulary while masking the
rest, and it is driven by an allowlist you tailor to your site.

Redaction works token by token. A token is a run of text between delimiters:
each value is split at whitespace, punctuation, and letter/digit boundaries (so
`MR512` becomes `MR` and `512`). Every token is compared case-insensitively
against the allowlist; tokens on the list pass through, and the rest are masked
character-for-character with `X`. Before tokenizing, a set of regular
expressions masks structured identifiers regardless of the allowlist, including
dates, times, phone numbers, SSNs, ZIP+4 codes, email addresses, URLs, and long
hexadecimal strings, while bare 1 to 5 digit numbers are allowed through.

Because the allowlist must match your site's vocabulary, the `redactor`
subcommands exist to build and maintain it. Export every `SeriesDescription`,
`StudyDescription`, and `ProtocolName` value from your PACS database to a CSV,
then run these commands over that export to review the distinct tokens and
decide which belong on the allowlist:

```bash
# Preview redactions and review flagged tokens, adding good ones to the allowlist
dicom-dre redactor quality-check input.csv --interactive
# List the distinct tokens in the export to curate the allowlist
dicom-dre redactor show-tokens --input input.csv
# Add one or more tokens to the allowlist directly
dicom-dre redactor allow-token TERM1 TERM2
# Redact every cell of a CSV against the current allowlist
dicom-dre redactor redact --input input.csv --output output.csv
```

See the [redactor guide](https://susom.github.io/dicom-dre/stable/guides/redactor.html).

## Documentation

Full documentation: **https://susom.github.io/dicom-dre/**

- [Installation](https://susom.github.io/dicom-dre/stable/getting-started/installation.html) and [Quickstart](https://susom.github.io/dicom-dre/stable/getting-started/quickstart.html)
- [Architecture](https://susom.github.io/dicom-dre/stable/concepts/architecture.html), [Device Catalog](https://susom.github.io/dicom-dre/stable/concepts/device-catalog.html), [JPEG DCT scrubbing](https://susom.github.io/dicom-dre/stable/concepts/jpeg-dct.html)
- [Profiles](https://susom.github.io/dicom-dre/stable/concepts/profiles.html), [Text redaction](https://susom.github.io/dicom-dre/stable/concepts/text-redaction.html), [Reproducibility](https://susom.github.io/dicom-dre/stable/concepts/reproducibility.html)
- [CLI reference](https://susom.github.io/dicom-dre/stable/guides/cli.html), [Extending the catalog](https://susom.github.io/dicom-dre/stable/guides/extending-the-catalog.html), [Local validation](https://susom.github.io/dicom-dre/stable/guides/local-validation.html)
- [API reference](https://susom.github.io/dicom-dre/stable/reference/api.html)

## Development

```bash
uv run pytest
```

The JPEG DCT accelerator is an optional compiled C extension roughly 300x faster
than the pure-Python fallback. Check its status with:

```bash
dicom-dre accelerator-status
```

Contributions are welcome via pull request. Changes to de-identification policy
(catalog, scrub regions, profiles, or allowlist) require local evidence and
regression fixtures.

## License

Apache-2.0; provided "AS IS" without warranty (see [LICENSE](LICENSE)). The JPEG
DCT-domain scrubber is a port of the PixelMed JPEG Selective Block Redaction
Codec, distributed under that codec's BSD license; see the source header in
`src/dicom_dre/jpeg_dct_scrubber.py` and the [NOTICE](NOTICE) file.
