# This module is a port of the PixelMed Java JPEG Selective Block Redaction
# Codec (https://www.pixelmed.com/jpeg.html) and is distributed under the terms
# of that codec's BSD license, reproduced below as required for redistribution
# of source derived from it.
#
# Copyright (c) 2001-2025, David A. Clunie DBA PixelMed Publishing.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimers.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimers in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of PixelMed Publishing nor the names of its contributors
#    may be used to endorse or promote products derived from this software.
#
# This software is provided by the copyright holders and contributors "as is"
# and any express or implied warranties, including, but not limited to, the
# implied warranties of merchantability and fitness for a particular purpose are
# disclaimed. In no event shall the copyright owner or contributors be liable
# for any direct, indirect, incidental, special, exemplary, or consequential
# damages (including, but not limited to, procurement of substitute goods or
# services; loss of use, data or profits; or business interruption) however
# caused and on any theory of liability, whether in contract, strict liability,
# or tort (including negligence or otherwise) arising in any way out of the use
# of this software, even if advised of the possibility of such damage.
#
# This software has neither been tested nor approved for clinical use or for
# incorporation in a medical device. It is the redistributor's or user's
# responsibility to comply with any applicable local, state, national or
# international regulations.
"""JPEG DCT-Domain Scrubber.

Blanks rectangular regions in JPEG Baseline images by zeroing DCT coefficients
directly in the compressed bitstream — no full decompression/recompression needed.
Non-blanked regions are preserved bit-for-bit with zero quality loss.

Only JPEG Baseline (SOF0) is supported: 8-bit, Huffman-coded, sequential DCT.

Usage:
    from jpeg_dct_scrubber import scrub_jpeg
    # blank_regions is a list of (x, y, width, height) rectangles in pixel coords
    scrub_jpeg("input.jpg", "output.jpg", [(0, 0, 200, 50)])

Acknowledgements:
    Ported from the PixelMed Java JPEG Selective Block Redaction Codec by David
    A. Clunie (https://www.pixelmed.com/jpeg.html). The PixelMed BSD license is
    retained in the comment block above this docstring. The method is described
    in:

        Clunie DA, Gebow D. "Block selective redaction for minimizing loss
        during de-identification of burned in text in irreversibly compressed
        JPEG medical images." J Med Imaging (Bellingham). 2015;2(1):016501.
        doi:10.1117/1.JMI.2.1.016501. PMCID: PMC4478853.

    Note on DC handling: the PixelMed codec leaves each redacted block's DC
    difference unchanged (so blocks take the average color of the preceding
    block). This port instead zeroes the DC coefficient and carries the
    correction forward on a separate DC-prediction chain, which the paper
    mentions as an alternative but the reference codec does not implement.
"""

import io
import logging
import struct
import sys
import warnings
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from dicom_dre.scrub_region import ScrubRegion


logger = logging.getLogger(__name__)

# The pure-Python entropy codec (BitReader/BitWriter + Huffman decode/encode) is
# correct but slow: it processes one bit at a time through Python method calls.
# The C extension reimplements _process_entropy_segment in C via CFFI, yielding
# ~300x speedup. This matters because a single DICOM study can contain hundreds
# of JPEG frames that each need DCT-domain blanking. The Python fallback is kept
# for environments where the C extension is not compiled.
try:
    from dicom_dre._jpeg_dct_accel import ffi as _ffi
    from dicom_dre._jpeg_dct_accel import lib as _lib

    _HAS_C_ACCEL = True
except ImportError:
    _HAS_C_ACCEL = False
    logger.debug("C extension _jpeg_dct_accel not available; using pure-Python fallback.")
    warnings.warn(
        "\n"
        "╔══════════════════════════════════════════════════════════════════════╗\n"
        "║  WARNING: dicom-dre C extension (_jpeg_dct_accel) is NOT loaded.    ║\n"
        "║  The pure-Python entropy codec fallback is ~300x SLOWER.            ║\n"
        "║  Compile the extension with:  just build-ext                        ║\n"
        "╚══════════════════════════════════════════════════════════════════════╝",
        stacklevel=2,
    )


