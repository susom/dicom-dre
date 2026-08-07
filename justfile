# dicom-dre development tasks
# Run `just` to list available recipes.

# Default: list recipes
default:
    @just --list

# Install all dependencies (including dev group)
sync:
    uv sync

# Install git hooks (pre-commit, pre-push, commit-msg)
git-hooks:
    uv run pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type commit-msg

# Run pre-commit checks on staged files (or all files with FILES=--all-files)
precommit *FILES:
    uv run pre-commit run {{ FILES }}

# Compile the CFFI JPEG-DCT acceleration extension
build-ext:
    cd src && uv run python -m dicom_dre._jpeg_dct_accel_build
    @echo "Extension compiled: $(ls src/dicom_dre/_jpeg_dct_accel*.so 2>/dev/null || echo 'NOT FOUND')"

# Remove compiled C extension artifacts
clean-ext:
    rm -f src/dicom_dre/_jpeg_dct_accel*.so src/dicom_dre/_jpeg_dct_accel*.o src/dicom_dre/_jpeg_dct_accel*.c

# Run ruff linter
lint:
    uv run ruff check src tests

# Check formatting without applying changes
fmt-check:
    uv run ruff format --check src tests

# Apply ruff auto-fixes and formatting
fmt:
    uv run ruff check --fix src tests
    uv run ruff format src tests

# Run pyrefly type checker
typecheck:
    uv run pyrefly check

# Build the HTML documentation (Sphinx + Furo)
docs:
    uv run --group docs sphinx-build -b html docs docs/_build/html
    @echo "Documentation built: docs/_build/html/index.html"

# Serve the documentation with live reload during editing
docs-serve:
    uv run --group docs sphinx-autobuild docs docs/_build/html --open-browser

# Remove built documentation artifacts
docs-clean:
    rm -rf docs/_build

# Run the full test suite
test:
    uv run pytest

# Run tests with coverage report
cov:
    uv run pytest --cov=src/dicom_dre --cov-report=term-missing

# Run a single test file or pattern (e.g. just test-one tests/unit/test_pipeline_preservation.py)
test-one FILE:
    uv run pytest {{ FILE }} -v

# Verify the pure-Python fallback works without the compiled extension
test-fallback:
    #!/usr/bin/env bash
    set -euo pipefail
    SOFILES=$(ls src/dicom_dre/_jpeg_dct_accel*.so 2>/dev/null || true)
    if [ -n "$SOFILES" ]; then
        TMPDIR=$(mktemp -d)
        mv $SOFILES "$TMPDIR/"
        trap "mv $TMPDIR/*.so src/dicom_dre/ 2>/dev/null; rm -rf $TMPDIR" EXIT
    fi
    uv run pytest -W ignore::UserWarning

# Run a fuzz harness locally (needs `uv pip install atheris`).
# Example: just fuzz fuzz_text_redactor 60
fuzz HARNESS DURATION="60":
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p crashes "fuzz/corpus/{{ HARNESS }}"
    uv run python "fuzz/{{ HARNESS }}.py" \
        -max_total_time={{ DURATION }} -timeout=25 -artifact_prefix=crashes/ \
        "fuzz/corpus/{{ HARNESS }}"

# Build sdist and wheel (compiles the C extension first)
build: build-ext
    uv run python -m build --no-isolation --wheel

# Full local CI: lint + typecheck + tests
ci: lint fmt-check typecheck test

# Bootstrap a fresh dev environment: sync deps then compile the C extension
bootstrap: sync build-ext
