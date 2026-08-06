"""Shared harness for the profile contract tests.

Builds a canonical in-memory dataset seeded with greppable PHI sentinels and
runs any named profile against it through a fixed :class:`ProfileSettings`. The
same dataset and helpers back the shared-invariant contract (this phase) and the
profile-specific behavior tests that build on it.

Pydicom and the profile builder are imported inside functions rather than at
module top level to avoid the GDCM/ARM64 collection segfault (see the root
``conftest.py`` ``pytest_configure`` hook). ``SENTINELS`` and the plain module
constants below hold only strings and therefore stay at module scope.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from dataclasses import field
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Iterator

    from pydicom.dataset import Dataset

    from dicom_dre.parameters import DeidParameters


# Build-time settings held constant for every profile under test. A fixed salt
# and UID root make hashing and UID re-derivation deterministic across runs.
HASH_SALT = "phase1-contract-salt"
UID_ROOT = "1.2.826.0.1.3680043.10.9999."

# Non-zero jitter supplied to date-shifting profiles so the shift is
# deterministic and a jittered date never equals its seeded value.
FIXED_JITTER = 7


# DICOM keyword -> unique, greppable sentinel value seeded into the canonical
# dataset. Date and datetime values use distinct, non-overlapping digit strings
# so a preserved date never matches another element's value by substring.
SENTINELS: dict[str, str] = {
    # Identifiers hashed to a deterministic replacement (never survive verbatim).
    "PatientName": "SENTINEL^PATNAME",
    "PatientID": "SENTINELMRN0001",
    "AccessionNumber": "SENTINELACC0002",
    # PHI removed outright.
    "InstitutionName": "SENTINELHOSPITAL",
    "PatientAddress": "SENTINEL ADDRESS 42",
    "PatientComments": "SENTINELPATCOMMENT",
    # PHI emptied to a zero-length value.
    "ReferringPhysicianName": "SENTINEL^REFDOC",
    # Free-text descriptions redacted against the allowlist.
    "StudyDescription": "SENTINELSTUDYDESC",
    "SeriesDescription": "SENTINELSERIESDESC",
    "ProtocolName": "SENTINELPROTOCOL",
    # Private creator plus decoy data element removed by private-group removal.
    "PrivateCreator": "SENTINELCREATOR",
    "PrivateData": "SENTINELPRIVATE",
    # PHI nested inside a retained sequence, reached only by recursion.
    "NestedInstitutionName": "SENTINELNESTEDINST",
    # Curve (50xx) and overlay (60xx) group descriptions removed wholesale.
    "CurveDescription": "SENTINELCURVE",
    "OverlayDescription": "SENTINELOVERLAY",
    # Dates and a time whose retention depends on the profile date policy.
    "StudyDate": "20200102",
    "AcquisitionDateTime": "20211115081500",
    "PatientBirthDate": "19850307",
    "PatientBirthTime": "083015",
    # Retained-or-removed demographics.
    "TimezoneOffsetFromUTC": "-0730",
    "PatientAge": "045Y",
}


def build_canonical_dataset() -> Dataset:
    """Build a kitchen-sink in-memory dataset seeded with PHI sentinels.

    The dataset carries hashed identifiers, removed and emptied PHI, redacted
    free-text descriptions, DA/DT dates, registered and vendor UIDs, a private
    creator plus a decoy private element, curve and overlay group elements, a
    retired group-length tag, and a nested sequence whose item holds PHI so the
    recursive element rules are exercised. A File Meta Information group is
    attached so file-meta preservation can be checked.
    """
    from pydicom.dataset import Dataset
    from pydicom.dataset import FileMetaDataset
    from pydicom.tag import Tag
    from pydicom.uid import ExplicitVRLittleEndian
    from pydicom.uid import MRImageStorage
    from pydicom.uid import generate_uid

    ds = Dataset()

    # Retired group-length tag (must be removed by apply()).
    ds.add_new(Tag(0x0008, 0x0000), "UL", 0)

    # Registered UID (under the DICOM root; must be preserved, never hashed) and
    # vendor/per-object UIDs (re-derived to deterministic replacements).
    sop_instance_uid = generate_uid()
    study_uid = generate_uid()
    series_uid = generate_uid()
    ds.add_new(Tag(0x0008, 0x0016), "UI", MRImageStorage)  # SOPClassUID
    ds.add_new(Tag(0x0008, 0x0018), "UI", sop_instance_uid)  # SOPInstanceUID
    ds.add_new(Tag(0x0020, 0x000D), "UI", study_uid)  # StudyInstanceUID
    ds.add_new(Tag(0x0020, 0x000E), "UI", series_uid)  # SeriesInstanceUID
    ds.add_new(Tag(0x0008, 0x0060), "CS", "MR")  # Modality

    # Identifiers hashed to a deterministic replacement.
    ds.add_new(Tag(0x0010, 0x0010), "PN", SENTINELS["PatientName"])
    ds.add_new(Tag(0x0010, 0x0020), "LO", SENTINELS["PatientID"])
    ds.add_new(Tag(0x0008, 0x0050), "SH", SENTINELS["AccessionNumber"])

    # PHI removed outright.
    ds.add_new(Tag(0x0008, 0x0080), "LO", SENTINELS["InstitutionName"])
    ds.add_new(Tag(0x0010, 0x1040), "LO", SENTINELS["PatientAddress"])
    ds.add_new(Tag(0x0010, 0x4000), "LT", SENTINELS["PatientComments"])

    # PHI emptied to a zero-length value.
    ds.add_new(Tag(0x0008, 0x0090), "PN", SENTINELS["ReferringPhysicianName"])

    # Free-text descriptions redacted against the allowlist.
    ds.add_new(Tag(0x0008, 0x1030), "LO", SENTINELS["StudyDescription"])
    ds.add_new(Tag(0x0008, 0x103E), "LO", SENTINELS["SeriesDescription"])
    ds.add_new(Tag(0x0018, 0x1030), "LO", SENTINELS["ProtocolName"])

    # Dates and a time shifted, preserved, or removed by profile policy. The
    # TM element exercises the VR=TM branch of date preservation and the
    # date-override removal in lds-no-dob.
    ds.add_new(Tag(0x0008, 0x0020), "DA", SENTINELS["StudyDate"])
    ds.add_new(Tag(0x0008, 0x002A), "DT", SENTINELS["AcquisitionDateTime"])
    ds.add_new(Tag(0x0010, 0x0030), "DA", SENTINELS["PatientBirthDate"])
    ds.add_new(Tag(0x0010, 0x0032), "TM", SENTINELS["PatientBirthTime"])

    # Demographics retained by some profiles and removed by others.
    ds.add_new(Tag(0x0008, 0x0201), "SH", SENTINELS["TimezoneOffsetFromUTC"])
    ds.add_new(Tag(0x0010, 0x1010), "AS", SENTINELS["PatientAge"])

    # Private creator plus decoy data element removed by private-group removal.
    ds.add_new(Tag(0x0009, 0x0010), "LO", SENTINELS["PrivateCreator"])
    ds.add_new(Tag(0x0009, 0x1001), "LO", SENTINELS["PrivateData"])

    # Curve (50xx) and overlay (60xx) group descriptions removed wholesale.
    ds.add_new(Tag(0x5000, 0x0022), "LO", SENTINELS["CurveDescription"])
    ds.add_new(Tag(0x6000, 0x0022), "LO", SENTINELS["OverlayDescription"])

    # Nested sequence carrying PHI so recursion is exercised. AnatomicRegionSequence
    # is retained by every profile (a content root for pixels-only), while the PHI
    # inside its item is removed by the recursive element rules.
    item = Dataset()
    item.add_new(Tag(0x0008, 0x0080), "LO", SENTINELS["NestedInstitutionName"])
    ds.add_new(Tag(0x0008, 0x2218), "SQ", [item])

    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = MRImageStorage
    file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = file_meta

    return ds


@pytest.fixture()
def canonical_dataset() -> Dataset:
    """Return a fresh canonical dataset per test."""
    return build_canonical_dataset()


def _profile_settings():
    """Return the fixed build-time settings shared by every profile under test."""
    from dicom_dre.profiles.config import ProfileSettings

    return ProfileSettings(hash_salt=HASH_SALT, uid_root=UID_ROOT)


def _default_params(name: str) -> DeidParameters:
    """Return profile-appropriate de-identification parameters.

    A date-shifting profile (``modifies_dates=True``) is given the fixed non-zero
    jitter. A date-preserving or date-removing profile rejects a non-zero jitter,
    so it receives empty parameters (unset jitter).
    """
    from dicom_dre.parameters import DeidParameters
    from dicom_dre.profiles.builder import build_profile

    profile = build_profile(name, _profile_settings())
    if profile.modifies_dates:
        return DeidParameters(jitter=FIXED_JITTER)
    return DeidParameters()


def apply_profile(name: str, *, dataset: Dataset, params: DeidParameters | None = None) -> Dataset:
    """Apply the named profile to a deep copy of ``dataset`` and return the result.

    The profile is built from the fixed :func:`_profile_settings`. When ``params``
    is omitted, :func:`_default_params` supplies parameters appropriate to the
    profile date policy.
    """
    from dicom_dre.profiles.builder import build_profile

    profile = build_profile(name, _profile_settings())
    result = copy.deepcopy(dataset)
    if params is None:
        params = _default_params(name)
    profile.apply(result, params)
    return result


def _iter_scalar_values(ds: Dataset, *, skip_ui: bool) -> Iterator[object]:
    """Yield every scalar element value, descending into sequence items.

    Sequence (SQ) elements are recursed into; multi-valued elements yield each
    member. Elements whose VR cannot be resolved are skipped. When ``skip_ui`` is
    set, UI (UID) values are skipped: they are hashed to non-PHI replacements and
    their digit strings would otherwise substring-match a numeric sentinel by
    chance.
    """
    for elem in ds:
        try:
            vr = elem.VR
        except (ValueError, NotImplementedError):
            continue
        if vr == "SQ" and elem.value:
            for item in elem.value:
                yield from _iter_scalar_values(item, skip_ui=skip_ui)
            continue
        if skip_ui and vr == "UI":
            continue
        value = elem.value
        if isinstance(value, (list, tuple)) or type(value).__name__ == "MultiValue":
            yield from value
        else:
            yield value


def iter_values(ds: Dataset) -> Iterator[object]:
    """Yield every scalar element value, descending into sequence items."""
    yield from _iter_scalar_values(ds, skip_ui=False)


def find_survivors(ds: Dataset, allowed: Iterable[str]) -> set[str]:
    """Return the sentinel values still present in ``ds`` minus ``allowed``.

    A sentinel counts as surviving when its value appears as a substring of any
    non-UID scalar element value anywhere in the dataset (including nested
    sequences). UID values are excluded because they are hashed to non-PHI
    replacements. ``allowed`` is an iterable of sentinel values expected to
    survive legitimately.
    """
    allowed_set = set(allowed)
    sentinel_values = set(SENTINELS.values())
    survivors: set[str] = set()
    for value in _iter_scalar_values(ds, skip_ui=True):
        text = str(value)
        for sentinel in sentinel_values:
            if sentinel in text:
                survivors.add(sentinel)
    return survivors - allowed_set


@dataclass(frozen=True)
class ProfileExpectation:
    """Observable behaviors expected of one profile under the shared contract.

    Attributes:
        name: Buildable profile name passed to ``build_profile``.
        date_policy: One of ``"jitter"``, ``"preserve"``, or ``"remove"``.
        removes_birth_date: Whether PatientBirthDate is removed (as opposed to
            jittered or preserved).
        caps_age: Whether PatientAge over the threshold is capped.
        keeps_timezone: Whether TimezoneOffsetFromUTC is retained.
        emits_basic_profile: Whether the Basic Application Confidentiality
            Profile code (113100) is emitted.
        required_method_codes: CodeValues that must appear in the
            De-identification Method Code Sequence.
        forbidden_method_codes: CodeValues that must not appear.
        allowed_sentinels: Sentinel keywords whose values may legitimately
            survive de-identification under this profile.
    """

    name: str
    date_policy: str
    removes_birth_date: bool
    caps_age: bool
    keeps_timezone: bool
    emits_basic_profile: bool
    required_method_codes: frozenset[str]
    forbidden_method_codes: frozenset[str]
    allowed_sentinels: frozenset[str] = field(default_factory=frozenset)


# Expectations for every buildable profile. Sentinel references are keywords into
# SENTINELS; the tests resolve them to values. Kept in conftest so the parametrize
# hook and the test module reach it without a tests-package-internal import (the
# tests tree is not on the type-checker or pytest import root).
PROFILE_EXPECTATIONS: tuple[ProfileExpectation, ...] = (
    ProfileExpectation(
        name="default",
        date_policy="jitter",
        removes_birth_date=False,
        caps_age=True,
        keeps_timezone=False,
        emits_basic_profile=True,
        required_method_codes=frozenset({"113100", "113104", "113105", "113107", "113108"}),
        forbidden_method_codes=frozenset({"113106"}),
        allowed_sentinels=frozenset({"PatientAge"}),
    ),
    ProfileExpectation(
        name="lds",
        date_policy="preserve",
        removes_birth_date=False,
        caps_age=False,
        keeps_timezone=True,
        emits_basic_profile=True,
        required_method_codes=frozenset({"113100", "113105", "113106", "113108"}),
        forbidden_method_codes=frozenset({"113107"}),
        allowed_sentinels=frozenset(
            {
                "StudyDate",
                "AcquisitionDateTime",
                "PatientBirthDate",
                "PatientBirthTime",
                "TimezoneOffsetFromUTC",
                "PatientAge",
            }
        ),
    ),
    ProfileExpectation(
        name="lds-no-dob",
        date_policy="preserve",
        removes_birth_date=True,
        caps_age=False,
        keeps_timezone=True,
        emits_basic_profile=True,
        required_method_codes=frozenset({"113100", "113105", "113106", "113108"}),
        forbidden_method_codes=frozenset({"113107"}),
        allowed_sentinels=frozenset(
            {
                "StudyDate",
                "AcquisitionDateTime",
                "TimezoneOffsetFromUTC",
                "PatientAge",
            }
        ),
    ),
    ProfileExpectation(
        name="pixels-only",
        date_policy="remove",
        removes_birth_date=True,
        caps_age=False,
        keeps_timezone=False,
        emits_basic_profile=False,
        required_method_codes=frozenset({"113103", "113104"}),
        forbidden_method_codes=frozenset({"113100", "113106", "113107"}),
        allowed_sentinels=frozenset(),
    ),
)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize any test requesting ``expectation`` over every profile.

    Using a hook (rather than a decorator that imports the table) keeps the test
    module free of tests-package-internal imports, which neither pytest nor the
    type checker resolve because the tests tree is not an import root.
    """
    if "expectation" in metafunc.fixturenames:
        metafunc.parametrize(
            "expectation",
            PROFILE_EXPECTATIONS,
            ids=[expectation.name for expectation in PROFILE_EXPECTATIONS],
        )


@pytest.fixture()
def profile_harness() -> SimpleNamespace:
    """Expose the harness helpers and sentinel table to test modules.

    The helpers are module-level functions in this conftest; a fixture hands them
    to tests so no test module imports from the tests package.
    """
    return SimpleNamespace(
        apply_profile=apply_profile,
        find_survivors=find_survivors,
        sentinels=SENTINELS,
    )
