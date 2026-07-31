# Local Validation

The bundled device catalog and free-text allowlist come from studies on a single
PACS at one medical research center. Their device rules, pixel scrub regions, and
allowlisted vocabulary reflect the scanner fleet and reporting conventions seen
there. They are unlikely to be complete or correct for a different site. This
guide describes how to validate the included configuration against your own data
before relying on the output.

:::{note}
Treat the included catalog and allowlist as a starting point that requires local
validation, not as a turnkey configuration. See
[Provenance and portability](../about/provenance.md).
:::

## Validate pixel scrubbing per device

For a device that the catalog does not recognize, the engine either denies it or
allows it with no pixel blanking. An allowed device with a scrub region defined
for the wrong resolution leaves burned-in text unblanked. Confirm the catalog
reaches the expected decision for every device in your fleet.

1. Collect representative instances across the resolutions and software versions
   each device produces. Read the matching tags with `pydicom`:

   ```python
   import pydicom
   from dicom_dre.catalog import DicomTags
   from dicom_dre.default_catalog import get_default_catalog

   ds = pydicom.dcmread("sample.dcm", stop_before_pixels=True)
   decision = get_default_catalog().evaluate(DicomTags.from_dataset(ds))
   print(decision.action, decision.reason)
   print(decision.scrub_regions)
   ```

2. Confirm the `action` is what you expect (`allow`, `deny`, or the accumulated
   `scrub` regions), and that `scrub_regions` covers every burned-in text banner
   at that resolution.

3. De-identify a sample and inspect the output pixels to confirm the engine
   blanked each banner:

   ```bash
   dicom-dre deidentify sample.dcm -o out/
   ```

4. For any device that is unmatched, denied in error, or has incomplete scrub
   regions, add or adjust a device rule. See
   [Extending the catalog](extending-the-catalog.md).

## Review and extend the allowlist

The engine redacts free-text description fields by masking every token that is
not on the allowlist. An allowlist tuned to another site over-redacts your local
vocabulary (masking legitimate terms) or under-redacts (leaking PHI that appears
as an allowlisted token).

1. Extract the unique tokens present in a sample of your free text to find
   candidate terms:

   ```bash
   dicom-dre redactor show-tokens --input samples.csv
   ```

2. Preview redaction side by side to see which terms are masked and which pass
   through:

   ```bash
   dicom-dre redactor quality-check samples.csv
   ```

3. Add legitimate local terms to the allowlist, either in bulk or interactively:

   ```bash
   dicom-dre redactor allow-token bicuspid spoonful
   dicom-dre redactor quality-check samples.csv --interactive
   ```

4. Confirm that no token containing PHI (names, identifiers, locations) remains on
   the allowlist. The redactor masks dates, times, emails, URLs, and hexadecimal
   strings regardless of the allowlist; use `--preserve-dates` only for limited
   data set profiles that retain dates. See
   [Text redaction](../concepts/text-redaction.md).

## Run the regression suite

The catalog regression fixtures record the technical matching tags and the
expected filter and scrub decisions for sampled studies, with no PHI or pixel
data. After any catalog or allowlist change, run the suite to confirm existing
outcomes are unchanged:

```bash
uv run pytest tests/unit/test_catalog_regression_fixtures.py
just test
```

When you extend the catalog for your own devices, add fixtures that record their
expected decisions so future changes cannot silently regress them. See
[Testing](../about/testing.md) for the full test commands.
