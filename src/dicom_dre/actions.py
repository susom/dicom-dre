"""Tag action factories for DICOM metadata de-identification.

Each factory returns a callable with signature
``(Dataset, BaseTag, DeidParameters) -> None``. Factories close over their
build-time arguments at profile construction time; per-patient values are read
from the :class:`DeidParameters` supplied at apply time.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

from pydicom.datadict import dictionary_VR
from pydicom.dataset import Dataset
from pydicom.tag import BaseTag

from dicom_dre.parameters import DEFAULT_STUDY_ID
from dicom_dre.parameters import IDENTIFIER_PLACEHOLDER
from dicom_dre.uid_utils import hash_identifier
from dicom_dre.uid_utils import hashuid


if TYPE_CHECKING:
    from dicom_dre.parameters import DeidParameters


TagAction = Callable[[Dataset, BaseTag, "DeidParameters"], None]

# Text VRs receiving a fixed non-empty token in dummy_for_vr(). UN is handled
# separately because it is written as raw bytes; numeric VRs are branched inline.
_DUMMY_TEXT_VRS: frozenset[str] = frozenset({"AE", "CS", "LO", "LT", "PN", "SH", "ST", "UC", "UR", "UT"})


def _create_element(ds: Dataset, tag: BaseTag, value: str) -> None:
    """Create a new element for *tag*, resolving its VR from the data dictionary.

    Unknown tags fall back to VR ``"LO"``. Sequence (SQ) tags are created empty,
    since a string value cannot populate a sequence.
    """
    try:
        vr = dictionary_VR(tag)
    except KeyError:
        vr = "LO"
    ds.add_new(tag, vr, [] if vr == "SQ" else value)


def keep() -> TagAction:
    """Preserve element unchanged."""

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        pass

    return action


def remove() -> TagAction:
    """Delete element from dataset."""

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag in ds:
            del ds[tag]

    return action


def empty() -> TagAction:
    """Replace element value with zero-length value.

    For SQ (sequence) elements, sets the value to an empty list rather
    than an empty string. Setting a string value on a VR=SQ element
    raises an error in pydicom 3.x.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag in ds:
            if ds[tag].VR == "SQ":
                ds[tag].value = []
            else:
                ds[tag].value = ""

    return action


def set_value(value: str, create_if_missing: bool = False) -> TagAction:
    """Replace an element's value with a literal string.

    When ``create_if_missing`` is False (default) and the element is absent, the
    action is a no-op. When True, the element is created (with its
    data-dictionary VR) and then assigned, so the value is guaranteed to appear
    in the output -- used for mandatory de-identification evidence attributes.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag in ds:
            ds[tag].value = value
        elif create_if_missing:
            _create_element(ds, tag, value)

    return action


def set_param(
    field_name: str,
    *,
    default: str | None = None,
    fallback_field: str | None = None,
    create_if_missing: bool = False,
) -> TagAction:
    """Write a per-patient value read from :class:`DeidParameters`.

    Reads ``getattr(params, field_name)`` at apply time, falling back to
    ``getattr(params, fallback_field)`` when the primary is ``None`` and then to
    ``default``. The resolved value is written with :func:`set_value` semantics:
    present elements are overwritten, and absent elements are created only when
    ``create_if_missing`` is True.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        value = getattr(params, field_name)
        if value is None and fallback_field is not None:
            value = getattr(params, fallback_field)
        if value is None:
            value = default
        if value is None:
            return
        if tag in ds:
            ds[tag].value = value
        elif create_if_missing:
            _create_element(ds, tag, value)

    return action


def _hash_source_value(value: object, *, salt: str, params: DeidParameters) -> str:
    """Hash a source element value with the study-scoped identifier salt.

    Resolves ``params.study_id`` (or :data:`DEFAULT_STUDY_ID` when absent) and
    returns the :func:`hash_identifier` result for ``str(value)``.
    """
    study_id = params.study_id if params.study_id is not None else DEFAULT_STUDY_ID
    return hash_identifier(str(value), salt=salt, study_id=study_id)


