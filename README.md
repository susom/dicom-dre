# DICOM-DRE

A reproducible DICOM de-identification and redaction engine.

## What it does

`dicom-dre` removes PHI from DICOM instances in two places where it commonly
appears:

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

The `default` profile admits and cleans two annotation-bearing object types in
place rather than dropping them:

- **2D softcopy presentation states** carrying a Graphic Annotation Sequence
  `(0070,0001)` and **Key Object Selection documents** that reference at least
  one instance are retained. Their annotation and content subtrees are cleaned:
  free-text attributes are redacted against the allowlist and referenced UIDs
  are hashed with the study-scoped function, so annotations and key-object
  references reach downstream use with cross-object linkage preserved.

Presentation states without an annotation, and Key Object Selection documents
that reference no instance, are filtered. See
[De-identification Profiles](docs/concepts/profiles.md) and the
[Device Catalog](docs/concepts/device-catalog.md).

## Reproducible by design

The engine performs no lookups and no network calls. Replacement identifiers are
derived deterministically: when a caller supplies no explicit value, PatientID
and AccessionNumber are hashed with SHA-256 over `salt|study_id|identifier`,
UIDs are re-derived under the configured UID root, and the date shift is derived
per study from the salt and study identifier when no jitter is supplied.
Explicitly supplied de-identification parameters (patient ID, accession number,
jitter, etc.) are consumed exactly as given. Given identical inputs, parameters,
and salt, the derived replacement identifiers, UIDs, and date shifts are
reproduced exactly.

A separate regression test suite guards the catalog decisions. It is built from
sampled DICOM studies. Each fixture records the technical matching tags and the
expected catalog filtering and pixel-scrub decisions (with no PHI or pixel
data), and the tests assert that the engine still reaches the recorded decision
for every case, so catalog or profile changes that alter existing outcomes are
caught.

## De-identification status and limits

`dicom-dre` performs automated, rule-based de-identification. Its output is not
de-identified under HIPAA Safe Harbor or Expert Determination, so it should not
be treated as de-identified or released publicly on the basis of this tool alone.
Output should be validated by a qualified person before downstream use or
sharing.

The engine reduces PHI but does not guarantee its removal. The bundled device
catalog and free-text allowlist were derived from studies on a **single PACS at
one medical research center**, so they encode that site's scanner fleet and
reporting conventions and are unlikely to be complete for a different site.
Unmatched or mismatched devices do not have their burned-in text blanked, and
free-text PHI that resembles allowlisted terms can pass through. The tool also
does not address re-identification vectors in the image content itself, such as
facial reconstruction from volumetric imaging.

At our institution, output from this application is classified as high risk: a
step down from full PHI, but still requiring a HIPAA Data Privacy Attestation
(DPA) before use. We recommend treating the output as retaining residual PHI risk
and governing it accordingly.

Before relying on `dicom-dre` at another site, validate pixel scrubbing against
your own devices and extend the allowlist for your local vocabulary. See
[Limitations and portability](docs/about/limitations.md) for the full list of
site-specific assumptions and re-identification vectors this tool does not
address.

## Outcomes

Each instance resolves to one terminal outcome:

- `DEIDENTIFIED`: metadata scrubbed, pixel regions blanked as required, written
  to the output directory.
- `FILTERED`: the instance matched a deny rule (for example an unsupported
  modality or device) and was not emitted.
- `QUARANTINED`: processing failed; the instance was not emitted.

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

- `default`: full metadata scrub with re-derived UIDs.
- `lds`: HIPAA limited data set (retains dates).
- `lds-no-dob`: limited data set without date of birth.
- `pixels-only`: pixel scrubbing with minimal metadata changes.

### Free-text redaction tools

The `redactor` subcommands operate on CSV files of free text, using the same
allowlist mechanism as description-field redaction:

```bash
# Redact every cell of a CSV against the allowlist
dicom-dre redactor redact --input input.csv --output output.csv

# Preview redactions side by side
dicom-dre redactor quality-check input.csv

# Interactively review flagged tokens and add them to the allowlist
dicom-dre redactor quality-check input.csv --interactive

# List unique tokens to help curate an allowlist
dicom-dre redactor show-tokens --input input.csv

# Add one or more tokens to the allowlist
dicom-dre redactor allow-token TERM1 TERM2
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

## Contributing

`dicom-dre` was built first for our own use and is tuned to the structure and
conventions of our datasets. We are sharing it because parts of it may be useful
to others, but its direction follows our internal needs. A few consequences
follow from that:

- **Pull requests are appreciated and are the best way to contribute.** Bug
  fixes, new features, and broader format support are all welcome. To keep
  review straightforward, keep each pull request focused, describe what changed
  and why, and add tests where they apply.

- **Changes to de-identification policy require local evidence.** Edits to the
  device catalog, pixel scrub regions, de-identification profiles, or the
  free-text allowlist change what counts as PHI and what is emitted. Ground any
  such change in a representative test sample drawn from your own imaging
  library, and add regression fixtures that record the expected catalog
  filtering and pixel-scrub decisions (with no PHI or pixel data). A policy
  change without supporting fixtures cannot be reviewed for correctness.

- **We may not act on every issue.** Because the engine is tuned to our use
  case, behavior that looks like a defect from the outside can be expected for
  us. We may be unable to reproduce or prioritize problems that do not affect
  our own workflows.

- **Support is best-effort.** We maintain this alongside our regular work, so
  responses may be slow.

If your requirements diverge from ours, forking is reasonable and encouraged; a
version you control fully may serve you better.

That said, we would like this library to be as generalizable as possible for the
broader community, so do not let any of the above discourage you from submitting
a pull request or opening an issue.

## License

Apache-2.0. The software is provided "AS IS", without warranty of any kind; see
the [LICENSE](LICENSE) file for the governing terms. The JPEG DCT-domain
scrubber is a port of the PixelMed JPEG
Selective Block Redaction Codec and is distributed under that codec's BSD
license; see the source header in `src/dicom_dre/jpeg_dct_scrubber.py` and the
`NOTICE` file.

## Acknowledgements

This project would not have been possible without our years of working with and
learning from the MIRC CTP (Clinical Trial Processor) engine, for which we are
grateful.