def jpeg_dct_accelerator_available() -> bool:
    """Report whether the JPEG DCT C accelerator is active.

    Returns the effective runtime state used by the scrubber to select the fast
    path. When ``False`` the pure-Python entropy codec fallback is used, which
    is roughly 300x slower.

    This function is import-safe and side-effect-free: it does not raise and
    does not re-emit the missing-extension warning.

    Returns:
        ``True`` if the compiled ``_jpeg_dct_accel`` extension is loaded and in
        use, ``False`` if the pure-Python fallback is active.
    """
    return _HAS_C_ACCEL


def jpeg_dct_accelerator_info() -> dict[str, object]:
    """Return diagnostic details about the JPEG DCT C accelerator.

    Returns:
        A mapping with at least the key ``"available"`` (``bool``). When the
        accelerator is loaded, ``"path"`` holds the extension module file path
        if it can be determined.
    """
    info: dict[str, object] = {"available": _HAS_C_ACCEL}
    if _HAS_C_ACCEL:
        module_file = getattr(sys.modules.get("dicom_dre._jpeg_dct_accel"), "__file__", None)
        if module_file is not None:
            info["path"] = module_file
    return info


# JPEG markers
SOI = 0xFFD8
EOI = 0xFFD9
SOF0 = 0xFFC0
DHT = 0xFFC4
DQT = 0xFFDB
DRI = 0xFFDD
SOS = 0xFFDA

# Block size for DCT
BLOCK_SIZE = 8


class HuffmanTable:
    """Huffman table for JPEG entropy decoding/encoding."""

    def __init__(self, table_class: int, table_id: int, bits: list[int], huffval: list[int]):
        """Initialize a Huffman table from JPEG DHT segment data."""
        self.table_class = table_class  # 0=DC, 1=AC
        self.table_id = table_id
        self.bits = bits  # counts of codes per bit length (index 1..16)
        self.huffval = huffval

        # Build decode tables (JPEG spec Figure C.1/C.2)
        self.mincode = [0] * 17
        self.maxcode = [-1] * 17
        self.valptr = [0] * 17
        self.huffsize = []
        self.huffcode = []

        # Generate size table
        for length in range(1, 17):
            for _ in range(self.bits[length]):
                self.huffsize.append(length)

        # Generate code table
        code = 0
        si = self.huffsize[0] if self.huffsize else 1
        k = 0
        while k < len(self.huffsize):
            while k < len(self.huffsize) and self.huffsize[k] == si:
                self.huffcode.append(code)
                code += 1
                k += 1
            code <<= 1
            si += 1

        # Build decoder tables
        j = 0
        for i in range(1, 17):
            if self.bits[i] > 0:
                self.valptr[i] = j
                self.mincode[i] = self.huffcode[j]
                j += self.bits[i]
                self.maxcode[i] = self.huffcode[j - 1]
            else:
                self.maxcode[i] = -1

        # Pre-compute EOB code for AC tables
        self.eob_code = -1
        self.eob_code_length = -1
        if table_class == 1:  # AC table
            for idx, val in enumerate(self.huffval):
                if val == 0x00:  # EOB
                    self.eob_code = self.huffcode[idx]
                    self.eob_code_length = self.huffsize[idx]
                    break

        # Build EFUFCO/EFUFSI encode lookup (value -> code/size)
        largest_val = max(self.huffval) if self.huffval else 0
        self.efufco = [0] * (largest_val + 1)
        self.efufsi = [0] * (largest_val + 1)
        for k, val in enumerate(self.huffval):
            self.efufco[val] = self.huffcode[k]
            self.efufsi[val] = self.huffsize[k]