def hash_value_identifier(*, salt: str) -> TagAction:
    """Hash the present value of an element with the study-scoped salt.

    Unlike :func:`hash_identifier_param`, this reads no per-patient parameter; it
    always hashes the element's current value. Used for TrackingID (0062,0020),
    which has no per-patient parameter. Study-scoped, so a hashed TrackingID and
    its paired TrackingUID (hashed with ``use_study_salt=True``) link
    consistently within a study.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag not in ds:
            return
        original = ds[tag].value
        if original:
            ds[tag].value = _hash_source_value(original, salt=salt, params=params)

    return action


def hash_identifier_param(
    field_name: str,
    *,
    salt: str,
    fallback_field: str | None = None,
    source_tag: BaseTag | None = None,
    placeholder: str = IDENTIFIER_PLACEHOLDER,
    create_if_missing: bool = False,
) -> TagAction:
    """Write a per-patient identifier, hashing the source element when absent.

    Precedence at apply time:

    1. ``getattr(params, field_name)`` (then ``fallback_field``) is written
       verbatim when supplied, so a caller-provided value always wins.
    2. Otherwise the original value of ``source_tag`` (defaulting to ``tag``) is
       hashed with :func:`hash_identifier`, salted with ``salt`` and
       ``params.study_id`` (or :data:`DEFAULT_STUDY_ID` when absent).
    3. When there is nothing to hash, ``placeholder`` is written as a fail-safe.

    The write follows :func:`set_value` semantics: present elements are
    overwritten, and absent elements are created only when ``create_if_missing``
    is True. ``source_tag`` lets PatientName derive from the original PatientID
    element so the two share one hash; the rule for PatientName must run before
    the PatientID rule mutates that element.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        value = getattr(params, field_name)
        if value is None and fallback_field is not None:
            value = getattr(params, fallback_field)
        if value is None:
            read_tag = source_tag if source_tag is not None else tag
            original = ds[read_tag].value if read_tag in ds else None
            if original:
                value = _hash_source_value(original, salt=salt, params=params)
            else:
                value = placeholder
        if tag in ds:
            ds[tag].value = value
        elif create_if_missing:
            _create_element(ds, tag, value)

    return action


def hash_uid(root: str, *, use_study_salt: bool = False) -> TagAction:
    """Hash UID using MD5, optionally salted with the study identifier.

    Reuses uid_utils.hashuid(). When ``use_study_salt`` is True the original UID
    value is concatenated with ``params.study_id`` (or :data:`DEFAULT_STUDY_ID`
    when absent) before hashing, so UIDs are hashed per study. When False the
    value is hashed with no salt.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag in ds and ds[tag].value:
            original = str(ds[tag].value)
            if use_study_salt:
                salt = params.study_id if params.study_id is not None else DEFAULT_STUDY_ID
                combined = original + salt
            else:
                combined = original
            ds[tag].value = hashuid(root, combined)

    return action


def dummy_for_vr(uid_root: str, *, use_study_salt: bool = False) -> TagAction:
    """Replace a present element with a VR-valid non-empty dummy value.

    Implements PS3.15 Table E.1-1 action code D in a VR-aware way. Present-only:
    an absent tag is left unchanged. The element VR is resolved from the element,
    mapping a runtime ``UN``/``OB`` (from an implicit-VR read) back to the
    data-dictionary VR so the dummy matches the intended VR. Replacements:

    - Text VRs -> ``"ANONYMIZED"`` (``UN`` receives the same token as bytes).
    - ``AS`` (Age String) -> ``"000Y"``.
    - Date/time VRs -> a VR-valid sentinel (``DA`` -> ``"19000101"``,
      ``TM`` -> ``"000000"``, ``DT`` -> ``"19000101000000"``).
    - Numeric VRs -> zero (``"0"`` for DS/IS; ``0``/``0.0`` for binary numerics).
    - ``UI`` -> hashed with ``uid_root`` and, when ``use_study_salt`` is True, the
      study identifier, matching the profile UID policy.
    - ``OB`` -> empty bytes; ``SQ`` -> empty sequence. A binary or sequence
      element has no scalar dummy, so an empty value is the safe equivalent.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag not in ds:
            return
        elem = ds[tag]
        try:
            raw_vr = elem.VR
        except (ValueError, NotImplementedError):
            return
        vr = raw_vr
        if vr in ("UN", "OB"):
            try:
                vr = dictionary_VR(tag)
            except KeyError:
                pass
        # Correct an implicit-VR placeholder so the new value is stored under the
        # dictionary VR (mirrors correct_implicit_vr_elements).
        if raw_vr in ("UN", "OB") and vr not in ("OB", "SQ"):
            elem.VR = vr
        if vr == "UI":
            original = str(elem.value) if elem.value else ""
            if use_study_salt:
                salt = params.study_id if params.study_id is not None else DEFAULT_STUDY_ID
                combined = original + salt
            else:
                combined = original
            elem.value = hashuid(uid_root, combined)
        elif vr == "AS":
            elem.value = "000Y"
        elif vr == "DA":
            elem.value = "19000101"
        elif vr == "TM":
            elem.value = "000000"
        elif vr == "DT":
            elem.value = "19000101000000"
        elif vr in ("DS", "IS"):
            elem.value = "0"
        elif vr in ("FL", "FD"):
            elem.value = 0.0
        elif vr in ("SL", "SS", "UL", "US"):
            elem.value = 0
        elif vr == "SQ":
            elem.value = []
        elif vr == "OB":
            elem.value = b""
        elif vr == "UN":
            # UN is written as raw bytes, so the dummy must be bytes, not str.
            elem.value = b"ANONYMIZED"
        elif vr in _DUMMY_TEXT_VRS:
            elem.value = "ANONYMIZED"

    return action


