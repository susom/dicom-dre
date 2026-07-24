"""Tag action factories for DICOM metadata de-identification.

Each factory returns a callable with signature (Dataset, BaseTag) -> None.
Factories close over their arguments at profile construction time.
"""

import re
from collections.abc import Callable
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING
from typing import cast

from pydicom.datadict import dictionary_VR
from pydicom.dataset import Dataset
from pydicom.tag import BaseTag

from dicom_dre.uid_utils import hashuid


if TYPE_CHECKING:
    from dicom_dre.text_redactor import TextRedactor


TagAction = Callable[[Dataset, BaseTag], None]


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


def keep() -> "TagAction":
    """Preserve element unchanged."""

    def action(ds: Dataset, tag: BaseTag) -> None:
        pass

    return action


def remove() -> "TagAction":
    """Delete element from dataset."""

    def action(ds: Dataset, tag: BaseTag) -> None:
        if tag in ds:
            del ds[tag]

    return action


def empty() -> "TagAction":
    """Replace element value with zero-length value.

    For SQ (sequence) elements, sets the value to an empty list rather
    than an empty string. Setting a string value on a VR=SQ element
    raises an error in pydicom 3.x.
    """

    def action(ds: Dataset, tag: BaseTag) -> None:
        if tag in ds:
            if ds[tag].VR == "SQ":
                ds[tag].value = []
            else:
                ds[tag].value = ""

    return action


def set_value(value: str, create_if_missing: bool = False) -> "TagAction":
    """Replace an element's value with a literal string.

    When ``create_if_missing`` is False (default) and the element is absent, the
    action is a no-op. When True, the element is created (with its
    data-dictionary VR) and then assigned, so the value is guaranteed to appear
    in the output -- used for mandatory de-identification evidence attributes.
    """

    def action(ds: Dataset, tag: BaseTag) -> None:
        if tag in ds:
            ds[tag].value = value
        elif create_if_missing:
            _create_element(ds, tag, value)

    return action


def redact_text(redactor: "TextRedactor") -> "TagAction":
    """Redact free text in an element using an allowlist redactor.

    Reads the element's current value, redacts tokens not present in the
    allowlist, and writes the result back. Missing elements are left
    untouched; present but empty elements are set to an empty string,
    following the "empty/missing source redacts to empty" convention for
    free-text description fields.
    """

    def action(ds: Dataset, tag: BaseTag) -> None:
        if tag not in ds:
            return
        value = ds[tag].value
        if value:
            ds[tag].value = cast(str, redactor.redact_text(text=str(value), track_redacted=False))
        else:
            ds[tag].value = ""

    return action


def hash_uid(root: str, salt: str = "") -> "TagAction":
    """Hash UID using MD5 with optional salt.

    Reuses uid_utils.hashuid(). When salt is provided, the original UID
    value is concatenated with the salt before hashing, so UIDs are hashed
    per study (the salt is typically the study identifier).
    """

    def action(ds: Dataset, tag: BaseTag) -> None:
        if tag in ds and ds[tag].value:
            original = str(ds[tag].value)
            combined = original + salt if salt else original
            ds[tag].value = hashuid(root, combined)

    return action


def jitter_date(days: int) -> "TagAction":
    """Shift a DICOM date forward by N days.

    Handles both VR=DA (YYYYMMDD, 8 chars) and VR=DT (YYYYMMDDHHMMSS.FFFFFF
    &ZZXX, up to 26 chars). The time portion and any trailing timezone offset
    of DT values are preserved; only the date component (first 8 characters)
    is shifted.

    Malformed dates in common non-DICOM formats (MM/DD/YY, MM/DD/YYYY,
    YYYY/MM/DD, DD.MM.YYYY) are normalized to YYYYMMDD before shifting.
    """

    def action(ds: Dataset, tag: BaseTag) -> None:
        if tag in ds and ds[tag].value:
            val = str(ds[tag].value)
            if len(val) < 6:
                return
            date_part, remainder = _extract_date_part(val)
            dt = _parse_dicom_date(date_part)
            if dt is None:
                return
            shifted = dt + timedelta(days=days)
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


def _parse_dicom_date(date_str: str) -> "datetime | None":
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


def append_value(text: str, create_if_missing: bool = False) -> "TagAction":
    """Append text to a multi-valued element using backslash as separator.

    Used for DeIdentificationMethod, a multi-valued LO element. When
    ``create_if_missing`` is True and the element is absent, it is created (with
    its data-dictionary VR) so the value is guaranteed to appear in the output;
    otherwise an absent element is left untouched.
    """

    def action(ds: Dataset, tag: BaseTag) -> None:
        if tag in ds and ds[tag].value:
            current = str(ds[tag].value)
            ds[tag].value = current + "\\" + text
        elif tag in ds:
            ds[tag].value = text
        elif create_if_missing:
            _create_element(ds, tag, text)

    return action


def cap_age(threshold: int, replacement: str) -> "TagAction":
    """Replace age if numeric portion exceeds threshold.

    DICOM VR=AS is exactly 4 characters: 3 digits + 1 suffix (D/W/M/Y).
    All non-numeric characters are stripped and the remainder is compared
    as an integer.
    """

    def action(ds: Dataset, tag: BaseTag) -> None:
        if tag in ds and ds[tag].value:
            val = str(ds[tag].value)
            digits = re.sub(r"[^0-9]", "", val)
            if digits and int(digits) > threshold:
                ds[tag].value = replacement

    return action


def if_exists(inner: "TagAction") -> "TagAction":
    """Apply inner action only when element is present."""

    def action(ds: Dataset, tag: BaseTag) -> None:
        if tag in ds:
            inner(ds, tag)

    return action


def process() -> "TagAction":
    """Marker action for a processed sequence.

    A processed sequence applies the full de-identification rule set (element
    rules and global removal) recursively to each item dataset of an SQ
    element. That recursion is driven by ``DeidProfile`` using its own
    ``self.rules``, so this action performs no work when invoked directly; it
    exists only to mark the tag as a processed sequence via
    ``is_process_action``. Driving the recursion from the profile (rather than
    closing over a rules dict here) keeps derived profiles correct without
    rebinding: the profile always recurses with its own final rule set.
    """

    def action(ds: Dataset, tag: BaseTag) -> None:
        # Recursion into the sequence items is handled by DeidProfile
        # using its own rule set; nothing to do here.
        pass

    action.is_process_action = True  # type: ignore[attr-defined]
    return action
