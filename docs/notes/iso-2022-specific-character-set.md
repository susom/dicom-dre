# Non-conformant SpecificCharacterSet and ISO 2022 escape sequences

:::{note}
This is a recorded finding. The behavior is understood and benign for run
outcomes. No change to the engine has been made for it yet.
:::

## Symptom

When de-identifying certain instances with a date-preserving profile, pydicom
emits:

```
WARNING | pydicom - Found unknown escape sequence in encoded string value - using encoding latin_1
.../pydicom/charset.py:481: UserWarning: Found unknown escape sequence in encoded string value - using encoding latin_1
```

Profiles that do not preserve dates do not emit it, even though every profile
reads the same source files.

## Root cause

A source instance has an internally inconsistent character-set declaration:

- `SpecificCharacterSet` (0008,0005) = `ISO_IR 192` (UTF-8), which has no ISO 2022
  code-extension mechanism.
- A text element, `Image Comments` (0020,4000), VR `LT`, contains raw ISO 2022-JP
  (JIS X 0208) escape sequences.

The offending value bytes are:

```
\x1b$B  !z!z  \x1b(B
```

- `\x1b$B` designates JIS X 0208 (Japanese) to G0.
- `!z!z` are the two encoded characters.
- `\x1b(B` returns to ASCII.

Decoded as ISO 2022-JP this is the two-character string of full-width black stars
(U+2605 U+2605). Because the declared charset (`ISO_IR 192`) cannot handle the
`\x1b$B` escape, pydicom reports "unknown escape sequence" and falls back to
`latin_1`, which decodes the bytes one-for-one and yields the literal 10-character
string `\x1b$B!z!z\x1b(B` (escape codes preserved as control/ASCII characters)
instead of the intended two stars.

## Why only date-preserving profiles emit the warning

The warning is emitted when a text element is decoded. Whether an element is
decoded depends on which tags a profile touches:

- A profile that preserves dates (`preserve_dates=True`) calls
  `_should_skip_for_date_preservation`, which reads `ds[tag].VR` for elements as
  it decides whether to keep them. Accessing `ds[tag]` forces pydicom to lazily
  decode the raw element value, which encounters the malformed escape sequence.
- A profile that does not preserve dates never runs that check, so it never
  decodes that element and never emits the warning.

Same source files; different tag handling.

## Impact

The warning is benign for run outcome: pydicom recovers via `latin_1` and
continues, so it does not change filter/scrub/quarantine results. The practical
downside is that a profile which *preserves* the element writes the garbled
`latin_1` text (raw escape bytes) into the output instead of the intended
characters.

## Two conformant ways to keep the characters

Both were verified to decode with no warning:

- Option A (content-preserving): keep the ISO 2022-JP bytes and declare the
  matching code extension. `SpecificCharacterSet` = `["", "ISO 2022 IR 87"]`
  (empty first value defaults to ISO 2022 IR 6). No re-encoding; byte-length
  safe.
- Option B (canonicalizing): re-encode the text as real UTF-8
  (`b'\xe2\x98\x85\xe2\x98\x85'`) and leave `SpecificCharacterSet` =
  `ISO_IR 192`. Changes value bytes/length.

## Generalized fix for the DRE engine

A pre-decode normalization pass, run immediately after each `dcmread` and before
any text element is decoded. It scans undecoded `RawDataElement` bytes for
ISO 2022 escape sequences, maps each escape to its DICOM defined term using
pydicom's own tables, and, when the declared `SpecificCharacterSet` does not
already cover those terms, widens (0008,0005) to the multi-valued ISO 2022 form
and resets the dataset's original encoding so pydicom re-decodes the existing
bytes correctly. This is content-preserving (bytes unchanged), conformant, and
handles any ISO 2022 code-extension charset (not just Japanese).

Verified end-to-end: an input declaring `ISO_IR 192` with `\x1b$B!z!z\x1b(B` in
`Image Comments` normalized to `SpecificCharacterSet = ['', 'ISO 2022 IR 87']`
and decoded to the two stars with no warning.

```python
from pydicom.dataelem import RawDataElement
from pydicom import charset as _charset

# Reverse pydicom's own tables: ISO 2022 escape -> DICOM defined term.
_ENC_TO_TERM = {v: k for k, v in _charset.python_encoding.items()}
_ESC_TO_TERM = {
    esc: _ENC_TO_TERM[enc]
    for esc, enc in _charset.CODES_TO_ENCODINGS.items()
    if enc in _ENC_TO_TERM
}


def normalize_character_set(ds) -> bool:
    """Widen SpecificCharacterSet to match ISO 2022 escapes present in raw text.

    Operates on undecoded RawDataElement bytes so no element is decoded (and no
    charset warning is emitted) before the declaration is corrected. Recurses
    into sequence items. Returns True if the dataset was modified.
    """
    needed: list[str] = []

    def _scan(dataset) -> None:
        for elem in dataset._dict.values():
            raw = elem.value if isinstance(elem, RawDataElement) else None
            if isinstance(raw, (bytes, bytearray)) and _charset.ESC in raw:
                i = raw.find(_charset.ESC)
                while i != -1:
                    for esc, term in _ESC_TO_TERM.items():
                        if (
                            raw[i:i + len(esc)] == esc
                            and term != "ISO 2022 IR 6"
                            and term not in needed
                        ):
                            needed.append(term)
                    i = raw.find(_charset.ESC, i + 1)
            # Recurse into already-parsed sequence items.
            if getattr(elem, "VR", None) == "SQ" and not isinstance(elem, RawDataElement):
                for item in (elem.value or []):
                    _scan(item)

    _scan(ds)
    if not needed:
        return False

    ds.SpecificCharacterSet = [""] + needed  # empty first value = default ISO 2022 IR 6
    ds.set_original_encoding(
        ds._read_implicit,
        ds._read_little,
        _charset.convert_encodings(ds.SpecificCharacterSet),
    )
    return True
```

### Where to call it

In the DRE `deidentify_file` pipeline, call `normalize_character_set(ds)` after
each read and before catalog evaluation, element rules, and write:

- after the initial `pydicom.dcmread(...)` of the input.
- after the post-pixel-scrub re-read of the working file.

It also supersedes the profile's default `_ensure_specific_character_set`
behavior for the escape case: when escapes are present, normalization sets the
correct code-extension charset instead of defaulting to `ISO_IR 100`.

### Notes and alternatives

- The two key pydicom details that make this work: decode uses
  `original_character_set` (the read-time `_read_charset`), so rewriting only
  (0008,0005) is not enough (`set_original_encoding` must update the original
  encoding too); and inspecting `RawDataElement.value` returns raw bytes without
  triggering a decode.
- A warning filter alone would only silence the message; it would not fix the
  garbled preserved value, so it is not a substitute for normalization.
- Option B (normalize all text to UTF-8, `ISO_IR 192`) is an alternative if a
  single canonical charset is preferred downstream, at the cost of rewriting
  values.
