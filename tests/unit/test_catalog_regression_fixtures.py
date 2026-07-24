"""Catalog decision regression tests driven by PHI-free fixtures.

Each fixture in ``catalog_fixtures/`` captures the technical DICOM tags the
device catalog uses for matching, together with the expected filtering and
scrub outcomes recorded in the regression suite. These tests replace the
bucket-backed regression for catalog decision logic: they assert that
``DeviceCatalog.evaluate`` still reaches the recorded decision for each case,
without any PHI or pixel data.
"""

import json
from pathlib import Path

import pytest

from dicom_dre.catalog import DicomTags
from dicom_dre.default_catalog import get_default_catalog


FIXTURE_DIR = Path(__file__).parent / "catalog_fixtures"


def _rect(region: str) -> tuple[int, int, int, int]:
    """Parse an 'x,y,width,height' region into (x0, y0, x1, y1) bounds."""
    x, y, width, height = (int(part) for part in region.split(","))
    return x, y, x + width, y + height


def _region_covered(expected: str, produced: list[str]) -> bool:
    """Return True when *expected* is fully covered by the union of *produced*.

    Coverage is exact rectangle-union containment: every pixel of the expected
    region must lie within at least one produced region. Over-blanking (larger
    or additional produced regions) is permitted.
    """
    ex0, ey0, ex1, ey1 = _rect(expected)
    if ex0 >= ex1 or ey0 >= ey1:
        return True
    rects = [_rect(region) for region in produced]

    x_edges = {ex0, ex1}
    for rx0, _, rx1, _ in rects:
        for edge in (rx0, rx1):
            if ex0 < edge < ex1:
                x_edges.add(edge)
    ordered_x = sorted(x_edges)

    for left, right in zip(ordered_x, ordered_x[1:]):
        intervals = sorted(
            (max(ry0, ey0), min(ry1, ey1))
            for rx0, ry0, rx1, ry1 in rects
            if rx0 <= left and rx1 >= right and min(ry1, ey1) > max(ry0, ey0)
        )
        covered_to = ey0
        for start, end in intervals:
            if start > covered_to:
                break
            covered_to = max(covered_to, end)
        if covered_to < ey1:
            return False
    return True


def _fixture_entries() -> list[tuple[Path, int, dict]]:
    """Return (path, index, entry) tuples for every entry across all files."""
    if not FIXTURE_DIR.is_dir():
        return []
    entries: list[tuple[Path, int, dict]] = []
    for path in sorted(FIXTURE_DIR.rglob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for index, entry in enumerate(data["entries"]):
            entries.append((path, index, entry))
    return entries


def _entry_id(item: tuple[Path, int, dict]) -> str:
    """Return a readable parametrization id from the file path and entry index."""
    path, index, _ = item
    return f"{path.relative_to(FIXTURE_DIR).with_suffix('').as_posix()}[{index}]"


@pytest.fixture(scope="module")
def catalog():
    """Return the default device catalog."""
    return get_default_catalog()


@pytest.mark.parametrize("item", _fixture_entries(), ids=_entry_id)
def test_catalog_decision_matches_fixture(item, catalog):
    """Catalog evaluation reproduces the recorded filtering and scrub outcome."""
    path, index, entry = item
    label = f"{path.name}[{index}]"
    tags = DicomTags(entry["tags"])

    decision = catalog.evaluate(tags)

    filtered = decision.action == "deny"
    actual_regions = sorted(region.to_string() for region in decision.scrub_regions)
    expected_regions = entry["expected_scrub_regions"]

    assert filtered == entry["expected_filtered"], (
        f"{label}: expected filtered={entry['expected_filtered']}, "
        f"got action={decision.action!r} (reason: {decision.reason})"
    )
    assert bool(decision.scrub_regions) == entry["expected_scrubbed"], (
        f"{label}: expected scrubbed={entry['expected_scrubbed']}, got regions={actual_regions}"
    )
    uncovered = [region for region in expected_regions if not _region_covered(region, actual_regions)]
    assert not uncovered, (
        f"{label}: catalog under-blanks. "
        f"expected regions not covered={uncovered}, produced={actual_regions} "
        f"(reason: {decision.reason})"
    )
