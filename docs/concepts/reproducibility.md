# Reproducibility

`dicom-dre` is reproducible by design. The engine performs no hashing lookups,
no network calls, and no randomization of its own. De-identification parameters
(patient ID, accession number, UID root, salt, jitter, and so on) are consumed
exactly as supplied. Given identical inputs and parameters, the output is
byte-for-byte identical.

## What the caller supplies

Because the engine does no lookups, the caller is responsible for supplying
already-mapped identifier values:

- Replacement identifiers (patient ID, accession number) are written verbatim.
- UID re-derivation is a pure function of the UID root and salt passed in; the
  same source UID plus the same root and salt always yields the same output UID.
- Date shifting uses the caller-supplied jitter value, not a random draw.
- Free-text description values, when provided, are written verbatim; when
  omitted, redaction is a pure function of the field content and the allowlist.

This keeps identifier mapping, salt management, and any cross-study consistency
under the caller's control rather than hidden inside the engine. See
[De-identification Profiles](profiles.md) and [Text redaction](text-redaction.md).

## Regression guard

Reproducibility is guarded by a regression test suite built from sampled DICOM
studies. Each fixture records the technical matching tags and the expected
catalog filtering and pixel-scrub decisions, with no PHI or pixel data, and the
tests assert that the engine still reaches the recorded decision for every case.
Catalog or profile changes that alter existing outcomes are caught by this
suite. See [Testing](../about/testing.md) and
[Local validation](../guides/local-validation.md).
