"""Shared de-identification invariants that hold for every profile.

Each test takes an ``expectation`` argument that ``conftest.pytest_generate_tests``
parametrizes over every buildable profile (``default``, ``lds``, ``lds-no-dob``,
``strict``), with the profile name as the test ID. The canonical dataset and
the harness helpers arrive through the ``canonical_dataset`` and
``profile_harness`` fixtures, so this module imports nothing from the tests
package.
"""

from __future__ import annotations


def _deidentification_method_codes(ds) -> set[str]:
    """Return the CodeValue set from the De-identification Method Code Sequence."""
    from pydicom.tag import Tag

    seq_tag = Tag(0x0012, 0x0064)
    code_value_tag = Tag(0x0008, 0x0100)
    if seq_tag not in ds:
        return set()
    return {str(item[code_value_tag].value) for item in ds[seq_tag].value if code_value_tag in item}


def test_patient_identity_removed_is_yes(expectation, canonical_dataset, profile_harness) -> None:
    """Every profile sets PatientIdentityRemoved (0012,0062) to YES."""
    from pydicom.tag import Tag

    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    tag = Tag(0x0012, 0x0062)
    assert tag in result, f"{expectation.name}: PatientIdentityRemoved (0012,0062) should be present"
    assert result[tag].value == "YES", (
        f"{expectation.name}: PatientIdentityRemoved should be 'YES', got {result[tag].value!r}"
    )


def test_no_unexpected_phi_sentinel_survives(expectation, canonical_dataset, profile_harness) -> None:
    """No PHI sentinel survives except the profile's allowed sentinels."""
    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    allowed_values = {profile_harness.sentinels[keyword] for keyword in expectation.allowed_sentinels}
    survivors = profile_harness.find_survivors(result, allowed_values)
    assert not survivors, (
        f"{expectation.name}: unexpected PHI sentinel(s) survived de-identification: {sorted(survivors)}"
    )


def test_allowed_sentinels_actually_survive(expectation, canonical_dataset, profile_harness) -> None:
    """Each sentinel declared allowed is present after de-identification.

    Guards the allow-list against drift: a sentinel listed as allowed but absent
    from the output would silently mask a regression in the survivor check.
    """
    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    present = profile_harness.find_survivors(result, allowed=set())
    for keyword in expectation.allowed_sentinels:
        value = profile_harness.sentinels[keyword]
        assert value in present, (
            f"{expectation.name}: allowed sentinel {keyword!r} ({value!r}) should survive but was absent"
        )


def test_method_code_sequence_contains_required_codes(expectation, canonical_dataset, profile_harness) -> None:
    """The method code sequence contains every required code and no forbidden code."""
    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    codes = _deidentification_method_codes(result)
    missing = expectation.required_method_codes - codes
    assert not missing, (
        f"{expectation.name}: required method code(s) missing: {sorted(missing)} (present: {sorted(codes)})"
    )
    forbidden_present = expectation.forbidden_method_codes & codes
    assert not forbidden_present, f"{expectation.name}: forbidden method code(s) present: {sorted(forbidden_present)}"


def test_private_decoy_elements_removed(expectation, canonical_dataset, profile_harness) -> None:
    """The decoy private creator and data element are removed by every profile."""
    from pydicom.tag import Tag

    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    creator_tag = Tag(0x0009, 0x0010)
    data_tag = Tag(0x0009, 0x1001)
    assert creator_tag not in result, f"{expectation.name}: private creator (0009,0010) should be removed"
    assert data_tag not in result, f"{expectation.name}: private data element (0009,1001) should be removed"


def test_file_meta_group_preserved(expectation, canonical_dataset, profile_harness) -> None:
    """The File Meta Information group (0002) is preserved through apply()."""
    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    assert result.file_meta is not None, f"{expectation.name}: file_meta should be preserved"
    assert "TransferSyntaxUID" in result.file_meta, (
        f"{expectation.name}: file_meta TransferSyntaxUID should be preserved"
    )


def test_retired_group_length_tag_removed(expectation, canonical_dataset, profile_harness) -> None:
    """The retired group-length tag (0008,0000) is removed by every profile."""
    from pydicom.tag import Tag

    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    tag = Tag(0x0008, 0x0000)
    assert tag not in result, f"{expectation.name}: retired group-length tag (0008,0000) should be removed"


def test_specific_character_set_present(expectation, canonical_dataset, profile_harness) -> None:
    """SpecificCharacterSet (0008,0005) is present after de-identification."""
    from pydicom.tag import Tag

    result = profile_harness.apply_profile(expectation.name, dataset=canonical_dataset)
    tag = Tag(0x0008, 0x0005)
    assert tag in result, f"{expectation.name}: SpecificCharacterSet (0008,0005) should be present"
