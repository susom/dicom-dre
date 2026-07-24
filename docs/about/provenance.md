# Provenance and Portability

The bundled device catalog and free-text allowlist were derived from studies on
a single PACS at one medical research center. The catalog's device rules, pixel
scrub regions, and allowlisted vocabulary reflect the scanner fleet and
reporting conventions observed there. They are unlikely to be complete or
correct for a different site.

## What is site-specific

The following ship with `dicom-dre` but encode assumptions about one site:

- **Device rules.** Each catalog entry matches a specific device by
  manufacturer, model, modality, software version, and image dimensions. Devices
  absent from the observed fleet have no entry and will not be recognized.
- **Pixel scrub regions.** Blanking coordinates are fixed per device and
  acquisition variant. A device that burns in text at a different location, or a
  firmware revision that moves the overlay, will not be scrubbed correctly.
- **Free-text allowlist.** The allowlisted vocabulary reflects the reporting
  conventions and clinical terms seen in one site's description fields. Local
  vocabulary that is absent from the allowlist is masked; local PHI patterns not
  anticipated by the allowlist may pass through.

## Consequences of an unvalidated deployment

- **Unmatched or mismatched devices** do not have their burned-in text blanked.
  An instance from an unknown device is filtered rather than emitted with
  unscrubbed PHI, but a partially matching rule with wrong coordinates can emit
  an instance whose overlay is not fully covered.
- **Over-redaction** masks legitimate terms when the allowlist omits vocabulary
  used at your site, degrading the usefulness of description fields.
- **Under-redaction** leaks PHI when tokens that should be masked resemble
  allowlisted terms.

## Before relying on `dicom-dre` elsewhere

- Validate pixel scrubbing against your own devices. Confirm that each device
  you process either matches a catalog entry with correct scrub regions or is
  intentionally filtered.
- Review and extend the allowlist for your local vocabulary to reduce
  over-redaction and under-redaction.
- Run the regression suite after any catalog or allowlist change to confirm that
  existing decisions are preserved.

The [Local validation](../guides/local-validation.md) guide describes these
steps in detail. The [Extending the catalog](../guides/extending-the-catalog.md)
guide covers adding new device entries.

Treat the shipped catalog and allowlist as a starting point that requires local
validation, not as a turnkey configuration.
