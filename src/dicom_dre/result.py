"""De-identification result type.

``DeidentifyResult`` is the return contract for
:func:`dicom_dre.pipeline.deidentify_file`. It reports the terminal outcome, the
output file, and the pixel regions scrubbed.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path

    from dicom_dre.scrub_region import ScrubRegion


class Outcome(Enum):
    """Terminal outcome kind for a de-identification run."""

    DEIDENTIFIED = "deidentified"
    FILTERED = "filtered"
    QUARANTINED = "quarantined"


@dataclass(frozen=True, slots=True)
class DeidentifyResult:
    """Result of de-identifying a single DICOM file.

    Attributes:
        outcome: The terminal outcome kind.
        output_file: Path to the de-identified file; None unless DEIDENTIFIED.
        was_decompressed: Whether pixel data was decompressed during processing.
        scrub_regions: The pixel regions blanked during processing.
        filter_reason: Why the file was rejected; set only when FILTERED.
        error: The processing error; set only when QUARANTINED.
    """

    outcome: Outcome
    output_file: Path | None = None
    was_decompressed: bool = False
    scrub_regions: frozenset[ScrubRegion] = field(default_factory=frozenset)
    filter_reason: str | None = None
    error: str | None = None

    @classmethod
    def deidentified(
        cls,
        output_file: Path,
        *,
        was_decompressed: bool,
        scrub_regions: frozenset[ScrubRegion],
    ) -> DeidentifyResult:
        """Build a successful (DEIDENTIFIED) result."""
        return cls(
            outcome=Outcome.DEIDENTIFIED,
            output_file=output_file,
            was_decompressed=was_decompressed,
            scrub_regions=scrub_regions,
        )

    @classmethod
    def filtered(cls, reason: str | None) -> DeidentifyResult:
        """Build a rejected (FILTERED) result."""
        return cls(outcome=Outcome.FILTERED, filter_reason=reason)

    @classmethod
    def quarantined(cls, error: str | None) -> DeidentifyResult:
        """Build a failed (QUARANTINED) result."""
        return cls(outcome=Outcome.QUARANTINED, error=error)

    @property
    def was_deidentified(self) -> bool:
        """Whether the file was successfully deidentified."""
        return self.outcome is Outcome.DEIDENTIFIED

    @property
    def was_filtered(self) -> bool:
        """Whether the file was rejected by the device catalog."""
        return self.outcome is Outcome.FILTERED

    @property
    def was_quarantined(self) -> bool:
        """Whether the file was quarantined due to a processing error."""
        return self.outcome is Outcome.QUARANTINED

    @property
    def was_scrubbed(self) -> bool:
        """Whether pixel data was scrubbed during processing."""
        return bool(self.scrub_regions)


@dataclass(frozen=True, slots=True)
class BatchItemResult:
    """Result of de-identifying one input within a batch run.

    Attributes:
        input_file: Path to the source DICOM file processed.
        result: The de-identification result for that input.
    """

    input_file: Path
    result: DeidentifyResult
