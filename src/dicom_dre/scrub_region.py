"""Shared scrub region model.

A ScrubRegion represents a rectangular area of DICOM pixel data to blank during
de-identification, expressed in pixel coordinates as (x, y, width, height).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScrubRegion:
    """A rectangular pixel region to blank, in (x, y, width, height) coordinates."""

    x: int
    y: int
    width: int
    height: int

    @classmethod
    def from_tuple(cls, values: tuple[int, int, int, int]) -> ScrubRegion:
        """Create a ScrubRegion from an (x, y, width, height) tuple."""
        x, y, width, height = values
        return cls(x=x, y=y, width=width, height=height)

    @classmethod
    def from_string(cls, value: str) -> ScrubRegion:
        """Create a ScrubRegion from an 'x,y,width,height' string."""
        parts = value.split(",")
        if len(parts) != 4:
            raise ValueError(f"Expected 'x,y,width,height', got {value!r}")
        x, y, width, height = (int(part) for part in parts)
        return cls(x=x, y=y, width=width, height=height)

    def to_tuple(self) -> tuple[int, int, int, int]:
        """Return the region as an (x, y, width, height) tuple."""
        return (self.x, self.y, self.width, self.height)

    def to_string(self) -> str:
        """Return the region as an 'x,y,width,height' string."""
        return f"{self.x},{self.y},{self.width},{self.height}"
