# Installation

`dicom-dre` requires Python 3.12 and uses
[`uv`](https://docs.astral.sh/uv/) for package management.

## Install the package

Install from a checkout of the repository:

```bash
uv pip install -e .
```

This installs the library and the `dicom-dre` command-line entry point.

Verify the install:

```bash
dicom-dre --help
```

## Optional: build the JPEG DCT C extension

The JPEG DCT-domain scrubber has a pure-Python implementation and an optional
CFFI-based C extension. The extension is not required; when it is absent, the
engine falls back to the pure-Python path. Building it reduces the time spent
zeroing DCT blocks in JPEG Baseline images.

Build the extension with the `just` recipe:

```bash
just build-ext
```

The recipe compiles `src/dicom_dre/_jpeg_dct_accel.c` and reports the path of
the resulting shared object. To remove the compiled artifacts:

```bash
just clean-ext
```

To confirm the pure-Python fallback still works without the compiled extension,
run:

```bash
just test-fallback
```

## Development environment

Sync all dependency groups and compile the extension in one step:

```bash
just bootstrap
```

This runs `uv sync` followed by `just build-ext`. Run the test suite with:

```bash
uv run pytest
```

See [Testing](../about/testing.md) for the full set of test recipes.
