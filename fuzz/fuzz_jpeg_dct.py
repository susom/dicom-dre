#!/usr/bin/env python3
"""Fuzz target for the JPEG DCT-domain scrubber.

Feeds arbitrary bytes and blanking regions to scrub_jpeg_bytes to find crashes,
infinite loops, and unbounded allocations in the hand-written JPEG Baseline
bitstream parser. Exceptions used to reject malformed input are treated as
expected; anything else (hang, OOM, unexpected exception type) is a finding.
"""

import struct
import sys

import atheris


with atheris.instrument_imports():
    from dicom_dre.jpeg_dct_scrubber import scrub_jpeg_bytes
    from dicom_dre.scrub_region import ScrubRegion

# Exceptions the parser raises to reject malformed or unsupported input.
_EXPECTED = (ValueError, EOFError, IndexError, OverflowError, struct.error)


def TestOneInput(data: bytes) -> None:
    """Scrub a fuzzed JPEG bitstream with a fuzzed blanking region."""
    fdp = atheris.FuzzedDataProvider(data)
    x = fdp.ConsumeIntInRange(0, 65535)
    y = fdp.ConsumeIntInRange(0, 65535)
    width = fdp.ConsumeIntInRange(0, 65535)
    height = fdp.ConsumeIntInRange(0, 65535)
    jpeg = fdp.ConsumeBytes(fdp.remaining_bytes())

    regions = [ScrubRegion(x=x, y=y, width=width, height=height)]
    try:
        scrub_jpeg_bytes(jpeg, regions)
    except _EXPECTED:
        return


def main() -> None:
    """Configure Atheris and start the fuzzing loop."""
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
