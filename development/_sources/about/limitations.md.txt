# Limitations and Portability

The bundled device catalog and free-text allowlist come from studies derived from a single
PACS at a medical research center. The catalog's device rules, pixel scrub
regions, and allowlisted vocabulary reflect the scanner fleet and reporting
conventions seen there. They are unlikely to be complete or correct for a
different site.

## Output is automated de-identification, not certified

`dicom-dre` performs automated, rule-based PHI removal. Its output is not
de-identified under HIPAA Safe Harbor or Expert Determination, so it should not
be treated as de-identified or released publicly on the basis of this tool alone.
A qualified person should validate output before downstream use or sharing.
Output may be incorporated into an expert-determined public dataset only after an
expert evaluates the actual records in the context of that combined release.

The engine reduces PHI; it does not guarantee its removal. Burned-in pixel PHI is
blanked only for devices and regions present in the catalog. Free-text PHI is
masked only for tokens absent from the allowlist. Unmatched devices, moved
overlays, and PHI that resembles allowlisted terms can all leave residual PHI in
the output.

At the originating institution, output from this application is classified as
high risk: a step down from full PHI, but still requiring a HIPAA Data Privacy
Attestation (DPA) before use. Sites that adopt `dicom-dre` set their own risk
classification and handling controls, and treat the output as retaining residual
PHI risk.

## Re-identification vectors this application does not address

`dicom-dre` targets two PHI carriers: burned-in pixel text and free-text
metadata fields, plus tag-level metadata scrubbing through the active profile. It
does not detect or remove identifying information that resides in the image
content itself or in other structural features. The following vectors are out of
scope and remain in the output.

- **Facial reconstruction from volumetric imaging.** High-resolution
  cross-sectional series that include the face (for example cranial MR or head
  CT) permit reconstruction of a recognizable 3D-rendered face from the 2D
  slices. Under the HIPAA Privacy Rule, full-face photographic images and any
  comparable images are direct identifiers, and GDPR classifies facial images as
  biometric data. `dicom-dre` does not deface or otherwise alter anatomical pixel
  content, so this identifier persists. Removing it requires a separate defacing
  or skull-stripping step. See Jeong YU, Yoo S, Kim YH, Shim WH.
  "De-Identification of Facial Features in Magnetic Resonance Images: Software
  Development Using Deep Learning Technology." *J Med Internet Res*
  2020;22(12):e22739.
  [doi:10.2196/22739](https://doi.org/10.2196/22739).
- **Other biometric or morphometric identifiers.** Dental structures, unique
  bone morphology, implants and hardware with serial-numbered geometry, and other
  distinctive anatomy can support re-identification and are not modified.
- **Linkage through quasi-identifiers.** Values retained under a profile (for
  example dates in a limited data set, ages, geographic granularity, rare
  diagnoses, or acquisition timestamps) can identify an individual when combined
  with other reasonably available data. Whether a given profile output is
  de-identified depends on the release context, not on this tool alone.
- **PHI in fields and structures the profile does not cover.** Private tags,
  embedded icons or secondary-capture overlays, structured report content, and
  file metadata outside the scrubbed tag set may carry identifiers that the
  configured profile does not remove.
- **Residual PHI in retained annotation subtrees.** Admitted 2D softcopy
  presentation states retain their Graphic Annotation Sequence. The profile
  redacts the two free-text attributes (Unformatted Text Value `(0070,0006)` and
  Tick Label `(0070,0289)`) against the allowlist and hashes identifiers within
  the subtree, but operator free text that resembles allowlisted terms can
  survive redaction, and retained reference sequences reconstruct a hashed
  cross-object linkage graph for admitted instances.
- **Residual PHI in retained Key Object Selection content.** Admitted KO
  documents retain their Content Sequence. The profile redacts Text Value
  `(0040,A160)` against the allowlist, but that attribute is operator- and
  vendor-entered free text, so a token that resembles an allowlisted term can
  survive redaction. Referenced UIDs are hashed, reconstructing a hashed
  cross-object linkage graph for admitted instances.

Evaluating and mitigating these vectors is the responsibility of the site and,
where public release is intended, of the expert performing the HIPAA Expert
Determination.

## What is site-specific

The following are distributed with `dicom-dre` but encode assumptions about one site:

- **Device rules.** Each catalog entry matches a specific device by
  manufacturer, model, modality, software version, and image dimensions. Devices
  absent from the observed fleet have no entry, and the engine will not
  recognize them.
- **Pixel scrub regions.** Blanking coordinates are fixed per device and
  acquisition variant. If a device burns in text at a different location, or a
  firmware revision moves the overlay, the engine will not scrub it correctly.
- **Free-text allowlist.** The allowlisted vocabulary reflects the reporting
  conventions and clinical terms seen in one site's description fields. The
  engine masks local vocabulary that is absent from the allowlist; local PHI
  patterns the allowlist does not anticipate may pass through.

## Consequences of an unvalidated deployment

- **Unmatched or mismatched devices** do not have their burned-in text blanked.
  The engine filters an instance from an unknown device rather than emitting it
  with unscrubbed PHI, but a partially matching rule with wrong coordinates can
  emit an instance whose overlay is not fully covered.
- **Over-redaction** masks legitimate terms when the allowlist omits vocabulary
  used at your site, degrading the usefulness of description fields.
- **Under-redaction** leaks PHI when tokens that should be masked resemble
  allowlisted terms.

## Before relying on `dicom-dre` elsewhere

- Validate pixel scrubbing against your own devices. Confirm that each device
  you process either matches a catalog entry with correct scrub regions or that
  the engine intentionally filters it.
- Review and extend the allowlist for your local vocabulary to reduce
  over-redaction and under-redaction.
- Run the regression suite after any catalog or allowlist change to confirm that
  existing decisions still hold.

The [Local validation](../guides/local-validation.md) guide describes these
steps in detail. The [Extending the catalog](../guides/extending-the-catalog.md)
guide covers adding new device entries.

Treat the included catalog and allowlist as a starting point that requires local
validation, not as a turnkey configuration.

The software is provided "AS IS", without warranty of any kind, under the terms
of the Apache License 2.0.
