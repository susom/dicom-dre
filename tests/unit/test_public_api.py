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


def test_accelerator_functions_in_all():
    """The accelerator status helpers are advertised in __all__."""
    assert "jpeg_dct_accelerator_available" in dicom_dre.__all__, "jpeg_dct_accelerator_available should be in __all__"
    assert "jpeg_dct_accelerator_info" in dicom_dre.__all__, "jpeg_dct_accelerator_info should be in __all__"


def test_accelerator_available_importable_from_root():
    """jpeg_dct_accelerator_available is importable from the package root."""
    from dicom_dre import jpeg_dct_accelerator_available

    assert isinstance(jpeg_dct_accelerator_available(), bool), (
        f"Expected bool, got {type(jpeg_dct_accelerator_available())}"
    )


def test_accelerator_available_reflects_runtime_flag():
    """The function returns the effective runtime accelerator flag."""
    from dicom_dre import jpeg_dct_accelerator_available
    from dicom_dre import jpeg_dct_scrubber

    assert jpeg_dct_accelerator_available() is jpeg_dct_scrubber._HAS_C_ACCEL, (
        "Function should return the same value the scrubber uses (_HAS_C_ACCEL)"
    )


def test_accelerator_available_true(monkeypatch):
    """When the extension flag is set, the function reports True."""
    from dicom_dre import jpeg_dct_accelerator_available
    from dicom_dre import jpeg_dct_scrubber

    monkeypatch.setattr(jpeg_dct_scrubber, "_HAS_C_ACCEL", True)
    assert jpeg_dct_accelerator_available() is True, "Expected True when _HAS_C_ACCEL is True"


def test_accelerator_available_false(monkeypatch):
    """When the extension flag is unset, the function reports False."""
    from dicom_dre import jpeg_dct_accelerator_available
    from dicom_dre import jpeg_dct_scrubber

    monkeypatch.setattr(jpeg_dct_scrubber, "_HAS_C_ACCEL", False)
    assert jpeg_dct_accelerator_available() is False, "Expected False when _HAS_C_ACCEL is False"


def test_accelerator_info_available_key():
    """jpeg_dct_accelerator_info reports a boolean availability key."""
    from dicom_dre import jpeg_dct_accelerator_info

    info = jpeg_dct_accelerator_info()
    assert isinstance(info["available"], bool), f"Expected bool for 'available', got {type(info['available'])}"


def test_accelerator_info_absent_has_no_path(monkeypatch):
    """When the accelerator is absent, no extension path is reported."""
    from dicom_dre import jpeg_dct_accelerator_info
    from dicom_dre import jpeg_dct_scrubber

    monkeypatch.setattr(jpeg_dct_scrubber, "_HAS_C_ACCEL", False)
    info = jpeg_dct_accelerator_info()
    assert info["available"] is False, "Expected available False when _HAS_C_ACCEL is False"
    assert "path" not in info, f"Expected no 'path' key when absent, got {info}"
