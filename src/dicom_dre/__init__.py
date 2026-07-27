"""DICOM De-identification & Redaction Engine (dicom-dre).

DICOM de-identification engine: metadata scrub, device-catalog
filtering, pixel blanking, and JPEG-DCT scrubbing.

Public API: the engine entry point (``deidentify_file``), the
result type (``DeidentifyResult`` / ``Outcome``), the canonical profile builder
(``build_profile``), the concrete profile factories, the device catalog, and
the supporting value types.
"""

from __future__ import annotations

from dicom_dre.attributes import IndexAttributes
from dicom_dre.batch import OutputPathCollisionError
from dicom_dre.batch import ProfileSpec
from dicom_dre.batch import deidentify_paths
from dicom_dre.catalog import CatalogDecision
from dicom_dre.catalog import DeviceCatalog
from dicom_dre.catalog import DicomTags
from dicom_dre.catalog import Variant
from dicom_dre.default_catalog import get_default_catalog
from dicom_dre.parameters import DeidParameters
from dicom_dre.pipeline import deidentify_file
from dicom_dre.profile import DeidProfile
from dicom_dre.profiles import default_profile
from dicom_dre.profiles import lds_no_dob_profile
from dicom_dre.profiles import lds_profile
from dicom_dre.profiles import pixels_only_profile
from dicom_dre.profiles.builder import build_profile
from dicom_dre.result import BatchItemResult
from dicom_dre.result import DeidentifyResult
from dicom_dre.result import Outcome
from dicom_dre.scrub_region import ScrubRegion
from dicom_dre.text_redactor import TextRedactor
from dicom_dre.text_redactor import get_text_redactor


try:
    from dicom_dre._version import __version__
except ImportError:  # pragma: no cover - version file generated at build time
    __version__ = "0.0.0.dev0"


__all__ = [
    "BatchItemResult",
    "CatalogDecision",
    "DeidParameters",
    "DeidProfile",
    "DeidentifyResult",
    "DeviceCatalog",
    "DicomTags",
    "IndexAttributes",
    "Outcome",
    "OutputPathCollisionError",
    "ProfileSpec",
    "ScrubRegion",
    "TextRedactor",
    "Variant",
    "__version__",
    "build_profile",
    "deidentify_file",
    "deidentify_paths",
    "default_profile",
    "get_default_catalog",
    "get_text_redactor",
    "lds_no_dob_profile",
    "lds_profile",
    "pixels_only_profile",
]
