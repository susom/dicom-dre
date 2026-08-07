"""Golden characterization tests for UID and identifier hashing.

These tests pin the output of the identifier-hash algorithm to fixed digests so
any change to the hashing scheme (input composition, normalization, digest, or
truncation) is caught. The salt and study identifier are fixed literals, not
random, so the expected digests stay stable across runs.
"""

from __future__ import annotations

import pytest

from dicom_dre.uid_utils import hash_identifier
from dicom_dre.uid_utils import hashuid
from dicom_dre.uid_utils import stable_jitter


# Fixed inputs standing in for a generated salt and a study identifier.
GOLDEN_SALT = "amber-thistle-harbor-lunar-eii5a"
GOLDEN_STUDY_ID = "STUDY-2f9c1a"
GOLDEN_PATIENT_ID = "MRN123456"


class TestHashIdentifierGolden:
    """Pinned outputs of hash_identifier for fixed salt and study identifier."""

    def test_patient_id_digest_is_stable(self) -> None:
        """A known PatientID hashes to a fixed 16-character digest."""
        digest = hash_identifier("MRN123456", salt=GOLDEN_SALT, study_id=GOLDEN_STUDY_ID)
        assert digest == "5D30D073C6D86D05", f"PatientID digest changed: got {digest!r}"

    def test_accession_digest_is_stable(self) -> None:
        """A known AccessionNumber hashes to a fixed 16-character digest."""
        digest = hash_identifier("ACC987654", salt=GOLDEN_SALT, study_id=GOLDEN_STUDY_ID)
        assert digest == "3B982A985329CB4B", f"AccessionNumber digest changed: got {digest!r}"

    def test_normalization_is_stable(self) -> None:
        """Surrounding whitespace and case do not change the digest."""
        canonical = hash_identifier("MRN123456", salt=GOLDEN_SALT, study_id=GOLDEN_STUDY_ID)
        noisy = hash_identifier("  mrn123456  ", salt=GOLDEN_SALT, study_id=GOLDEN_STUDY_ID)
        assert noisy == canonical, f"Normalization changed the digest: {noisy!r} != {canonical!r}"

    def test_salt_changes_digest(self) -> None:
        """A different salt produces a different digest for the same identifier."""
        base = hash_identifier("MRN123456", salt=GOLDEN_SALT, study_id=GOLDEN_STUDY_ID)
        other = hash_identifier("MRN123456", salt="different-salt", study_id=GOLDEN_STUDY_ID)
        assert other != base, "A different salt should change the digest"

    def test_study_id_changes_digest(self) -> None:
        """A different study identifier produces a different digest."""
        base = hash_identifier("MRN123456", salt=GOLDEN_SALT, study_id=GOLDEN_STUDY_ID)
        other = hash_identifier("MRN123456", salt=GOLDEN_SALT, study_id="OTHER-STUDY")
        assert other != base, "A different study_id should change the digest"


class TestStableJitterGolden:
    """Pinned and property-based behavior of the derived per-patient jitter."""

    def test_digest_is_stable(self) -> None:
        """Fixed salt, study, and patient identifiers yield a fixed jitter."""
        days = stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, GOLDEN_PATIENT_ID)
        assert days == 4, f"Stable jitter changed: got {days!r}"

    def test_deterministic_for_same_inputs(self) -> None:
        """Repeated calls with the same inputs return the same jitter."""
        first = stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, GOLDEN_PATIENT_ID)
        second = stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, GOLDEN_PATIENT_ID)
        assert first == second, "Stable jitter should be deterministic"

    def test_within_range_and_never_zero(self) -> None:
        """Across many patients the jitter stays in [-30, 30] and is never zero."""
        values = {stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, f"MRN-{i}") for i in range(5000)}
        assert min(values) >= -30, f"Jitter fell below -30: {min(values)}"
        assert max(values) <= 30, f"Jitter exceeded 30: {max(values)}"
        assert 0 not in values, "Jitter must never be zero"

    @pytest.mark.parametrize(
        "field",
        ["patient_id", "study_id", "salt"],
    )
    def test_input_sensitivity_varies_jitter(self, field: str) -> None:
        """Varying any one of patient, study, or salt spreads the derived jitter.

        Each input feeds the jitter derivation, so holding the other two fixed
        and varying one must produce more than a single value across samples.
        """

        def jitter_for(index: int) -> int:
            if field == "patient_id":
                return stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, f"MRN-{index}")
            if field == "study_id":
                return stable_jitter(GOLDEN_SALT, f"STUDY-{index}", GOLDEN_PATIENT_ID)
            return stable_jitter(f"salt-{index}", GOLDEN_STUDY_ID, GOLDEN_PATIENT_ID)

        values = {jitter_for(i) for i in range(50)}
        assert len(values) > 1, f"Varying {field} should spread the derived jitter, got {values}"


