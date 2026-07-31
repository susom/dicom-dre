"""Golden characterization tests for UID and identifier hashing.

These tests pin the output of the identifier-hash algorithm to fixed digests so
any change to the hashing scheme (input composition, normalization, digest, or
truncation) is caught. The salt and study identifier are fixed literals, not
random, so the expected digests stay stable across runs.
"""

from __future__ import annotations

from dicom_dre.uid_utils import hash_identifier
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

    def test_patient_id_changes_jitter(self) -> None:
        """The jitter varies with the patient identifier (longitudinal per patient)."""
        values = {stable_jitter(GOLDEN_SALT, GOLDEN_STUDY_ID, f"MRN-{i}") for i in range(50)}
        assert len(values) > 1, "Different PatientIDs should vary the derived jitter"

    def test_study_id_changes_jitter(self) -> None:
        """The same patient in different studies gets different jitter."""
        values = {stable_jitter(GOLDEN_SALT, f"STUDY-{i}", GOLDEN_PATIENT_ID) for i in range(50)}
        assert len(values) > 1, "Different study_ids should vary the derived jitter"

    def test_salt_changes_jitter(self) -> None:
        """The jitter varies with the salt."""
        values = {stable_jitter(f"salt-{i}", GOLDEN_STUDY_ID, GOLDEN_PATIENT_ID) for i in range(50)}
        assert len(values) > 1, "Different salts should vary the derived jitter"
