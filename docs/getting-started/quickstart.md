# Quickstart

This page shows the minimal steps to de-identify DICOM instances with the
`dicom-dre` command-line interface. See [Installation](installation.md) if the
package is not yet installed.

## De-identify files or directories

De-identify one or more sources into an output directory:

```bash
# Single file
dicom-dre deidentify scan.dcm -o out/

# Recurse a directory tree (mirrored under out/)
dicom-dre deidentify studies/ -o out/ -r
```

Sources are read but never modified. Output is written under the directory
passed with `-o`.

## Select a profile and parameters

Choose a de-identification profile with `--profile` and supply replacement
parameters with `-p KEY=VALUE`:

```bash
dicom-dre deidentify a.dcm b.dcm dir/ -o out/ \
    --profile default \
    -p PATIENT_ID=TEST -p ACCESSION_NUMBER=TESTING \
    -j 8
```

The `-j` option sets the number of parallel workers. The available profiles are
`default`, `lds`, `lds-no-dob`, and `pixels-only`; see
[De-identification Profiles](../concepts/profiles.md).

## Outcomes and exit status

Each instance resolves to one terminal outcome:

- `DEIDENTIFIED` — metadata scrubbed, pixel regions blanked as required, and the
  instance written to the output directory.
- `FILTERED` — the instance matched a deny rule (for example an unsupported
  modality or device) and was intentionally not emitted.
- `QUARANTINED` — processing failed; the instance was not emitted.

The command exits non-zero if any instance is `QUARANTINED`. `FILTERED`
instances are a normal outcome and do not cause a non-zero exit. See
[Architecture](../concepts/architecture.md) for how instances reach each
outcome.

## Next steps

- [CLI guide](../guides/cli.md) for the full `deidentify` option set.
- [Free-text redaction tools](../guides/redactor.md) for curating an allowlist.
- [Local validation](../guides/local-validation.md) before relying on the
  shipped catalog and allowlist at a new site.
