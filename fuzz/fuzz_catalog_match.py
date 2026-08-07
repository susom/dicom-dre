#!/usr/bin/env python3
"""Fuzz target for device-catalog pattern matching.

Exercises catalog.match_string, which compiles and runs user-supplied ``/regex/``
patterns against DICOM tag values. Targets catastrophic backtracking (ReDoS) and
crashes in the pattern-dispatch logic. Invalid user regexes raise re.error and
are treated as expected input rejection.
"""

import re
import sys

import atheris


with atheris.instrument_imports():
    from dicom_dre.catalog import match_string

# Instrument re.* so libFuzzer can drive coverage into compiled patterns.
atheris.enabled_hooks.add("RegEx")


def TestOneInput(data: bytes) -> None:
    """Match a fuzzed pattern against a fuzzed tag value."""
    fdp = atheris.FuzzedDataProvider(data)
    pattern = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 256))
    value = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())

    try:
        match_string(pattern, value)
    except re.error:
        return


def main() -> None:
    """Configure Atheris and start the fuzzing loop."""
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
