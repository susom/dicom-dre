# Command-line Interface

The `dicom-dre deidentify` command de-identifies one or more DICOM files or
directories. It is a command-line wrapper over the batch engine
([`dicom_dre.deidentify_paths`](../reference/api.md)). Beyond forwarding the
per-patient parameters, the CLI resolves the identifier-hash salt (from
`--hash-salt`, the `DICOM_DRE_HASH_SALT` environment variable, or a generated
per-user salt file) and the build-time configuration (`--uid-root`,
`--allowlist-csv`, `--hash-salt`); the engine performs the identifier and UID
hashing, date jitter, and free-text redaction.

## Usage

```bash
dicom-dre deidentify [OPTIONS] SOURCES...
```

`SOURCES` is one or more files and/or directories. The command reads every
source but never modifies it. It mirrors directory trees under the output
directory; explicitly listed files are written directly into the output
directory. It prints one line per processed file, followed by a summary.

## Options

- `-o, --output-dir DIRECTORY`: Directory to write de-identified files into,
  created if needed. Required.
- `-r, --recursive`: Recurse into subdirectories of directory sources.
- `--glob PATTERN`: Filename pattern for directory scans. Repeatable and
  case-insensitive. Default: `*.dcm`, `*.dicom`.
- `--profile [default|lds|lds-no-dob|pixels-only]`: De-identification profile
  to apply. Default: `default`. See
  [De-identification Profiles](../concepts/profiles.md).
- `-p, --param KEY=VALUE`: A per-patient de-identification parameter,
  repeatable, for example `-p PATIENT_ID=TEST`. Accepts only the per-patient
  identity keys (`PATIENT_ID`, `PATIENT_NAME`, `ACCESSION_NUMBER`, `STUDY_ID`,
  `SERIES_DESCRIPTION`, `STUDY_DESCRIPTION`, `PROTOCOL_NAME`, `JITTER`); any
  other key is rejected. Build-time settings use their own flags below. A
  non-zero `JITTER` applies only to date-shifting profiles; combining a non-zero
  `JITTER` with a date-preserving profile (`lds`, `lds-no-dob`, `pixels-only`)
  is a usage error. `JITTER=0` requests no shift and is accepted by any profile.
- `--study-id VALUE`: Study identifier scoping the identifier and UID hashes
  (the `STUDY_ID` parameter). Default: unset.
- `--uid-root VALUE`: UID root prefix under which re-derived UIDs are hashed.
  Default: `1.2.840.4267.32.`.
- `--allowlist-csv VALUE`: Free-text redaction allowlist filename or absolute
  path. Default: `default.csv`.
- `--hash-salt VALUE`: Salt applied when hashing `PatientID`, `PatientName`,
  and `AccessionNumber`. When omitted, the salt is resolved in order: the
  `DICOM_DRE_HASH_SALT` environment variable, then the per-user salt file at
  `$XDG_CONFIG_HOME/dicom-dre/salt` (default `~/.config/dicom-dre/salt`). If
  none exists, a memorable passphrase is generated, saved with `0600`
  permissions, and reported on stderr. Keep that file secret and back it up: the
  same salt is required to reproduce the same pseudonyms on later runs. For
  scripted or CI use, supply the salt explicitly (via `--hash-salt` or
  `DICOM_DRE_HASH_SALT`) so runs stay deterministic.
- `--generate-salt / --no-generate-salt`: Whether to generate and persist a
  salt when none is supplied. With `--no-generate-salt` the command errors
  instead of generating, keeping scripted runs deterministic. Default:
  `--generate-salt`.
- `-q, --quiet`: Suppress informational notices on stderr, such as the salt
  generation notice. Does not affect the per-file result lines or summary on
  stdout.
- `-v, --verbose`: Enable debug logging, including tracebacks for quarantined
  files. Quarantine reasons are always reported on the `QUARANTINED:` line; this
  flag adds the underlying traceback for diagnosis. Python warnings raised by
  dependencies (for example pydicom VR mismatches) are routed through logging
  and shown only under this flag; otherwise they are suppressed.
- `--decompress / --no-decompress`: Decompress encapsulated pixel data on
  output. Default: `--no-decompress`.
- `--rename-to-sop-uid / --no-rename-to-sop-uid`: Rename each output file to
  its new SOP Instance UID. Default: `--rename-to-sop-uid`.
- `--highlight-blanked-pixels`: Fill scrubbed pixel regions with a visible
  color.
- `-j, --workers N`: Number of worker processes; `1` runs sequentially
  in-process. Default: number of CPUs.
- `--help`: Show the message and exit.

## Output filenames

Output filenames are the new SOP Instance UID by default. With
`--no-rename-to-sop-uid`, the command keeps the input basename and fails before
writing anything if two inputs would resolve to the same output path.

## Parallel processing

With `--workers` greater than `1`, the command processes files across worker
processes and prints lines as each file completes rather than in discovery
order.

## Outcomes and exit status

Each instance resolves to one terminal outcome:

- `DEIDENTIFIED`: metadata scrubbed, pixel regions blanked as required, and the
  instance written to the output directory.
- `FILTERED`: the instance matched a deny rule, so the command did not emit it.
- `QUARANTINED`: processing failed, so the command did not emit the instance.

The command exits with status `1` when any file was `QUARANTINED`. `FILTERED`
files are a normal outcome and do not affect the exit code.

## Examples

De-identify a single file:

```bash
dicom-dre deidentify scan.dcm -o out/
```

Recurse a directory tree, mirrored under the output directory:

```bash
dicom-dre deidentify studies/ -o out/ -r
```

Mix files and directories in one run:

```bash
dicom-dre deidentify a.dcm b.dcm dir/ -o out/
```

Apply a profile with replacement parameters and parallel workers:

```bash
dicom-dre deidentify studies/ -o out/ -r \
    --profile default \
    -p PATIENT_ID=TEST -p ACCESSION_NUMBER=TESTING \
    -j 8
```

## Checking the JPEG DCT accelerator

JPEG DCT-domain blanking uses an optional compiled C extension
(`_jpeg_dct_accel`) that is roughly 300x faster than the pure-Python fallback.
The `dicom-dre accelerator-status` command reports whether that extension is
active, so operators can confirm the fast path in CI and health checks.

```bash
dicom-dre accelerator-status
```

It prints one line and sets the exit code:

- `JPEG DCT C accelerator: ACTIVE`, exit code `0`.
- `JPEG DCT C accelerator: NOT AVAILABLE (using pure-Python fallback, ~300x slower)`,
  exit code `1`.

The same state is available from Python through
[`dicom_dre.jpeg_dct_accelerator_available`](../reference/api.md):

```python
from dicom_dre import jpeg_dct_accelerator_available

if not jpeg_dct_accelerator_available():
    raise SystemExit("JPEG DCT C accelerator is not compiled")
```

