# dicom-dre

A reproducible DICOM de-identification and redaction engine.

:::{warning}
`dicom-dre` performs automated, rule-based de-identification of protected health
information (PHI). Its output is not de-identified under HIPAA Safe Harbor or
Expert Determination, so it should not be treated as de-identified or released
publicly on the basis of this tool alone. Output should be validated by a
qualified person before downstream use or sharing.

The engine reduces PHI; it does not guarantee its removal. Burned-in pixel PHI is
blanked only for devices and regions present in the catalog, and free-text PHI is
masked only for tokens absent from the allowlist. Unmatched devices, moved
overlays, and PHI that resembles allowlisted terms can all leave residual PHI in
the output.

At the originating institution, output from this application is classified as
high risk: a step down from full PHI, but still requiring a HIPAA Data Privacy
Attestation (DPA) before use. Treat the output as retaining residual PHI risk and
govern it accordingly. See [Limitations and portability](about/limitations.md).
:::

`dicom-dre` removes protected health information (PHI) from DICOM instances in
two locations where it commonly occurs:

- **Burned-in pixel PHI.** A declarative device catalog fingerprints each
  instance against a known hardware device and acquisition variant. It then
  blanks the fixed pixel regions where that device burns in text. For JPEG
  Baseline images, the engine zeroes regions directly in the DCT domain, so
  unblanked pixels stay bit-for-bit identical with no recompression loss.
- **Free-text metadata PHI.** The engine redacts description fields that often
  contain PHI (`SeriesDescription`, `StudyDescription`, `ProtocolName`) token by
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
the included catalog and allowlist as a starting point that requires local
validation, not as a turnkey configuration. See
[Limitations and portability](about/limitations.md).
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
:caption: Notes

notes/iso-2022-specific-character-set
```

```{toctree}
:maxdepth: 2
:caption: About

about/limitations
about/history
about/testing
about/changelog
```

## Indices and tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
