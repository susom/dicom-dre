# Testing

The project uses pytest. Tests live in `tests/unit/` and mirror the structure of
`src/dicom_dre/`.

## Running the test suite

Run all tests:

```bash
uv run pytest
```

Or use the justfile target:

```bash
just test
```

Run a single test file or pattern:

```bash
just test-one tests/unit/test_pipeline_preservation.py
```

## Coverage

Generate a coverage report with per-line detail for uncovered lines:

```bash
just cov
```

This runs `uv run pytest --cov=src/dicom_dre --cov-report=term-missing`.

## Pure-Python fallback

The JPEG DCT-domain scrubber has an optional compiled C accelerator. To confirm
that the pure-Python fallback works when the extension is absent, run:

```bash
just test-fallback
```

The target temporarily moves any compiled `_jpeg_dct_accel*.so` out of the
package, runs the suite, and restores the extension afterward.

## Regression fixtures

`tests/unit/test_catalog_regression_fixtures.py` asserts that the catalog still
reaches the recorded filtering and pixel-scrub decision for each sampled case.
The fixtures record only the technical matching tags and the expected decision,
with no PHI or pixel data. Run this suite after any catalog or profile change so
that it catches alterations to existing outcomes.

## Writing tests

- Place tests in `tests/unit/`, mirroring the source structure.
- Use descriptive test names that state what each test verifies.
- Mock external services in unit tests, especially any that would make network
  calls.
- Use fixtures for common setup.
