# dicom-dre

A fast, reproducible DICOM de-identification and redaction engine.

`dicom-dre` removes protected health information (PHI) from DICOM instances in
two places where it commonly hides:

- **Burned-in pixel PHI.** A declarative device catalog fingerprints each
  instance against a known hardware device and acquisition variant. It then
  blanks the fixed pixel regions where that device burns in text. For JPEG
  Baseline images, the engine zeroes regions directly in the DCT domain, so
  unblanked pixels stay bit-for-bit identical with no recompression loss.
- **Free-text metadata PHI.** The engine redacts description fields that often
  carry PHI (`SeriesDescription`, `StudyDescription`, `ProtocolName`) token by
  token against an allowlist. It masks any token that is not on the allowlist
  and passes known clinical terms through.

The engine also scrubs instance metadata against a configurable
de-identification profile and re-derives instance, study, and series UIDs
reproducibly. The same input and the same parameters always yield the same
output.

:::{note}
The bundled device catalog and free-text allowlist come from studies on a single
PACS at one medical research center. Their device rules, pixel scrub regions, and
allowlisted vocabulary reflect the scanner fleet and reporting conventions seen
there. They are unlikely to be complete or correct for a different site. Treat
the shipped catalog and allowlist as a starting point that requires local
validation, not as a turnkey configuration. See
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
concepts/reproducibility
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
