# Reproducibility

`dicom-dre` is reproducible by design. The engine makes no network calls,
consults no external mapping tables, and draws no random values. Given the same
input DICOM and the same parameters, it produces byte-for-byte identical output.
Every value the engine writes is either copied verbatim from a parameter or
computed by a pure function of the input and the parameters. The hashed
identifiers and UIDs, the date shift, and free-text redaction are all computed
this way.

## What the caller supplies

The caller may supply already-mapped replacement values; when it omits them the
engine derives them deterministically rather than looking them up:

- The engine writes caller-supplied replacement identifiers (patient ID,
  patient name, accession number) verbatim. When the caller omits one, the
  engine derives the replacement by hashing the original element value, a pure
  function of that value, the `ProfileSettings.hash_salt` value, and the study
  identifier.
- UID re-derivation is a pure function of the UID root and salt passed in; the
  same source UID plus the same root and salt always yields the same output UID.
- Date shifting uses the caller-supplied jitter value when provided. When it is
  omitted, the shift is a pure function of the hash salt, the study identifier,
  and the original PatientID, so it is deterministic rather than a random draw.
- The engine writes free-text description values verbatim when the caller
  provides them; when the caller omits them, redaction is a pure function of the
  field content and the allowlist.

The identifier-hash salt is itself a parameter. The `dicom-dre` CLI can generate
and persist one on first use (a one-time random draw), but reusing that saved
salt keeps every subsequent run reproducible. This keeps identifier mapping, salt
management, and any cross-study consistency under the caller's control rather than
hidden inside the engine. See [De-identification Profiles](profiles.md) and
[Text redaction](text-redaction.md).

## Cross-object linkage

A retained presentation state and the images it references align only when both
are processed with the same `study_id` on `DeidParameters`. UID re-derivation
salts each UID with the study identifier (`use_study_salt=True`), and the
identifier hash applied to Tracking ID salts with the same study identifier.
Processing every instance of a study with one `STUDY_ID` parameter therefore
yields matching hashed references between the presentation state and its
referenced images. Processing them under different study identifiers breaks the
linkage.

## Regression guard

A regression test suite built from sampled DICOM studies guards reproducibility.
Each fixture records the technical matching tags and the expected catalog
filtering and pixel-scrub decisions, with no PHI or pixel data. The tests assert
that the engine still reaches the recorded decision for every case. This suite
catches catalog or profile changes that alter existing outcomes. See [Testing](../about/testing.md) and
[Local validation](../guides/local-validation.md).