class BitReader:
    """Reads bits from a byte buffer, handling JPEG byte stuffing (FF00 -> FF)."""

    def __init__(self, data: bytearray):
        """Initialize a bit reader over the given byte buffer."""
        self.data = data
        self.pos = 0
        self.bit_buffer = 0
        self.bits_available = 0

    def _next_byte(self) -> int:
        if self.pos >= len(self.data):
            raise EOFError("Unexpected end of entropy-coded data")
        b = self.data[self.pos]
        self.pos += 1
        if b == 0xFF:
            # Byte stuffing: 0xFF 0x00 -> 0xFF
            if self.pos < len(self.data) and self.data[self.pos] == 0x00:
                self.pos += 1
            # RST markers (0xD0-0xD7) can appear; skip marker byte
            elif self.pos < len(self.data) and 0xD0 <= self.data[self.pos] <= 0xD7:
                # This shouldn't happen inside a segment read
                pass
        return b

    def get_bits(self, n: int) -> int:
        """Read n bits from the stream and return as an integer."""
        while self.bits_available < n:
            self.bit_buffer = (self.bit_buffer << 8) | self._next_byte()
            self.bits_available += 8
        self.bits_available -= n
        return (self.bit_buffer >> self.bits_available) & ((1 << n) - 1)

    def get_bit(self) -> int:
        """Read a single bit from the stream."""
        return self.get_bits(1)


class BitWriter:
    """Writes bits to a byte buffer with JPEG byte stuffing."""

    def __init__(self):
        """Initialize an empty bit writer."""
        self.output = bytearray()
        self.bit_buffer = 0
        self.bits_pending = 0

    def write_bits(self, value: int, n: int):
        """Write n bits of value to the output stream."""
        for i in range(n - 1, -1, -1):
            self.bit_buffer = (self.bit_buffer << 1) | ((value >> i) & 1)
            self.bits_pending += 1
            if self.bits_pending == 8:
                self._flush_byte()

    def _flush_byte(self):
        b = self.bit_buffer & 0xFF
        self.output.append(b)
        if b == 0xFF:
            self.output.append(0x00)  # byte stuffing
        self.bit_buffer = 0
        self.bits_pending = 0

    def flush(self):
        """Pad remaining bits with 1s and flush."""
        if self.bits_pending > 0:
            self.bit_buffer <<= 8 - self.bits_pending
            self.bit_buffer |= (1 << (8 - self.bits_pending)) - 1  # pad with 1s
            self.bits_pending = 8
            self._flush_byte()

    def get_bytes(self) -> bytes:
        """Return the accumulated output as bytes."""
        return bytes(self.output)


class SOFInfo:
    """Start of Frame info."""

    def __init__(self, precision: int, height: int, width: int, components: list[tuple[int, int, int, int]]):
        """Initialize SOF info with image dimensions and component descriptors."""
        self.precision = precision
        self.height = height
        self.width = width
        self.components = components


class SOSInfo:
    """Start of Scan info."""

    def __init__(self, components: list[tuple[int, int, int]], ss: int, se: int, ah: int, al: int):
        """Initialize SOS info with scan component selectors and spectral parameters."""
        self.components = components
        self.ss = ss
        self.se = se
        self.ah = ah
        self.al = al


def _decode_huffman(reader: BitReader, table: HuffmanTable) -> int:
    """Decode one Huffman symbol."""
    code = 0
    for length in range(1, 17):
        code = (code << 1) | reader.get_bit()
        if code <= table.maxcode[length] and table.maxcode[length] >= 0:
            idx = table.valptr[length] + code - table.mincode[length]
            return table.huffval[idx]
    raise ValueError("Invalid Huffman code")


def _encode_huffman(writer: BitWriter, table: HuffmanTable, symbol: int):
    """Encode one Huffman symbol using EFUFCO/EFUFSI lookup."""
    if symbol < len(table.efufco):
        writer.write_bits(table.efufco[symbol], table.efufsi[symbol])
    else:
        raise ValueError(f"Symbol {symbol:#x} not in Huffman table")


def _receive_extend(reader: BitReader, nbits: int) -> int:
    """Receive and sign-extend a value (JPEG spec section F.2.2.1)."""
    if nbits == 0:
        return 0
    value = reader.get_bits(nbits)
    if value < (1 << (nbits - 1)):
        value -= (1 << nbits) - 1
    return value


def _size_and_amplitude(value: int) -> tuple[int, int]:
    """Get the category (size) and amplitude bits for a DC/AC coefficient.

    Returns the SSSS category and the amplitude bit pattern.
    """
    if value == 0:
        return 0, 0
    absval = abs(value)
    size = absval.bit_length()
    if value < 0:
        # For negative values: (value - 1) & maxAmplitude[size], where maxAmplitude[n] = (1<<n) - 1
        amplitude = (value - 1) & ((1 << size) - 1)
    else:
        amplitude = value & ((1 << size) - 1)
    return size, amplitude


