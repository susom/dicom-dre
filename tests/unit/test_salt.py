"""Unit tests for identifier-hash salt generation and persistence.

Exercises the memorable-passphrase generator, the per-user salt path resolution,
and the load-or-create persistence logic, including file permissions and the
empty-file-as-absent rule. All file I/O uses ``tmp_path``; environment lookups
use ``monkeypatch``.
"""

from __future__ import annotations

import stat
import string
from typing import TYPE_CHECKING

import pytest

from dicom_dre.salt import _WORDS
from dicom_dre.salt import default_salt_path
from dicom_dre.salt import generate_passphrase
from dicom_dre.salt import load_or_create_salt
from dicom_dre.salt import read_salt


if TYPE_CHECKING:
    from pathlib import Path


class TestGeneratePassphrase:
    """Passphrase generation shape, charset, validation, and uniqueness."""

    def test_default_shape_is_four_words_plus_suffix(self) -> None:
        """The default passphrase is four words followed by a suffix segment."""
        parts = generate_passphrase().split("-")
        assert len(parts) == 5, f"Expected four words plus one suffix segment, got {parts!r}"

    def test_words_are_drawn_from_the_pool(self) -> None:
        """Every word segment comes from the curated word pool."""
        parts = generate_passphrase().split("-")
        words = parts[:-1]
        for word in words:
            assert word in _WORDS, f"Word {word!r} should come from the pool"

    def test_suffix_length_defaults_to_five(self) -> None:
        """The default suffix segment is five characters long."""
        suffix = generate_passphrase().split("-")[-1]
        assert len(suffix) == 5, f"Expected a five-character suffix, got {suffix!r}"

    def test_suffix_is_lowercase_alphanumeric(self) -> None:
        """The suffix uses only lowercase letters and digits."""
        allowed = set(string.ascii_lowercase + string.digits)
        suffix = generate_passphrase().split("-")[-1]
        assert set(suffix) <= allowed, f"Suffix {suffix!r} should be lowercase alphanumeric"

    def test_custom_word_count_and_suffix_length(self) -> None:
        """Custom word_count and suffix_length control the segment layout."""
        parts = generate_passphrase(word_count=2, suffix_length=8).split("-")
        assert len(parts) == 3, f"Expected two words plus one suffix segment, got {parts!r}"
        assert len(parts[-1]) == 8, f"Expected an eight-character suffix, got {parts[-1]!r}"

    def test_custom_separator(self) -> None:
        """A custom separator joins the words and precedes the suffix."""
        result = generate_passphrase(word_count=3, separator=".")
        parts = result.split(".")
        assert len(parts) == 4, f"Expected three words plus one suffix segment, got {parts!r}"
        assert "-" not in result, f"No default hyphen should appear, got {result!r}"

    def test_suffix_makes_results_unique(self) -> None:
        """Repeated generation yields distinct values because of the random suffix."""
        results = {generate_passphrase() for _ in range(200)}
        assert len(results) == 200, f"Expected 200 unique passphrases, got {len(results)}"

    def test_word_count_below_one_raises(self) -> None:
        """A word_count below one is rejected."""
        with pytest.raises(ValueError, match="word_count must be at least 1"):
            generate_passphrase(word_count=0)

    def test_suffix_length_below_one_raises(self) -> None:
        """A suffix_length below one is rejected."""
        with pytest.raises(ValueError, match="suffix_length must be at least 1"):
            generate_passphrase(suffix_length=0)