def jitter_date() -> TagAction:
    """Shift a DICOM date forward by the per-patient jitter amount.

    The shift is read from ``params.jitter``, which :meth:`DeidProfile.apply`
    resolves to a deterministic per-patient, per-study value before the rules
    run when the caller supplies none. Handles both VR=DA (YYYYMMDD, 8 chars) and
    VR=DT (YYYYMMDDHHMMSS.FFFFFF&ZZXX, up to 26 chars). The time portion and any
    trailing timezone offset of DT values are preserved; only the date component
    (first 8 characters) is shifted.

    Malformed dates in common non-DICOM formats (MM/DD/YY, MM/DD/YYYY,
    YYYY/MM/DD, DD.MM.YYYY) are normalized to YYYYMMDD before shifting.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if params.jitter is None:
            return
        if tag in ds and ds[tag].value:
            val = str(ds[tag].value)
            if len(val) < 6:
                return
            date_part, remainder = _extract_date_part(val)
            dt = _parse_dicom_date(date_part)
            if dt is None:
                return
            shifted = dt + timedelta(days=params.jitter)
            ds[tag].value = shifted.strftime("%Y%m%d") + remainder

    return action


# Alternate date formats encountered in non-compliant DICOM files.
_ALTERNATE_DATE_FORMATS = (
    "%m/%d/%Y",  # 10/14/2020
    "%m/%d/%y",  # 10/14/20
    "%Y/%m/%d",  # 2020/10/14
    "%d.%m.%Y",  # 14.10.2020
    "%m-%d-%Y",  # 10-14-2020
    "%Y-%m-%d",  # 2020-10-14
)


def _extract_date_part(val: str) -> tuple[str, str]:
    """Split a DA or DT value into date and remainder portions.

    Standard DICOM DA is exactly 8 digits. DT prepends 8-digit date
    to time components. Non-standard values may contain separators
    (slashes, dashes, dots) which expand the date portion beyond 8
    characters.
    """
    # Standard DICOM: first 8 characters are digits (DA or DT)
    if len(val) >= 8 and val[:8].isdigit():
        return val[:8], val[8:]
    # Non-standard: try to find a date with separators.
    # Match date patterns with separators (e.g., MM/DD/YYYY, YYYY-MM-DD)

    m = re.match(r"(\d{1,4}[/\.\-]\d{1,2}[/\.\-]\d{2,4})(.*)", val)
    if m:
        return m.group(1), m.group(2)
    return val, ""


def _parse_dicom_date(date_str: str) -> datetime | None:
    """Parse a date string, trying DICOM format first then common alternates."""
    # Standard DICOM YYYYMMDD
    if len(date_str) == 8 and date_str.isdigit():
        try:
            return datetime.strptime(date_str, "%Y%m%d")
        except ValueError:
            pass
    # Try alternate formats for non-compliant files
    for fmt in _ALTERNATE_DATE_FORMATS:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def append_value(text: str, create_if_missing: bool = False) -> TagAction:
    """Append text to a multi-valued element using backslash as separator.

    Used for DeIdentificationMethod, a multi-valued LO element. When
    ``create_if_missing`` is True and the element is absent, it is created (with
    its data-dictionary VR) so the value is guaranteed to appear in the output;
    otherwise an absent element is left untouched.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag in ds and ds[tag].value:
            current = str(ds[tag].value)
            ds[tag].value = current + "\\" + text
        elif tag in ds:
            ds[tag].value = text
        elif create_if_missing:
            _create_element(ds, tag, text)

    return action


def cap_age(threshold: int, replacement: str) -> TagAction:
    """Replace age if numeric portion exceeds threshold.

    DICOM VR=AS is exactly 4 characters: 3 digits + 1 suffix (D/W/M/Y).
    All non-numeric characters are stripped and the remainder is compared
    as an integer.
    """

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag in ds and ds[tag].value:
            val = str(ds[tag].value)
            digits = re.sub(r"[^0-9]", "", val)
            if digits and int(digits) > threshold:
                ds[tag].value = replacement

    return action


def if_exists(inner: TagAction) -> TagAction:
    """Apply inner action only when element is present."""

    def action(ds: Dataset, tag: BaseTag, params: DeidParameters) -> None:
        if tag in ds:
            inner(ds, tag, params)

    return action
