# JPEG DCT Scrubbing

The {py:mod}`dicom_dre.jpeg_dct_scrubber` module blanks rectangular regions in JPEG
Baseline images by zeroing DCT coefficients directly in the compressed
bitstream. No full decompression or recompression is performed, so non-blanked
regions are preserved bit-for-bit with no quality loss.

:::{note}
This module implements the JPEG Baseline path of the pixel-scrub stage. For how
it fits into the end-to-end de-identification flow, see
[Architecture](architecture.md).
:::

## Background

The DCT-domain redaction approach comes from the
[PixelMed DICOM Toolkit](https://www.pixelmed.com/jpeg.html), which demonstrated
that burned-in text in JPEG-compressed DICOM images can be removed by operating
on the Huffman-coded DCT coefficients without decoding and re-encoding pixel
data. This module is a Python port of the PixelMed JPEG Selective Block
Redaction Codec by David A. Clunie, with an optional C accelerator. The PixelMed
BSD license is reproduced at the top of the module source.

## Supported format

Only JPEG Baseline (SOF0) is supported:

- 8-bit sample precision
- Huffman-coded entropy coding
- Sequential DCT

Progressive JPEG, arithmetic coding, and extended JPEG processes are rejected
with a `ValueError`.

## How it works

1. The JPEG bytestream is parsed marker-by-marker (SOI, SOF0, DHT, DQT, DRI,
   SOS, EOI).
2. Huffman tables from DHT segments are used to build decode and encode lookup
   structures.
3. The entropy-coded segment after each SOS marker is decoded MCU-by-MCU. For
   each 8x8 DCT block, the module checks whether the block overlaps any of the
   specified blanking regions.
4. Blocks that overlap a blanking region have their DC coefficient set to zero
   and all 63 AC coefficients replaced with an EOB (end-of-block) marker.
   This produces a uniform mid-gray patch in the output.
5. Blocks outside blanking regions are passed through with their original
   coefficients. Two separate DC prediction chains (one for the input stream,
   one for the output stream) ensure that modifying one block does not corrupt
   the DC values of subsequent blocks.
6. Restart markers (DRI/RST) are handled by resetting both prediction chains at
   each restart interval boundary.

## C accelerator

The pure-Python entropy codec processes one bit at a time through Python method
calls (`BitReader`, `BitWriter`, `HuffmanTable`). This is correct but slow. A
single DICOM study can contain hundreds of JPEG frames that each need
DCT-domain blanking.

The C extension `_jpeg_dct_accel` reimplements `_process_entropy_segment` in C
via CFFI, yielding approximately 300x speedup over the Python fallback.

When the C extension is not available, the module emits a warning and falls back
to the Python implementation.

To compile the extension locally:

```bash
just build-ext
```

This runs `uv run python -m dicom_dre._jpeg_dct_accel_build` and writes the
compiled `_jpeg_dct_accel*.so` next to the module.

## API

### `scrub_jpeg(input_path, output_path, regions)`

Read a JPEG file from `input_path`, blank the specified regions, and write the
result to `output_path`.

| Name | Type | Description |
|------|------|-------------|
| `input_path` | `str` | Path to the input JPEG file |
| `output_path` | `str` | Path to write the scrubbed JPEG file |
| `regions` | `list[tuple[int, int, int, int]]` | Rectangles to blank as `(x, y, width, height)` in pixel coordinates |

### `scrub_jpeg_bytes(data, regions)`

Scrub JPEG data in memory and return the modified bytes.

| Name | Type | Description |
|------|------|-------------|
| `data` | `bytes` | Raw JPEG data |
| `regions` | `list[ScrubRegion]` | Rectangles to blank as `ScrubRegion(x, y, width, height)` in pixel coordinates |

**Returns:** `bytes` — the modified JPEG data.

## Command-line usage

The module can be run directly for testing:

```bash
python -m dicom_dre.jpeg_dct_scrubber input.jpg output.jpg 10,5,200,50 300,400,100,30
```

Each region argument is a comma-separated `x,y,width,height` rectangle.
