"""Tests for the ScrubRegion pixel-region model.

Validates construction from tuples and strings, the string-parse error paths,
and round-trip conversion back to tuple and string forms.
"""

from __future__ import annotations

import pytest

from dicom_dre.scrub_region import ScrubRegion


class TestFromString:
    """Parsing an 'x,y,width,height' string into a ScrubRegion."""

    def test_valid_string_parses_to_fields(self) -> None:
        """A well-formed 'x,y,width,height' string maps to the four fields."""
        region = ScrubRegion.from_string("10,20,30,40")
        assert region.x == 10, f"Expected x=10, got {region.x}"
        assert region.y == 20, f"Expected y=20, got {region.y}"
        assert region.width == 30, f"Expected width=30, got {region.width}"
        assert region.height == 40, f"Expected height=40, got {region.height}"

    def test_wrong_part_count_raises(self) -> None:
        """A string without exactly four parts is rejected."""
        with pytest.raises(ValueError, match="Expected 'x,y,width,height'"):
            ScrubRegion.from_string("10,20,30")

    def test_non_integer_part_raises(self) -> None:
        """A non-integer part raises ValueError from the int conversion."""
        with pytest.raises(ValueError, match="invalid literal for int"):
            ScrubRegion.from_string("10,20,30,abc")


class TestRoundTrip:
    """Conversion between ScrubRegion and its tuple and string forms."""

    def test_from_tuple_sets_fields(self) -> None:
        """from_tuple maps an (x, y, width, height) tuple onto the fields."""
        region = ScrubRegion.from_tuple((1, 2, 3, 4))
        assert region.to_tuple() == (1, 2, 3, 4), f"Round-trip tuple changed: {region.to_tuple()}"

    def test_to_string_matches_from_string(self) -> None:
        """to_string produces a value that from_string parses back equally."""
        region = ScrubRegion.from_string("5,6,7,8")
        assert region.to_string() == "5,6,7,8", f"Expected '5,6,7,8', got {region.to_string()!r}"
        assert ScrubRegion.from_string(region.to_string()) == region, "String round-trip should be stable"
