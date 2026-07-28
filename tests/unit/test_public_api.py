"""Tests for the stable top-level public API exports."""

import dicom_dre


def test_public_names_importable_from_package_root():
    """The three promoted symbols are importable from the package root."""
    from dicom_dre import DATE_TAGS
    from dicom_dre import UID_TAGS
    from dicom_dre import correct_implicit_vr_elements

    assert callable(correct_implicit_vr_elements)
    assert isinstance(DATE_TAGS, frozenset)
    assert isinstance(UID_TAGS, frozenset)


def test_tag_set_membership_unchanged():
    """DATE_TAGS and UID_TAGS retain their published sizes."""
    assert len(dicom_dre.DATE_TAGS) == 28
    assert len(dicom_dre.UID_TAGS) == 35


def test_private_alias_identity_holds():
    """The underscore alias resolves to the same public function object."""
    assert dicom_dre.correct_implicit_vr_elements is dicom_dre.profile._correct_implicit_vr_elements


def test_public_names_in_all():
    """All three names are advertised in the package __all__."""
    assert "DATE_TAGS" in dicom_dre.__all__
    assert "UID_TAGS" in dicom_dre.__all__
    assert "correct_implicit_vr_elements" in dicom_dre.__all__