def _block_overlaps_any_region(
    block_x: int, block_y: int, block_w: int, block_h: int, regions: list[tuple[int, int, int, int]]
) -> bool:
    """Check if a block overlaps any blanking region."""
    bx2 = block_x + block_w
    by2 = block_y + block_h
    for rx, ry, rw, rh in regions:
        # Rectangle overlap test
        if block_x < rx + rw and bx2 > rx and block_y < ry + rh and by2 > ry:
            return True
    return False


def _parse_dht(data: bytes) -> list[HuffmanTable]:
    """Parse DHT marker segment, which may contain multiple tables."""
    tables = []
    pos = 0
    while pos < len(data):
        tc_th = data[pos]
        tc = (tc_th >> 4) & 0x0F  # table class
        th = tc_th & 0x0F  # table id
        pos += 1
        bits = [0] + list(data[pos : pos + 16])
        pos += 16
        total = sum(bits[1:])
        huffval = list(data[pos : pos + total])
        pos += total
        tables.append(HuffmanTable(tc, th, bits, huffval))
    return tables


def _parse_dqt(data: bytes) -> dict:
    """Parse DQT marker segment. Returns {table_id: [64 values]}."""
    tables = {}
    pos = 0
    while pos < len(data):
        pq_tq = data[pos]
        precision = (pq_tq >> 4) & 0x0F  # 0=8bit, 1=16bit
        tq = pq_tq & 0x0F
        pos += 1
        if precision == 0:
            tables[tq] = list(data[pos : pos + 64])
            pos += 64
        else:
            vals = []
            for _ in range(64):
                vals.append((data[pos] << 8) | data[pos + 1])
                pos += 2
            tables[tq] = vals
    return tables


def _parse_sof(data: bytes) -> SOFInfo:
    """Parse SOF0 marker segment."""
    precision = data[0]
    height = (data[1] << 8) | data[2]
    width = (data[3] << 8) | data[4]
    ncomp = data[5]
    components = []
    pos = 6
    for _ in range(ncomp):
        comp_id = data[pos]
        hv = data[pos + 1]
        h_sampling = (hv >> 4) & 0x0F
        v_sampling = hv & 0x0F
        qt_id = data[pos + 2]
        components.append((comp_id, h_sampling, v_sampling, qt_id))
        pos += 3
    return SOFInfo(precision, height, width, components)


def _parse_sos(data: bytes) -> SOSInfo:
    """Parse SOS marker segment."""
    ns = data[0]
    components = []
    pos = 1
    for _ in range(ns):
        cs = data[pos]
        td_ta = data[pos + 1]
        td = (td_ta >> 4) & 0x0F
        ta = td_ta & 0x0F
        components.append((cs, td, ta))
        pos += 2
    ss = data[pos]
    se = data[pos + 1]
    ah_al = data[pos + 2]
    ah = (ah_al >> 4) & 0x0F
    al = ah_al & 0x0F
    return SOSInfo(components, ss, se, ah, al)


def _extract_entropy_data(stream: io.BufferedIOBase) -> bytearray:
    """Extract entropy-coded data from stream, stopping at the next marker."""
    result = bytearray()
    while True:
        b = stream.read(1)
        if not b:
            break
        byte = b[0]
        if byte == 0xFF:
            next_b = stream.read(1)
            if not next_b:
                result.append(byte)
                break
            next_byte = next_b[0]
            if next_byte == 0x00:
                # Byte stuffing
                result.append(0xFF)
                result.append(0x00)
            elif 0xD0 <= next_byte <= 0xD7:
                # RST marker — include it
                result.append(0xFF)
                result.append(next_byte)
            else:
                # Real marker — put it back
                stream.seek(-2, io.SEEK_CUR)
                break
        else:
            result.append(byte)
    return result