class TestHashIdentifierEdges:
    """Empty-input and maxlen handling of hash_identifier."""

    def test_empty_identifier_raises(self) -> None:
        """An empty identifier is rejected."""
        with pytest.raises(ValueError, match="Identifier for hash cannot be empty"):
            hash_identifier("", salt=GOLDEN_SALT, study_id=GOLDEN_STUDY_ID)

    def test_large_maxlen_returns_full_digest(self) -> None:
        """A maxlen at or above the digest length returns the full 64-character digest."""
        digest = hash_identifier("MRN123456", salt=GOLDEN_SALT, study_id=GOLDEN_STUDY_ID, maxlen=64)
        assert len(digest) == 64, f"Expected the full 64-character digest, got {len(digest)}"

    def test_small_maxlen_truncates(self) -> None:
        """A small maxlen truncates the digest to that length."""
        digest = hash_identifier("MRN123456", salt=GOLDEN_SALT, study_id=GOLDEN_STUDY_ID, maxlen=8)
        assert len(digest) == 8, f"Expected an 8-character digest, got {len(digest)}"


class TestStableJitterRanges:
    """Range handling and validation of stable_jitter."""

    def test_positive_only_range(self) -> None:
        """A range without zero yields values within that positive range."""
        values = {stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, f"MRN-{i}", low=1, high=10) for i in range(500)}
        assert min(values) >= 1, f"Value fell below 1: {min(values)}"
        assert max(values) <= 10, f"Value exceeded 10: {max(values)}"

    def test_negative_only_range(self) -> None:
        """A negative-only range yields values within that range."""
        values = {stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, f"MRN-{i}", low=-10, high=-1) for i in range(500)}
        assert min(values) >= -10, f"Value fell below -10: {min(values)}"
        assert max(values) <= -1, f"Value exceeded -1: {max(values)}"

    def test_symmetric_boundary_range_excludes_zero(self) -> None:
        """A [-1, 1] range yields only -1 and 1, never zero."""
        values = {stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, f"MRN-{i}", low=-1, high=1) for i in range(500)}
        assert values <= {-1, 1}, f"Boundary range produced unexpected values: {values}"
        assert 0 not in values, "Zero must be excluded from the boundary range"

    def test_empty_range_raises(self) -> None:
        """A range containing only zero has no valid non-zero value and is rejected."""
        with pytest.raises(ValueError, match="jitter range must contain at least one non-zero value"):
            stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, GOLDEN_PATIENT_ID, low=0, high=0)


class TestHashuid:
    """UID hashing: prefix normalization, truncation, and the leading-zero branch."""

    def test_prefix_without_trailing_dot_is_normalized(self) -> None:
        """A prefix with no trailing dot has one appended before the digits."""
        result = hashuid("1.2.840.99", "1.2.3")
        assert result.startswith("1.2.840.99."), f"Expected a dot after the prefix, got {result!r}"

    def test_prefix_with_trailing_dot_is_unchanged(self) -> None:
        """A prefix that already ends with a dot is not given a second dot."""
        result = hashuid("1.2.840.99.", "1.2.3")
        assert result.startswith("1.2.840.99."), f"Expected the prefix preserved, got {result!r}"
        assert not result.startswith("1.2.840.99.."), "The prefix should not gain a double dot"

    def test_result_is_deterministic(self) -> None:
        """The same prefix and UID always hash to the same value."""
        first = hashuid("1.2.840.99", "1.2.3")
        second = hashuid("1.2.840.99", "1.2.3")
        assert first == second, "hashuid should be deterministic for the same inputs"

    def test_result_truncated_to_64_characters(self) -> None:
        """A long prefix truncates the result to 64 characters."""
        long_prefix = "9" * 80
        result = hashuid(long_prefix, "1.2.3")
        assert len(result) == 64, f"Expected a 64-character result, got {len(result)}"

    def test_leading_zero_digest_gets_nine_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A digest whose decimal form starts with zero gets a '9' inserted."""
        import dicom_dre.uid_utils as uid_utils

        class _FakeMd5:
            def hexdigest(self) -> str:
                return "0" * 32

        monkeypatch.setattr(uid_utils.hashlib, "md5", lambda _data, **_kwargs: _FakeMd5())
        result = hashuid("1.2.840.99", "1.2.3")
        assert result == "1.2.840.99.90", f"Expected a '9' before the zero digit, got {result!r}"
