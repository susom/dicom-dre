"""Persistent identifier-hash salt generation and storage.

The identifier-hash salt is a deployment secret mixed into PatientID,
PatientName, and AccessionNumber hashing. When a caller supplies no salt, the
CLI loads a per-user salt from disk, generating and persisting a memorable
passphrase on first use so the resulting pseudonyms stay reproducible across
runs. Resolution occurs outside the de-identification engine, which performs no
settings lookups or file I/O of its own.
"""

from __future__ import annotations

import os
import secrets
import string
from pathlib import Path


# Curated lowercase words for memorable passphrases. Kept distinct so every
# choice contributes uniform entropy.
_WORDS: tuple[str, ...] = (
    "amber",
    "anchor",
    "apple",
    "arrow",
    "autumn",
    "badge",
    "basil",
    "beacon",
    "birch",
    "bishop",
    "bison",
    "blossom",
    "bramble",
    "breeze",
    "bright",
    "bronze",
    "brook",
    "canyon",
    "cedar",
    "cherry",
    "cinder",
    "cliff",
    "clover",
    "cobalt",
    "comet",
    "coral",
    "cotton",
    "crane",
    "crest",
    "crimson",
    "crystal",
    "dagger",
    "daisy",
    "dawn",
    "delta",
    "ember",
    "fable",
    "falcon",
    "fern",
    "fjord",
    "flint",
    "forest",
    "garnet",
    "ginger",
    "glacier",
    "granite",
    "harbor",
    "hazel",
    "heron",
    "hollow",
    "ivory",
    "jade",
    "jasper",
    "jungle",
    "kernel",
    "lagoon",
    "lantern",
    "laurel",
    "ledger",
    "lily",
    "linen",
    "lotus",
    "lunar",
    "maple",
    "marble",
    "meadow",
    "mellow",
    "meteor",
    "mica",
    "mint",
    "moss",
    "mountain",
    "nectar",
    "nimbus",
    "nomad",
    "oaken",
    "ocean",
    "olive",
    "onyx",
    "opal",
    "orbit",
    "otter",
    "pebble",
    "pepper",
    "pewter",
    "pine",
    "piper",
    "plume",
    "pollen",
    "poppy",
    "prairie",
    "quartz",
    "quill",
    "quince",
    "radish",
    "raven",
    "reed",
    "ridge",
    "river",
    "robin",
    "rustic",
    "saffron",
    "sage",
    "sable",
    "sand",
    "sapphire",
    "scarlet",
    "sequoia",
    "shadow",
    "shale",
    "sierra",
    "silver",
    "sleet",
    "slate",
    "sparrow",
    "spruce",
    "storm",
    "summit",
    "sunset",
    "tamarind",
    "teak",
    "thistle",
    "thunder",
    "timber",
    "topaz",
    "tulip",
    "tundra",
    "umber",
    "valley",
    "velvet",
    "vine",
    "walnut",
    "willow",
    "winter",
    "wren",
    "zephyr",
)


def generate_passphrase(word_count: int = 4, separator: str = "-", suffix_length: int = 5) -> str:
    """Return a memorable passphrase with a random alphanumeric suffix.

    The suffix guarantees uniqueness even when words repeat, so every generated
    salt differs regardless of the word draw.

    Args:
        word_count: Number of words to join. Must be at least 1.
        separator: String placed between words and before the suffix.
        suffix_length: Number of random lowercase-alphanumeric characters to
            append. Must be at least 1.

    Returns:
        The generated passphrase, for example ``"amber-thistle-harbor-lunar-eii5a"``.

    Raises:
        ValueError: If word_count or suffix_length is less than 1.
    """
    if word_count < 1:
        raise ValueError("word_count must be at least 1")
    if suffix_length < 1:
        raise ValueError("suffix_length must be at least 1")
    words = separator.join(secrets.choice(_WORDS) for _ in range(word_count))
    alphabet = string.ascii_lowercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(suffix_length))
    return f"{words}{separator}{suffix}"


def default_salt_path() -> Path:
    """Return the per-user salt file path, honoring ``XDG_CONFIG_HOME``."""
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "dicom-dre" / "salt"


def read_salt(path: Path | None = None) -> str | None:
    """Return the persisted salt, or ``None`` when it is absent or empty.

    A file that exists but is empty (or whitespace only) is treated as absent.

    Args:
        path: Salt file location. Defaults to :func:`default_salt_path`.

    Returns:
        The stored salt, or ``None`` when no usable salt is present.
    """
    if path is None:
        path = default_salt_path()
    try:
        existing = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return existing or None


def load_or_create_salt(path: Path | None = None) -> tuple[str, bool]:
    """Load the persisted salt, generating and saving one when absent.

    The salt file is written with ``0600`` permissions and its parent directory
    with ``0700`` so the secret is not world-readable. A file that exists but is
    empty (or whitespace only) is treated as absent and replaced.

    Args:
        path: Salt file location. Defaults to :func:`default_salt_path`.

    Returns:
        A tuple ``(salt, created)`` where ``created`` is True when a new salt was
        generated and written.
    """
    if path is None:
        path = default_salt_path()
    existing = read_salt(path)
    if existing is not None:
        return existing, False

    salt = generate_passphrase()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{salt}\n", encoding="utf-8")
    try:
        path.parent.chmod(0o700)
        path.chmod(0o600)
    except OSError:
        # Permission tightening is best-effort on filesystems that reject chmod.
        pass
    return salt, True
