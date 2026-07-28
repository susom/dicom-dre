# DICOM-DRE

A fast, reproducible DICOM de-identification and redaction engine.

`dicom-dre` removes protected health information (PHI) from DICOM instances in
two places where it commonly hides:

- **Burned-in pixel PHI.** A declarative device catalog matches each instance to
  a known device and acquisition variant (by manufacturer, model, modality,
  software version, image dimensions, SOP class, and image type) and blanks the
  fixed pixel regions where that device is known to burn in text. For JPEG
  Baseline images, regions are zeroed directly in the DCT domain, so unblanked
  pixels are preserved bit-for-bit with no recompression loss.
- **Free-text metadata PHI.** Description fields that frequently carry PHI
  (`SeriesDescription`, `StudyDescription`, `ProtocolName`) are redacted
  token-by-token against an allowlist: any token not on the allowlist is masked,
  while known clinical terms pass through. This approach works because the
  distinct values in these short description fields are overwhelmingly derived
  from structured entries in the source PACS, so a finite allowlist covers the
  legitimate vocabulary. It is not intended for paragraphs of prose, general
  clinical notes, or other entirely free-form fields with no discernible
  pattern, where the allowlist model cannot bound the vocabulary or reliably
  de-identify the text.

Instance metadata is also scrubbed against a configurable de-identification
profile, and instance/study/series UIDs are deterministically re-derived, so the
same input plus the same parameters always yields the same output.

## Reproducible by design

The engine performs no hashing lookups, no network calls, and no randomization
of its own. De-identification parameters (patient ID, accession number, UID
root, salt, jitter, etc.) are consumed exactly as supplied. Given identical
inputs and parameters, output is byte-for-byte reproducible. Callers are
responsible for supplying already-hashed or already-mapped identifier values.

This reproducibility is guarded by a regression test suite built from sampled
DICOM studies. Each fixture records the technical matching tags and the expected
catalog filtering and pixel-scrub decisions (with no PHI or pixel data), and the
tests assert that the engine still reaches the recorded decision for every case,
so catalog or profile changes that alter existing outcomes are caught.

## Provenance and portability caveat

The bundled device catalog and free-text allowlist were derived from studies on
a **single PACS at one medical research center**. The catalog's device rules,
pixel scrub regions, and allowlisted vocabulary reflect the scanner fleet and
reporting conventions observed there. They are unlikely to be complete or
correct for a different site. Before relying on `dicom-dre` elsewhere:

- Validate pixel scrubbing against your own devices; unmatched or mismatched
  devices will not have their burned-in text blanked.
- Review and extend the allowlist for your local vocabulary to avoid
  over-redaction (masking legitimate terms) or under-redaction (leaking PHI).

Treat the shipped catalog and allowlist as a starting point that requires local
validation, not as a turnkey configuration.

## Outcomes

Each instance resolves to one terminal outcome:

- `DEIDENTIFIED` — metadata scrubbed, pixel regions blanked as required, written
  to the output directory.
- `FILTERED` — the instance matched a deny rule (for example an unsupported
  modality or device) and was intentionally not emitted.
- `QUARANTINED` — processing failed; the instance was not emitted.

## Installation

This project uses [`uv`](https://docs.astral.sh/uv/) for package management and
requires Python 3.12.

```bash
uv pip install -e .
```

## Command-line usage

De-identify files or directories into an output directory:

```bash
# Single file
dicom-dre deidentify scan.dcm -o out/

# Recurse a directory tree (mirrored under out/)
dicom-dre deidentify studies/ -o out/ -r

# Mixed sources, parallel workers, chosen profile and parameters
dicom-dre deidentify a.dcm b.dcm dir/ -o out/ \
    --profile default \
    -p PATIENT_ID=TEST -p ACCESSION_NUMBER=TESTING \
    -j 8
```

Sources are read but never modified. The command exits non-zero if any instance
is `QUARANTINED`; `FILTERED` instances are a normal outcome.

### JPEG DCT accelerator status

JPEG DCT-domain blanking uses an optional compiled C extension that is roughly
300x faster than the pure-Python fallback. Confirm it is active:

```bash
dicom-dre accelerator-status
```

The command prints `JPEG DCT C accelerator: ACTIVE` and exits `0` when the
extension is loaded, or reports the pure-Python fallback and exits `1`
otherwise. The same state is available in Python via
`dicom_dre.jpeg_dct_accelerator_available()`:

```python
from dicom_dre import jpeg_dct_accelerator_available

assert jpeg_dct_accelerator_available(), "JPEG DCT C accelerator is not compiled"
```

### Profiles

Select a de-identification profile with `--profile`:

- `default` — full metadata scrub with re-derived UIDs.
- `lds` — HIPAA limited data set (retains dates).
- `lds-no-dob` — limited data set without date of birth.
- `pixels-only` — pixel scrubbing with minimal metadata changes.

### Free-text redaction tools

The `redactor` subcommands operate on CSV files of free text, using the same
allowlist mechanism as description-field redaction:

```bash
# Redact every cell of a CSV against the allowlist
dicom-dre redactor redact --input input.csv --output output.csv

# Preview redactions side by side
dicom-dre redactor quality-check input.csv

# List unique tokens to help curate an allowlist
dicom-dre redactor show-tokens --input input.csv
```

Pass `--allowlist <file.csv-or-path>` to use a custom allowlist and
`--preserve-dates` to keep dates and times intact for limited data sets.

These commands are useful when you can dump every `SeriesDescription`,
`StudyDescription`, and `ProtocolName` value from your PACS: run them over that
export to review the distinct tokens and build an allowlist tailored to your
site's vocabulary.

## Library usage

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

The public API also exposes `deidentify_file`, `build_profile`,
`get_default_catalog`, `DeviceCatalog`, `TextRedactor`, and the profile
factories. See the module docstrings and `docs/` for details.

## Development

```bash
uv run pytest        # run the test suite
```

## License

Apache-2.0. The JPEG DCT-domain scrubber is a port of the PixelMed JPEG
Selective Block Redaction Codec and is distributed under that codec's BSD
license; see the source header in `src/dicom_dre/jpeg_dct_scrubber.py` and the
`NOTICE` file.

## Acknowledgements

This project would not have been possible without our years of working with and
learning from the MIRC CTP (Clinical Trial Processor) engine, for which we are
grateful.
