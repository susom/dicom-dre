"""UID hashing utilities for DICOM de-identification."""

import hashlib


def hash_identifier(identifier: str, *, salt: str, study_id: str, maxlen: int = 16) -> str:
    """Hash a patient identifier deterministically using SHA-256.

    The identifier is stripped of surrounding whitespace and uppercased, then
    combined with the salt and study identifier as ``salt|study_id|identifier``
    before hashing. The uppercase hex digest is truncated to ``maxlen``
    characters. Used to derive replacement PatientID/AccessionNumber values when
    the caller supplies no explicit value.

    Args:
        identifier: The original identifier to hash. Must be non-empty.
        salt: Deployment-wide salt applied to every identifier.
        study_id: Study identifier that scopes the hash.
        maxlen: Maximum length of the returned digest.

    Returns:
        The truncated uppercase hex digest.

    Raises:
        ValueError: If identifier is empty.
    """
    if not identifier:
        raise ValueError("Identifier for hash cannot be empty")

    scrubbed_identifier = identifier.strip().upper()
    salted_string = f"{salt}|{study_id}|{scrubbed_identifier}"
    result = hashlib.sha256(salted_string.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    if len(result) <= maxlen:
        return result
    return result[:maxlen]


def stable_jitter(salt: str, study_id: str, patient_id: str, *, low: int = -30, high: int = 30) -> int:
    """Derive a deterministic non-zero date shift from salt, study, and patient.

    Maps a SHA-256 digest of the salt, study identifier, and patient identifier
    onto the inclusive range ``[low, high]`` with zero excluded. The same patient
    within one study always shifts by the same non-zero amount (longitudinal
    consistency), while the same patient in a different study shifts differently.
    Used to jitter dates when the caller supplies no explicit jitter.

    Args:
        salt: Deployment-wide salt.
        study_id: Study identifier that scopes the shift.
        patient_id: Source (PHI) patient identifier that scopes the shift.
        low: Inclusive lower bound of the shift in days.
        high: Inclusive upper bound of the shift in days.

    Returns:
        An integer in ``[low, high]`` that is never zero.

    Raises:
        ValueError: If the range contains no non-zero value.
    """
    count = high - low + 1
    if low <= 0 <= high:
        count -= 1  # zero is excluded from the output range
    if count < 1:
        raise ValueError("jitter range must contain at least one non-zero value")

    digest = hashlib.sha256(f"{salt}|{study_id}|{patient_id}|jitter".encode(), usedforsecurity=False).hexdigest()
    value = low + (int(digest, 16) % count)
    if low <= 0 <= high and value >= 0:
        value += 1  # skip over the excluded zero
    return value


def hashuid(prefix: str, uid: str) -> str:
    """Hash a DICOM UID deterministically using MD5.

    Creates a deterministic replacement UID by computing the MD5 hash of the
    original UID, converting it to a base-10 digit string, and prepending the
    given prefix.

    Args:
        prefix: The prefix for the new UID (e.g., "1.2.840.4267.32.")
        uid: The original UID to hash

    Returns:
        str: A new UID with the format: prefix + [extra] + md5_hash, truncated to 64 characters
             where [extra] is "9" if the MD5 hash starts with "0", otherwise empty
    """
    prefix = prefix.strip()
    if prefix and not prefix.endswith("."):
        prefix += "."

    hash_string = hashlib.md5(uid.encode("utf-8"), usedforsecurity=False).hexdigest()  # noqa: S324
    hash_int = int(hash_string, 16)
    hash_string = str(hash_int)

    extra = "9" if hash_string.startswith("0") else ""
    newuid = prefix + extra + hash_string

    if len(newuid) > 64:
        newuid = newuid[:64]

    return newuid
