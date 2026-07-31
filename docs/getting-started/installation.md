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

Development uses a [Dev Container](https://containers.dev/) so every contributor
has the same toolchain (Python 3.12, `uv`, `just`, `dcmtk`, and the build
dependencies for the C extension) regardless of host operating system.

### Prerequisites

- [Visual Studio Code](https://code.visualstudio.com/)
- [Docker](https://www.docker.com/)
- The [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
  VS Code extension

### Open the repository in the container

1. Clone the repository and open the folder in VS Code.
2. When VS Code detects the Dev Container configuration, select "Reopen in
   Container". You can also run "Dev Containers: Reopen in Container" from the
   command palette.
3. The first build downloads the base image and installs the container
   features; later starts reuse the cached image.

The container's `postCreateCommand` runs `.devcontainer/post-create.sh`, which:

- runs `uv sync` to install all dependency groups,
- compiles the CFFI JPEG-DCT acceleration extension into `src/dicom_dre/`, and
- installs the pre-commit, pre-push, and commit-msg git hooks.

No manual bootstrap step is required. After the script finishes, run the test
suite:

```bash
uv run pytest
```

See [Testing](../about/testing.md) for the full set of test recipes.