def _serialize_huff_tables(tables: dict):
    """Serialize a dict of HuffmanTable objects into flat arrays for the C extension."""
    sorted_ids = sorted(tables.keys())
    n = len(sorted_ids)
    table_ids = []
    all_mincode = []
    all_maxcode = []
    all_valptr = []
    all_huffval = []
    huffval_counts = []
    all_efufco = []
    all_efufsi = []
    efuf_lens = []
    eob_codes = []
    eob_code_lengths = []

    for tid in sorted_ids:
        ht = tables[tid]
        table_ids.append(tid)
        all_mincode.extend(ht.mincode)
        all_maxcode.extend(ht.maxcode)
        all_valptr.extend(ht.valptr)
        all_huffval.extend(ht.huffval)
        huffval_counts.append(len(ht.huffval))
        all_efufco.extend(ht.efufco)
        all_efufsi.extend(ht.efufsi)
        efuf_lens.append(len(ht.efufco))
        eob_codes.append(ht.eob_code)
        eob_code_lengths.append(ht.eob_code_length)

    return (
        n,
        table_ids,
        all_mincode,
        all_maxcode,
        all_valptr,
        all_huffval,
        huffval_counts,
        all_efufco,
        all_efufsi,
        efuf_lens,
        eob_codes,
        eob_code_lengths,
    )


def _process_entropy_segment_c(
    entropy_data: bytearray,
    sof: SOFInfo,
    sos: SOSInfo,
    dc_tables: dict,
    ac_tables: dict,
    restart_interval: int,
    regions: list[tuple[int, int, int, int]],
) -> bytes:
    """C-accelerated entropy segment processing."""
    scan_dc_idx = []
    scan_ac_idx = []
    scan_h = []
    scan_v = []
    for cs, dc_sel, ac_sel in sos.components:
        for comp_id, h_samp, v_samp, _qt_id in sof.components:
            if comp_id == cs:
                scan_dc_idx.append(dc_sel)
                scan_ac_idx.append(ac_sel)
                scan_h.append(h_samp)
                scan_v.append(v_samp)
                break

    comp_h = [c[1] for c in sof.components]
    comp_v = [c[2] for c in sof.components]

    (n_dc, dc_ids, dc_min, dc_max, dc_vp, dc_hv, dc_hvc, dc_eco, dc_esi, dc_efl, _, _) = _serialize_huff_tables(
        dc_tables
    )

    (n_ac, ac_ids, ac_min, ac_max, ac_vp, ac_hv, ac_hvc, ac_eco, ac_esi, ac_efl, ac_eob, ac_eobl) = (
        _serialize_huff_tables(ac_tables)
    )

    flat_regions = []
    for r in regions:
        flat_regions.extend(r)

    out_cap = len(entropy_data) * 2 + 4096

    c_entropy = _ffi.new("uint8_t[]", bytes(entropy_data))
    c_comp_h = _ffi.new("int[]", comp_h)
    c_comp_v = _ffi.new("int[]", comp_v)
    c_scan_dc = _ffi.new("int[]", scan_dc_idx)
    c_scan_ac = _ffi.new("int[]", scan_ac_idx)
    c_scan_h = _ffi.new("int[]", scan_h)
    c_scan_v = _ffi.new("int[]", scan_v)
    c_dc_ids = _ffi.new("int[]", dc_ids)
    c_dc_min = _ffi.new("int[]", dc_min)
    c_dc_max = _ffi.new("int[]", dc_max)
    c_dc_vp = _ffi.new("int[]", dc_vp)
    c_dc_hv = _ffi.new("int[]", dc_hv) if dc_hv else _ffi.new("int[]", [0])
    c_dc_hvc = _ffi.new("int[]", dc_hvc)
    c_dc_eco = _ffi.new("int[]", dc_eco) if dc_eco else _ffi.new("int[]", [0])
    c_dc_esi = _ffi.new("int[]", dc_esi) if dc_esi else _ffi.new("int[]", [0])
    c_dc_efl = _ffi.new("int[]", dc_efl)
    c_ac_ids = _ffi.new("int[]", ac_ids)
    c_ac_min = _ffi.new("int[]", ac_min)
    c_ac_max = _ffi.new("int[]", ac_max)
    c_ac_vp = _ffi.new("int[]", ac_vp)
    c_ac_hv = _ffi.new("int[]", ac_hv) if ac_hv else _ffi.new("int[]", [0])
    c_ac_hvc = _ffi.new("int[]", ac_hvc)
    c_ac_eco = _ffi.new("int[]", ac_eco) if ac_eco else _ffi.new("int[]", [0])
    c_ac_esi = _ffi.new("int[]", ac_esi) if ac_esi else _ffi.new("int[]", [0])
    c_ac_efl = _ffi.new("int[]", ac_efl)
    c_ac_eob = _ffi.new("int[]", ac_eob)
    c_ac_eobl = _ffi.new("int[]", ac_eobl)
    c_regions = _ffi.new("int[]", flat_regions) if flat_regions else _ffi.new("int[]", [0])
    c_output = _ffi.new("uint8_t[]", out_cap)
    c_output_len = _ffi.new("int[]", [0])

    rc = _lib.process_entropy_segment(
        c_entropy,
        len(entropy_data),
        sof.width,
        sof.height,
        len(sof.components),
        c_comp_h,
        c_comp_v,
        len(scan_dc_idx),
        c_scan_dc,
        c_scan_ac,
        c_scan_h,
        c_scan_v,
        n_dc,
        c_dc_ids,
        c_dc_min,
        c_dc_max,
        c_dc_vp,
        c_dc_hv,
        c_dc_hvc,
        c_dc_eco,
        c_dc_esi,
        c_dc_efl,
        n_ac,
        c_ac_ids,
        c_ac_min,
        c_ac_max,
        c_ac_vp,
        c_ac_hv,
        c_ac_hvc,
        c_ac_eco,
        c_ac_esi,
        c_ac_efl,
        c_ac_eob,
        c_ac_eobl,
        restart_interval,
        len(regions),
        c_regions,
        c_output,
        out_cap,
        c_output_len,
    )

    if rc != 0:
        raise ValueError(f"C entropy segment processing failed with code {rc}")

    return _ffi.buffer(c_output, c_output_len[0])[:]


