#!/usr/bin/env python3
"""Fuzz target for the free-text PHI redactor.

Exercises TextRedactor.redact_text with arbitrary Unicode input to find crashes,
hangs, and catastrophic backtracking (ReDoS) in the deny/allow regex patterns.
Also enforces a redaction invariant: an isolated PHI canary token must never
survive redaction.
"""

import sys

import atheris


with atheris.instrument_imports():
    from dicom_dre.text_redactor import TextRedactor

# Instrument re.* so libFuzzer can drive coverage through the redaction patterns.
atheris.enabled_hooks.add("RegEx")

# Redactor with default patterns and an empty allowlist (nothing is exempt).
_REDACTOR = TextRedactor()

# A Social Security Number token that the default deny patterns must always mask.
_SSN_CANARY = "123-45-6789"


def TestOneInput(data: bytes) -> None:
    """Redact fuzzed text and assert the PHI canary is masked."""
    fdp = atheris.FuzzedDataProvider(data)
    text = fdp.ConsumeUnicodeNoSurrogates(fdp.remaining_bytes())

    # Robustness: none of the redaction modes may raise on arbitrary text.
    _REDACTOR.redact_text(text)
    _REDACTOR.redact_text(text, track_redacted=True)
    _REDACTOR.redact_text(text, return_token_pairs=True)

    # Invariant: a delimiter-isolated SSN canary must be redacted regardless of
    # the surrounding fuzzed text.
    probe = f"note {_SSN_CANARY} end {text}"
    redacted = _REDACTOR.redact_text(probe)
    if isinstance(redacted, str) and _SSN_CANARY in redacted:
        raise RuntimeError(f"PHI canary survived redaction: {_SSN_CANARY!r}")


def main() -> None:
    """Configure Atheris and start the fuzzing loop."""
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
