# dicom-dre

A fast, deterministic DICOM de-identification and redaction engine.

`dicom-dre` removes protected health information (PHI) from DICOM instances in
two places where it commonly hides:

- **Burned-in pixel PHI.** A declarative device catalog matches each instance to
  a known device and acquisition variant and blanks the fixed pixel regions
  where that device is known to burn in text. For JPEG Baseline images, regions
  are zeroed directly in the DCT domain, so unblanked pixels are preserved
  bit-for-bit with no recompression loss.
- **Free-text metadata PHI.** Description fields that frequently carry PHI
  (`SeriesDescription`, `StudyDescription`, `ProtocolName`) are redacted
  token-by-token against an allowlist: any token not on the allowlist is masked,
  while known clinical terms pass through.

Instance metadata is also scrubbed against a configurable de-identification
profile, and instance/study/series UIDs are deterministically re-derived, so the
same input plus the same parameters always yields the same output.

:::{note}
The bundled device catalog and free-text allowlist were derived from studies on
a single PACS at one medical research center. Their device rules, pixel scrub
regions, and allowlisted vocabulary reflect the scanner fleet and reporting
conventions observed there, and are unlikely to be complete or correct for a
different site. Treat the shipped catalog and allowlist as a starting point that
requires local validation, not as a turnkey configuration. See
[Provenance and portability](about/provenance.md).
:::

```{toctree}
:maxdepth: 2
:caption: Getting Started

getting-started/installation
getting-started/quickstart
```

```{toctree}
:maxdepth: 2
:caption: Concepts

concepts/architecture
concepts/device-catalog
concepts/jpeg-dct
concepts/profiles
concepts/text-redaction
concepts/determinism
```

```{toctree}
:maxdepth: 2
:caption: Guides

guides/cli
guides/redactor
guides/extending-the-catalog
guides/local-validation
```

```{toctree}
:maxdepth: 2
:caption: Reference

reference/api
```

```{toctree}
:maxdepth: 2
:caption: About

about/provenance
about/history
about/testing
about/changelog
```

## Indices and tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