class TestDefaultSaltPath:
    """Per-user salt path resolution from environment."""

    def test_honors_xdg_config_home(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """XDG_CONFIG_HOME roots the salt path when set."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        expected = tmp_path / "cfg" / "dicom-dre" / "salt"
        assert default_salt_path() == expected, f"Expected {expected}, got {default_salt_path()}"

    def test_falls_back_to_home_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without XDG_CONFIG_HOME the path falls back to ~/.config."""
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        expected = tmp_path / "home" / ".config" / "dicom-dre" / "salt"
        assert default_salt_path() == expected, f"Expected {expected}, got {default_salt_path()}"


class TestReadSalt:
    """Read-only salt loading without side effects."""

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        """A missing salt file yields None and writes nothing."""
        path = tmp_path / "salt"
        assert read_salt(path) is None, "A missing salt file should read as None"
        assert not path.exists(), "read_salt must not create the file"

    def test_returns_none_when_empty(self, tmp_path: Path) -> None:
        """A whitespace-only salt file yields None."""
        path = tmp_path / "salt"
        path.write_text("   \n", encoding="utf-8")
        assert read_salt(path) is None, "A whitespace-only salt file should read as None"

    def test_returns_stored_value(self, tmp_path: Path) -> None:
        """A populated salt file yields its stripped contents."""
        path = tmp_path / "salt"
        path.write_text("preset-salt-value\n", encoding="utf-8")
        assert read_salt(path) == "preset-salt-value", "read_salt should return the stored salt"

    def test_uses_default_path_when_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no argument the default path is read."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        default_salt_path().parent.mkdir(parents=True)
        default_salt_path().write_text("from-default\n", encoding="utf-8")
        assert read_salt() == "from-default", "read_salt should read the default path"


class TestLoadOrCreateSalt:
    """Persistence, permissions, and reuse of the salt file."""

    def test_creates_salt_when_absent(self, tmp_path: Path) -> None:
        """A missing salt file is created and reported as newly created."""
        path = tmp_path / "dicom-dre" / "salt"
        salt, created = load_or_create_salt(path)
        assert created is True, "A missing salt file should be reported as created"
        assert path.exists(), "The salt file should be written"
        assert path.read_text(encoding="utf-8").strip() == salt, "The stored salt should match the returned value"

    def test_created_salt_has_passphrase_shape(self, tmp_path: Path) -> None:
        """A generated salt is a hyphenated passphrase with a suffix."""
        path = tmp_path / "salt"
        salt, _ = load_or_create_salt(path)
        assert len(salt.split("-")) == 5, f"Expected a four-word passphrase plus suffix, got {salt!r}"

    def test_file_and_directory_permissions(self, tmp_path: Path) -> None:
        """The salt file is 0600 and its parent directory 0700."""
        path = tmp_path / "dicom-dre" / "salt"
        load_or_create_salt(path)
        file_mode = stat.S_IMODE(path.stat().st_mode)
        dir_mode = stat.S_IMODE(path.parent.stat().st_mode)
        assert file_mode == 0o600, f"Expected file mode 0o600, got {oct(file_mode)}"
        assert dir_mode == 0o700, f"Expected directory mode 0o700, got {oct(dir_mode)}"

    def test_existing_salt_is_reused(self, tmp_path: Path) -> None:
        """An existing salt file is returned unchanged and not reported as created."""
        path = tmp_path / "salt"
        path.write_text("preset-salt-value\n", encoding="utf-8")
        salt, created = load_or_create_salt(path)
        assert created is False, "An existing salt file should not be reported as created"
        assert salt == "preset-salt-value", f"Expected the stored salt, got {salt!r}"

    def test_second_call_returns_first_salt(self, tmp_path: Path) -> None:
        """A second call reuses the salt persisted by the first."""
        path = tmp_path / "salt"
        first, first_created = load_or_create_salt(path)
        second, second_created = load_or_create_salt(path)
        assert first_created is True, "The first call should create the salt"
        assert second_created is False, "The second call should reuse the salt"
        assert second == first, f"Expected the persisted salt {first!r}, got {second!r}"

    def test_empty_file_treated_as_absent(self, tmp_path: Path) -> None:
        """A whitespace-only salt file is replaced with a new salt."""
        path = tmp_path / "salt"
        path.write_text("   \n", encoding="utf-8")
        salt, created = load_or_create_salt(path)
        assert created is True, "A whitespace-only file should be treated as absent"
        assert salt.strip() != "", "A non-empty salt should be generated"
        assert path.read_text(encoding="utf-8").strip() == salt, "The new salt should be written to the file"

    def test_uses_default_path_when_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no path argument the salt is written to the default location."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
        salt, created = load_or_create_salt()
        expected = tmp_path / "cfg" / "dicom-dre" / "salt"
        assert created is True, "A missing default salt file should be created"
        assert expected.exists(), f"The salt should be written to {expected}"
        assert expected.read_text(encoding="utf-8").strip() == salt, "The stored salt should match the returned value"
