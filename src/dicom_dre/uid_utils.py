"""UID hashing utilities for DICOM de-identification."""

import hashlib


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

    hash_string = hashlib.md5(uid.encode("utf-8")).hexdigest()  # noqa: S324
    hash_int = int(hash_string, 16)
    hash_string = str(hash_int)

    extra = "9" if hash_string.startswith("0") else ""
    newuid = prefix + extra + hash_string

    if len(newuid) > 64:
        newuid = newuid[:64]

    return newuid
