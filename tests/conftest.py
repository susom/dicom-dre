"""Root pytest configuration for dicom_dre tests.

Imports pydicom during pytest_configure to work around a segmentation fault that
occurs when python-gdcm is loaded during pytest's collection phase. The fault
stems from the interaction between pytest's assertion rewriting and the GDCM
SWIG bindings on ARM64. Importing pydicom (which triggers GDCM loading) before
collection begins avoids the segfault.
"""

import pydicom  # noqa: F401  imported for its side effect during configure


def pytest_configure(config):
    """Import pydicom before pytest loads test files to prevent a GDCM segfault."""