def _process_entropy_segment(
    entropy_data: bytearray,
    sof: SOFInfo,
    sos: SOSInfo,
    dc_tables: dict,
    ac_tables: dict,
    restart_interval: int,
    regions: list[tuple[int, int, int, int]],
) -> bytes:
    """Decode and re-encode entropy-coded data, zeroing DCT coefficients in blanking regions."""
    # Dispatch to C when available (~300x faster than the Python path below).
    if _HAS_C_ACCEL:
        return _process_entropy_segment_c(entropy_data, sof, sos, dc_tables, ac_tables, restart_interval, regions)
    # Determine MCU layout
    max_h = max(c[1] for c in sof.components)
    max_v = max(c[2] for c in sof.components)
    mcu_width = max_h * BLOCK_SIZE
    mcu_height = max_v * BLOCK_SIZE
    mcus_per_row = (sof.width + mcu_width - 1) // mcu_width
    mcus_per_col = (sof.height + mcu_height - 1) // mcu_height
    total_mcus = mcus_per_row * mcus_per_col

    # Build per-scan component info
    scan_components = []
    for cs, dc_sel, ac_sel in sos.components:
        for comp_id, h_samp, v_samp, _qt_id in sof.components:
            if comp_id == cs:
                scan_components.append(
                    {
                        "id": comp_id,
                        "h": h_samp,
                        "v": v_samp,
                        "dc_table": dc_tables[dc_sel],
                        "ac_table": ac_tables[ac_sel],
                    }
                )
                break

    reader = BitReader(entropy_data)
    writer = BitWriter()
    # Track two DC prediction chains: original (for decoding) and output (for encoding)
    orig_prev_dc = [0] * len(scan_components)
    out_prev_dc = [0] * len(scan_components)
    mcu_count = 0

    for mcu_idx in range(total_mcus):
        # MCU pixel position
        mcu_row = mcu_idx // mcus_per_row
        mcu_col = mcu_idx % mcus_per_row

        for ci, comp in enumerate(scan_components):
            dc_table = comp["dc_table"]
            ac_table = comp["ac_table"]
            h_blocks = comp["h"]
            v_blocks = comp["v"]

            for bv in range(v_blocks):
                for bh in range(h_blocks):
                    # Block geometry in pixel coordinates:
                    # hBlockSize = 8 * maxH / thisH (in pixel coords)
                    # xBlock = mcuPixelOffset + h * hBlockSize
                    h_block_size = BLOCK_SIZE * max_h // h_blocks
                    v_block_size = BLOCK_SIZE * max_v // v_blocks
                    block_x = mcu_col * mcu_width + bh * h_block_size
                    block_y = mcu_row * mcu_height + bv * v_block_size

                    should_blank = _block_overlaps_any_region(block_x, block_y, h_block_size, v_block_size, regions)

                    # --- Decode DC coefficient using original prediction chain ---
                    dc_size = _decode_huffman(reader, dc_table)
                    dc_diff = _receive_extend(reader, dc_size)
                    orig_dc_value = orig_prev_dc[ci] + dc_diff
                    orig_prev_dc[ci] = orig_dc_value

                    if should_blank:
                        # Target DC is 0; compute diff from output prediction
                        new_dc_value = 0
                    else:
                        # Preserve original DC value
                        new_dc_value = orig_dc_value

                    # Compute the diff relative to the output prediction chain
                    new_dc_diff = new_dc_value - out_prev_dc[ci]
                    out_prev_dc[ci] = new_dc_value

                    # Encode DC
                    new_size, new_amp = _size_and_amplitude(new_dc_diff)
                    _encode_huffman(writer, dc_table, new_size)
                    if new_size > 0:
                        writer.write_bits(new_amp, new_size)

                    # --- Decode and re-encode AC coefficients ---
                    if should_blank:
                        # Decode all 63 AC coefficients (to advance reader), then write EOB
                        k = 1
                        while k < 64:
                            rs = _decode_huffman(reader, ac_table)
                            rrrr = (rs >> 4) & 0x0F
                            ssss = rs & 0x0F
                            if ssss == 0:
                                if rrrr == 0:
                                    break  # EOB
                                elif rrrr == 0x0F:
                                    k += 16  # ZRL
                                    continue
                            else:
                                _receive_extend(reader, ssss)  # discard
                                k += rrrr + 1
                        # Write EOB (all AC = 0)
                        _encode_huffman(writer, ac_table, 0x00)
                    else:
                        # Pass through AC coefficients unchanged
                        k = 1
                        while k < 64:
                            rs = _decode_huffman(reader, ac_table)
                            rrrr = (rs >> 4) & 0x0F
                            ssss = rs & 0x0F
                            _encode_huffman(writer, ac_table, rs)
                            if ssss == 0:
                                if rrrr == 0:
                                    break  # EOB
                                elif rrrr == 0x0F:
                                    k += 16
                                    continue
                            else:
                                val = _receive_extend(reader, ssss)
                                _, amp = _size_and_amplitude(val)
                                writer.write_bits(amp, ssss)
                                k += rrrr + 1

        mcu_count += 1

        # Handle restart markers
        if restart_interval > 0 and mcu_count % restart_interval == 0 and mcu_idx < total_mcus - 1:
            writer.flush()
            rst_marker_num = ((mcu_count // restart_interval) - 1) % 8
            writer.output.append(0xFF)
            writer.output.append(0xD0 + rst_marker_num)
            # Reset both DC prediction chains
            orig_prev_dc = [0] * len(scan_components)
            out_prev_dc = [0] * len(scan_components)
            # Skip RST marker in reader
            if reader.bits_available > 0:
                reader.bits_available = 0  # discard partial byte
            # Skip past the RST marker bytes in the input
            while reader.pos < len(reader.data):
                if reader.data[reader.pos] == 0xFF:
                    if reader.pos + 1 < len(reader.data) and 0xD0 <= reader.data[reader.pos + 1] <= 0xD7:
                        reader.pos += 2
                        break
                    elif reader.pos + 1 < len(reader.data) and reader.data[reader.pos + 1] == 0x00:
                        break
                break

    writer.flush()
    return writer.get_bytes()


def _scrub_jpeg_stream(stream: io.BytesIO, regions: list[tuple[int, int, int, int]]) -> bytes:
    """Parse a JPEG bytestream and blank specified regions in the DCT domain.

    Args:
        stream: Seekable stream positioned at the start of the JPEG data.
        regions: List of (x, y, width, height) rectangles to blank.

    Returns:
        The modified JPEG data as bytes.
    """
    out_stream = io.BytesIO()

    dc_tables: dict[int, HuffmanTable] = {}
    ac_tables: dict[int, HuffmanTable] = {}
    sof = None
    restart_interval = 0

    # Read SOI
    marker = struct.unpack(">H", stream.read(2))[0]
    if marker != SOI:
        raise ValueError("Not a JPEG file")
    out_stream.write(struct.pack(">H", SOI))

    while True:
        # Read next marker
        b = stream.read(1)
        if not b:
            break
        if b[0] != 0xFF:
            continue
        while True:
            b = stream.read(1)
            if not b or b[0] != 0xFF:
                break
        if not b:
            break
        marker = 0xFF00 | b[0]

        if marker == EOI:
            out_stream.write(struct.pack(">H", EOI))
            break

        if marker == SOS:
            # Read SOS header
            length = struct.unpack(">H", stream.read(2))[0]
            sos_data = stream.read(length - 2)
            sos = _parse_sos(sos_data)

            # Write SOS header
            out_stream.write(struct.pack(">H", marker))
            out_stream.write(struct.pack(">H", length))
            out_stream.write(sos_data)

            # Extract entropy data
            entropy_data = _extract_entropy_data(stream)

            if sof is None:
                raise ValueError("SOS marker encountered before SOF0")

            # Process it
            new_entropy = _process_entropy_segment(
                entropy_data, sof, sos, dc_tables, ac_tables, restart_interval, regions
            )

            out_stream.write(new_entropy)
            continue

        # Variable-length marker segment
        length_data = stream.read(2)
        if len(length_data) < 2:
            break
        length = struct.unpack(">H", length_data)[0]
        segment_data = stream.read(length - 2)

        if marker == SOF0:
            sof = _parse_sof(segment_data)
        elif 0xFFC1 <= marker <= 0xFFCF and marker not in (DHT, DQT, DRI):
            raise ValueError(f"Unsupported JPEG process marker {marker:#06x}; only SOF0 (baseline DCT) is supported")
        elif marker == DHT:
            for ht in _parse_dht(segment_data):
                if ht.table_class == 0:
                    dc_tables[ht.table_id] = ht
                else:
                    ac_tables[ht.table_id] = ht
        elif marker == DQT:
            _parse_dqt(segment_data)  # parsed but not used for DCT-domain blanking
        elif marker == DRI:
            restart_interval = (segment_data[0] << 8) | segment_data[1]
        # Write marker segment through
        out_stream.write(struct.pack(">H", marker))
        out_stream.write(struct.pack(">H", length))
        out_stream.write(segment_data)

    return out_stream.getvalue()


def scrub_jpeg(input_path: str, output_path: str, regions: list[tuple[int, int, int, int]]):
    """Scrub a JPEG Baseline image by blanking rectangular regions in DCT domain.

    Args:
        input_path: Path to input JPEG file.
        output_path: Path to write scrubbed JPEG file.
        regions: List of (x, y, width, height) rectangles to blank (pixel coords).
    """
    with open(input_path, "rb") as f:
        result = _scrub_jpeg_stream(io.BytesIO(f.read()), regions)

    with open(output_path, "wb") as f:
        f.write(result)


def scrub_jpeg_bytes(data: bytes, regions: list["ScrubRegion"]) -> bytes:
    """Scrub JPEG data in memory by blanking rectangular regions in DCT domain.

    Args:
        data: Raw JPEG data bytes.
        regions: List of ScrubRegion rectangles to blank.

    Returns:
        Modified JPEG data as bytes.
    """
    tuple_regions = [region.to_tuple() for region in regions]
    return _scrub_jpeg_stream(io.BytesIO(data), tuple_regions)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python jpeg_dct_scrubber.py input.jpg output.jpg [x,y,w,h ...]")
        print("Example: python jpeg_dct_scrubber.py photo.jpg anon.jpg 10,5,200,50 300,400,100,30")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    regions: list[tuple[int, int, int, int]] = []
    for arg in sys.argv[3:]:
        x, y, w, h = (int(p) for p in arg.split(","))
        regions.append((x, y, w, h))

    scrub_jpeg(input_file, output_file, regions)
    print(f"Scrubbed {input_file} -> {output_file} with {len(regions)} blanking region(s)")
