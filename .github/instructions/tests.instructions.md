---
description: Writing tests in tests/unit/
applyTo: "tests/**/*.py"
---

# Writing Tests in dicom-dre

Instructions for creating and maintaining tests in the `tests/` directory.

## Test Structure

All tests live in `tests/unit/` and mirror the `src/dicom_dre/` module structure:

```
tests/
├── conftest.py          # Root config: GDCM/ARM64 segfault guard (pytest_configure)
└── unit/
    ├── conftest.py      # Shared fixtures: synthetic GE SIGNA Premier MR dataset
    ├── test_catalog.py
    ├── test_cli.py
    ├── test_default_catalog.py
    ├── test_jpeg_dct_anonymizer.py
    ├── test_pipeline_preservation.py
    ├── test_pixel_blanker.py
    ├── test_profile.py
    └── test_text_redactor.py
```

## Placing New Tests

All new tests go in `tests/unit/`. They must use only mocks, `tmp_path`, pure Python
logic, or `pydicom` test data — no network calls, no cloud services, no external
processes. For example, a test for `src/dicom_dre/catalog.py` belongs at
`tests/unit/test_catalog.py`.

## Test Framework

Use pytest for all tests. Configuration is in `pyproject.toml`:

- Test timeout: 90 seconds (configurable per test with `@pytest.mark.timeout`)
- Coverage requirement: 20% minimum

## GDCM / ARM64 Import Note

`python-gdcm` (SWIG bindings) can segfault on ARM64 if loaded during pytest's
assertion-rewriting phase. The root `conftest.py` imports `pydicom` in
`pytest_configure` to trigger GDCM loading before collection begins. To stay
safe, import `pydicom` inside test functions or fixtures rather than at module
level in test files.

## File Naming Conventions

- Test files: `test_*.py`
- Benchmark files: `bench_*.py`
- Test functions: `test_*`
- Benchmark functions: `bench_*`

## Test Class Organization

Group related tests in classes with descriptive names:

```python
"""Tests for the device catalog lookup."""

import pytest

from dicom_dre.catalog import DeviceCatalog
from dicom_dre.catalog import CatalogDecision


class TestDeviceCatalogLookup:
    """Test device catalog manufacturer/model matching."""

    def test_known_device_returns_decision(self):
        """A known manufacturer/model pair returns a catalog decision."""
        catalog = DeviceCatalog.from_default()
        decision = catalog.lookup("GE MEDICAL SYSTEMS", "SIGNA Premier")
        assert decision is not None, "Known device should return a decision"

    def test_unknown_device_returns_none(self):
        """An unrecognised manufacturer/model pair returns None."""
        catalog = DeviceCatalog.from_default()
        decision = catalog.lookup("UNKNOWN_MFR", "UNKNOWN_MODEL")
        assert decision is None, "Unknown device should return None"
```

## Docstrings

- Module docstring: Describe what is being tested
- Class docstring: Describe the test suite purpose
- Test function docstring: Describe the expected behavior being validated
- Use present tense and be specific about what is being tested
- Avoid vague descriptions like "Test validation" or wordy phrases like "This test validates..."

## Temporary Files and Directories

**CRITICAL**: Always use pytest's `tmp_path` fixture. Never use hardcoded paths like `/tmp/test.dcm` or `Path.home()`.

```python
def test_operation(tmp_path):
    """Test with temporary files."""
    input_file = tmp_path / "test.dcm"
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    # tmp_path is automatically cleaned up after the test
```

For custom fixtures, use `tempfile.mkdtemp()`:

```python
@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)
```

## Mocking External Services

Mock any calls that cross a process boundary (file I/O to real paths, network calls).

```python
from unittest.mock import Mock, patch

def test_with_mock():
    """Test with mocked external service."""
    mock_client = Mock()
    mock_client.download.return_value = b"test data"

    with patch("module.get_client", return_value=mock_client):
        result = function_that_uses_client()
        assert result is not None, "Result should not be None"
```

## Environment Variables in Tests

Use `monkeypatch.setenv()` and `monkeypatch.delenv()` to set and clear environment
variables. Never use `os.environ` directly in tests or fixtures, as it leaks state
across tests.

```python
def test_requires_env_var(monkeypatch):
    """Test behavior when environment variable is set."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    result = load_config()
    assert result.secret_key == "test-secret-key", "Config should read SECRET_KEY"


def test_missing_env_var(monkeypatch):
    """Test behavior when environment variable is absent."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        load_config()
```

## Session-Scoped Temporary Directories

For session-scoped fixtures that need a temporary directory, use `tmp_path_factory`:

```python
@pytest.fixture(scope="session")
def shared_output_dir(tmp_path_factory):
    """Shared output directory for session-scoped tests."""
    return tmp_path_factory.mktemp("output")
```

## Testing with Real Data

### Using pydicom Test Data

Use pydicom test data for DICOM file tests:

```python
from pathlib import Path
from pydicom.data import get_testdata_file

def test_dicom_processing(tmp_path):
    """Test DICOM file processing."""
    input_file_str = get_testdata_file("CT_small.dcm")
    if not isinstance(input_file_str, str):
        raise ValueError("get_testdata_file did not return a string path")

    source_file = Path(input_file_str)
    test_file = tmp_path / "test.dcm"
    shutil.copy2(source_file, test_file)

    result = process_dicom(test_file)
    assert result is not None
```

**Important**: Do not skip tests if pydicom is not available. All project dependencies (including pydicom) are listed in `pyproject.toml` and must be present. If a test cannot import pydicom, the test should **fail**, not skip. This ensures the development environment is correctly set up.

### Assertions

**EVERY assertion MUST include a message.** Never write bare `assert` statements without explanatory text. Include expected and actual values in assertion messages to make test failures immediately understandable.

```python
# Correct - always include messages
assert result.success is True, "Operation should succeed"
assert len(items) == 3, f"Expected 3 items, got {len(items)}"
assert status.used_percent == 50.0, f"Expected 50.0%, got {status.used_percent}"

# Wrong - bare assertions without messages
assert result.success is True  # NO - missing message
assert len(items) == 3  # NO - missing message

# Testing exceptions - use match parameter or check exc_info
def test_invalid_input_raises_error():
    """Invalid input raises ValueError."""
    with pytest.raises(ValueError, match="cannot be None"):
        validate_input(None)

    # Or with exc_info for more complex checks
    with pytest.raises(ValueError) as exc_info:
        validate_input(None)
    assert "cannot be None" in str(exc_info.value), f"Expected 'cannot be None' in error, got {exc_info.value}"

# Testing optional values - use explicit None checks
assert result.output_file is None, "No output file should be created"
```

### Test Isolation

Each test must be independent. Never share state between tests.

```python
def test_operation(tmp_path):
    """Test operation with fresh data."""
    input_file = tmp_path / "input.txt"
    input_file.write_text("test data")
    result = process_file(input_file)
    assert result.success

# Use fixtures for setup/teardown
@pytest.fixture
def test_database():
    """Set up test database."""
    db = create_test_db()
    yield db
    db.cleanup()

def test_with_database(test_database):
    """Test with isolated database."""
    test_database.insert(record)
    assert test_database.count() == 1

### Maintain Test Integrity

If a test fails, fix the root cause in the code or the test. Do not remove assertions, add empty try/catch blocks to hide errors, or add conditional logic to skip test cases. Never skip or disable failing tests. Tests must fail (not skip) when dependencies are missing.

### Parametrized Tests

Test multiple inputs efficiently:

```python
@pytest.mark.parametrize("method,expected", [
    ("equals", True),
    ("contains", True),
    ("startsWith", True),
    ("invalid_method", False),
])
def test_method_validation(method, expected):
    """Test method name validation."""
    result = is_valid_method(method)
    assert result == expected
```

### Testing Time-Dependent Code

```python
from unittest.mock import patch
from datetime import datetime

def test_timestamp_logic():
    """Test time-dependent logic with fixed time."""
    fixed_time = datetime(2024, 1, 1, 12, 0, 0)
    with patch("module.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        result = function_using_current_time()
        assert result.timestamp == fixed_time
```

## Running Tests

```bash
# Run the full test suite
just test

# Run tests with coverage report
just cov

# Run a single test file
just test-one tests/unit/test_pipeline_preservation.py

# Verify the pure-Python fallback (without compiled C extension)
just test-fallback
```

## PHI Protection

Never use real PHI in tests. Use the synthetic `signa_premier_file` fixture from
`tests/unit/conftest.py` or pydicom's built-in test files. Never commit test files
containing real patient data.

## Common Anti-patterns

Never use hardcoded paths like `Path("/tmp/test.dcm")`. Always use `tmp_path` for
temporary files. Never skip failing tests or remove assertions to make tests pass.
Tests must fail (not skip) when dependencies are missing. Do not share state between
tests using global variables. Do not comment out failing assertions or catch
exceptions to hide failures. Keep all dependencies in `pyproject.toml`. **Never
write bare assertions without messages** — every `assert` statement must include an
explanatory message with expected and actual values.
