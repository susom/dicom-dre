# Command-line Interface

The `dicom-dre deidentify` command de-identifies one or more DICOM files or
directories. It is a thin wrapper over the batch engine
([`dicom_dre.deidentify_paths`](../reference/api.md)) and performs no hashing,
settings lookups, or free-text redaction. De-identification parameters are
consumed as supplied, mirroring the library contract.

## Usage

```bash
dicom-dre deidentify [OPTIONS] SOURCES...
```

`SOURCES` is one or more files and/or directories. Every source is read but
never modified. Directory trees are mirrored under the output directory;
explicitly listed files land flat in the output directory. One line is printed
per processed file, followed by a summary.

## Options

- `-o, --output-dir DIRECTORY` — Directory to write de-identified files into,
  created if needed. Required.
- `-r, --recursive` — Recurse into subdirectories of directory sources.
- `--glob PATTERN` — Filename pattern for directory scans. Repeatable and
  case-insensitive. Default: `*.dcm`, `*.dicom`.
- `--profile [default|lds|lds-no-dob|pixels-only]` — De-identification profile
  to apply. Default: `default`. See
  [De-identification Profiles](../concepts/profiles.md).
- `-p, --param KEY=VALUE` — A de-identification parameter, repeatable, for
  example `-p PATIENT_ID=TEST`.
- `--decompress / --no-decompress` — Decompress encapsulated pixel data on
  output. Default: `--no-decompress`.
- `--rename-to-sop-uid / --no-rename-to-sop-uid` — Rename each output file to
  its new SOP Instance UID. Default: `--rename-to-sop-uid`.
- `--highlight-blanked-pixels` — Fill scrubbed pixel regions with a visible
  color.
- `-j, --workers N` — Number of worker processes; `1` runs sequentially
  in-process. Default: number of CPUs.
- `--help` — Show the message and exit.

## Output filenames

Output filenames are the new SOP Instance UID by default. With
`--no-rename-to-sop-uid` the input basename is kept, and the command fails
before writing anything if two inputs would resolve to the same output path.

## Parallel processing

With `--workers` greater than `1`, files are processed across worker processes
and lines are printed as each file completes rather than in discovery order.

## Outcomes and exit status

Each instance resolves to one terminal outcome:

- `DEIDENTIFIED` — metadata scrubbed, pixel regions blanked as required, and the
  instance written to the output directory.
- `FILTERED` — the instance matched a deny rule and was intentionally not
  emitted.
- `QUARANTINED` — processing failed; the instance was not emitted.

The command exits with status `1` if any file was `QUARANTINED`. `FILTERED`
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
