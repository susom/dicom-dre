# The C entropy codec compiled by this script is a port of the PixelMed Java
# JPEG Selective Block Redaction Codec (https://www.pixelmed.com/jpeg.html) and
# is distributed under the terms of that codec's BSD license, reproduced below
# as required for redistribution of source derived from it.
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
"""Build script for the JPEG DCT accelerator C extension.

Uses cffi out-of-line API mode to compile the C code into a shared library.
The compiled module is cached and reused on subsequent imports.

The compiled entropy codec is ported from the PixelMed Java JPEG Selective
Block Redaction Codec; its BSD license is retained in the comment block above
this docstring and embedded in the generated C source.

Run directly to force a rebuild:
    python _jpeg_dct_accel_build.py
"""

import cffi


ffi = cffi.FFI()

ffi.cdef("""
    int process_entropy_segment(
        const uint8_t *entropy_data,
        int entropy_len,
        int image_width,
        int image_height,
        int num_components,
        const int *comp_h_sampling,
        const int *comp_v_sampling,
        int num_scan_components,
        const int *scan_dc_table_idx,
        const int *scan_ac_table_idx,
        const int *scan_h_blocks,
        const int *scan_v_blocks,
        int num_dc_tables,
        const int *dc_table_ids,
        const int *dc_mincode,
        const int *dc_maxcode,
        const int *dc_valptr,
        const int *dc_huffval,
        const int *dc_huffval_counts,
        const int *dc_efufco,
        const int *dc_efufsi,
        const int *dc_efuf_len,
        int num_ac_tables,
        const int *ac_table_ids,
        const int *ac_mincode,
        const int *ac_maxcode,
        const int *ac_valptr,
        const int *ac_huffval,
        const int *ac_huffval_counts,
        const int *ac_efufco,
        const int *ac_efufsi,
        const int *ac_efuf_len,
        const int *ac_eob_code,
        const int *ac_eob_code_length,
        int restart_interval,
        int num_regions,
        const int *regions,
        uint8_t *output,
        int output_capacity,
        int *output_len
    );
""")

ffi.set_source(
    "dicom_dre._jpeg_dct_accel",
    r"""
/*
 * Ported from the PixelMed Java JPEG Selective Block Redaction Codec
 * (https://www.pixelmed.com/jpeg.html).
 *
 * Copyright (c) 2001-2025, David A. Clunie DBA PixelMed Publishing.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright notice,
 *    this list of conditions and the following disclaimers.
 * 2. Redistributions in binary form must reproduce the above copyright notice,
 *    this list of conditions and the following disclaimers in the documentation
 *    and/or other materials provided with the distribution.
 * 3. Neither the name of PixelMed Publishing nor the names of its contributors
 *    may be used to endorse or promote products derived from this software.
 *
 * This software is provided by the copyright holders and contributors "as is"
 * and any express or implied warranties, including, but not limited to, the
 * implied warranties of merchantability and fitness for a particular purpose
 * are disclaimed. In no event shall the copyright owner or contributors be
 * liable for any direct, indirect, incidental, special, exemplary, or
 * consequential damages (including, but not limited to, procurement of
 * substitute goods or services; loss of use, data or profits; or business
 * interruption) however caused and on any theory of liability, whether in
 * contract, strict liability, or tort (including negligence or otherwise)
 * arising in any way out of the use of this software, even if advised of the
 * possibility of such damage.
 *
 * This software has neither been tested nor approved for clinical use or for
 * incorporation in a medical device. It is the redistributor's or user's
 * responsibility to comply with any applicable local, state, national or
 * international regulations.
 */
#include <stdint.h>
#include <string.h>

/* ---------- Huffman table (decoded from Python-side arrays) ---------- */

typedef struct {
    int mincode[17];
    int maxcode[17];
    int valptr[17];
    int huffval[256];
    int huffval_count;
    int efufco[256];
    int efufsi[256];
    int efuf_len;
    int eob_code;
    int eob_code_length;
} HuffTable;

/* ---------- Bit reader with JPEG byte-stuffing ---------- */

typedef struct {
    const uint8_t *data;
    int len;
    int pos;
    uint32_t bit_buffer;
    int bits_available;
} BitReader;

static inline void br_init(BitReader *br, const uint8_t *data, int len) {
    br->data = data;
    br->len = len;
    br->pos = 0;
    br->bit_buffer = 0;
    br->bits_available = 0;
}

static inline int br_next_byte(BitReader *br) {
    if (br->pos >= br->len) return -1;
    int b = br->data[br->pos++];
    if (b == 0xFF && br->pos < br->len) {
        uint8_t next = br->data[br->pos];
        if (next == 0x00) {
            br->pos++;  /* byte stuffing */
        }
        /* RST markers inside data are handled at MCU boundary level */
    }
    return b;
}

static inline int br_get_bits(BitReader *br, int n) {
    while (br->bits_available < n) {
        int b = br_next_byte(br);
        if (b < 0) return 0;
        br->bit_buffer = (br->bit_buffer << 8) | (uint32_t)b;
        br->bits_available += 8;
    }
    br->bits_available -= n;
    return (int)((br->bit_buffer >> br->bits_available) & ((1u << n) - 1));
}

static inline int br_get_bit(BitReader *br) {
    return br_get_bits(br, 1);
}

/* ---------- Bit writer with JPEG byte-stuffing ---------- */

typedef struct {
    uint8_t *output;
    int capacity;
    int pos;
    int bit_buffer;
    int bits_pending;
} BitWriter;

static inline void bw_init(BitWriter *bw, uint8_t *output, int capacity) {
    bw->output = output;
    bw->capacity = capacity;
    bw->pos = 0;
    bw->bit_buffer = 0;
    bw->bits_pending = 0;
}

static inline void bw_flush_byte(BitWriter *bw) {
    uint8_t b = (uint8_t)(bw->bit_buffer & 0xFF);
    if (bw->pos < bw->capacity) bw->output[bw->pos++] = b;
    if (b == 0xFF && bw->pos < bw->capacity) {
        bw->output[bw->pos++] = 0x00;  /* byte stuffing */
    }
    bw->bit_buffer = 0;
    bw->bits_pending = 0;
}

static inline void bw_write_bits(BitWriter *bw, int value, int n) {
    for (int i = n - 1; i >= 0; --i) {
        bw->bit_buffer = (bw->bit_buffer << 1) | ((value >> i) & 1);
        bw->bits_pending++;
        if (bw->bits_pending == 8) {
            bw_flush_byte(bw);
        }
    }
}

static inline void bw_flush(BitWriter *bw) {
    if (bw->bits_pending > 0) {
        bw->bit_buffer <<= (8 - bw->bits_pending);
        bw->bit_buffer |= (1 << (8 - bw->bits_pending)) - 1;  /* pad with 1s */
        bw->bits_pending = 8;
        bw_flush_byte(bw);
    }
}

/* ---------- Huffman decode/encode ---------- */

static inline int huff_decode(BitReader *br, const HuffTable *ht) {
    int code = 0;
    for (int length = 1; length <= 16; length++) {
        code = (code << 1) | br_get_bit(br);
        if (code <= ht->maxcode[length] && ht->maxcode[length] >= 0) {
            int idx = ht->valptr[length] + code - ht->mincode[length];
            /* A malformed table can yield an index outside huffval; reject it
               instead of reading out of bounds. */
            if (idx < 0 || idx >= ht->huffval_count || idx >= 256) {
                return 0;
            }
            return ht->huffval[idx];
        }
    }
    return 0;  /* invalid code, return 0 as safe fallback */
}

static inline void huff_encode(BitWriter *bw, const HuffTable *ht, int symbol) {
    if (symbol >= 0 && symbol < ht->efuf_len && symbol < 256) {
        bw_write_bits(bw, ht->efufco[symbol], ht->efufsi[symbol]);
    }
}

static inline int receive_extend(BitReader *br, int nbits) {
    if (nbits == 0) return 0;
    int value = br_get_bits(br, nbits);
    if (value < (1 << (nbits - 1))) {
        value -= (1 << nbits) - 1;
    }
    return value;
}

static inline void size_and_amplitude(int value, int *size_out, int *amp_out) {
    if (value == 0) {
        *size_out = 0;
        *amp_out = 0;
        return;
    }
    int absval = value < 0 ? -value : value;
    int size = 0;
    int tmp = absval;
    while (tmp > 0) { size++; tmp >>= 1; }
    int amplitude;
    if (value < 0) {
        amplitude = (value - 1) & ((1 << size) - 1);
    } else {
        amplitude = value & ((1 << size) - 1);
    }
    *size_out = size;
    *amp_out = amplitude;
}

/* ---------- Region overlap test ---------- */

static inline int block_overlaps_any_region(
    int bx, int by, int bw, int bh,
    int num_regions, const int *regions)
{
    int bx2 = bx + bw;
    int by2 = by + bh;
    for (int i = 0; i < num_regions; i++) {
        int rx = regions[i * 4];
        int ry = regions[i * 4 + 1];
        int rw = regions[i * 4 + 2];
        int rh = regions[i * 4 + 3];
        if (bx < rx + rw && bx2 > rx && by < ry + rh && by2 > ry) {
            return 1;
        }
    }
    return 0;
}

/* ---------- Main processing function ---------- */

int process_entropy_segment(
    const uint8_t *entropy_data,
    int entropy_len,
    int image_width,
    int image_height,
    int num_components,
    const int *comp_h_sampling,
    const int *comp_v_sampling,
    int num_scan_components,
    const int *scan_dc_table_idx,
    const int *scan_ac_table_idx,
    const int *scan_h_blocks,
    const int *scan_v_blocks,
    /* DC tables: each table has 17 entries for mincode/maxcode/valptr */
    int num_dc_tables,
    const int *dc_table_ids,
    const int *dc_mincode,      /* num_dc_tables * 17 */
    const int *dc_maxcode,      /* num_dc_tables * 17 */
    const int *dc_valptr,       /* num_dc_tables * 17 */
    const int *dc_huffval,      /* flattened, use dc_huffval_counts for offsets */
    const int *dc_huffval_counts,
    const int *dc_efufco,       /* flattened, use dc_efuf_len for sizes */
    const int *dc_efufsi,
    const int *dc_efuf_len,
    /* AC tables */
    int num_ac_tables,
    const int *ac_table_ids,
    const int *ac_mincode,
    const int *ac_maxcode,
    const int *ac_valptr,
    const int *ac_huffval,
    const int *ac_huffval_counts,
    const int *ac_efufco,
    const int *ac_efufsi,
    const int *ac_efuf_len,
    const int *ac_eob_code,
    const int *ac_eob_code_length,
    /* Other params */
    int restart_interval,
    int num_regions,
    const int *regions,
    /* Output */
    uint8_t *output,
    int output_capacity,
    int *output_len)
{
    /* Build local HuffTable structs from flat arrays */
    HuffTable dc_tables[4];
    HuffTable ac_tables[4];
    memset(dc_tables, 0, sizeof(dc_tables));
    memset(ac_tables, 0, sizeof(ac_tables));

    int dc_hv_offset = 0;
    int dc_ef_offset = 0;
    for (int t = 0; t < num_dc_tables && t < 4; t++) {
        int id = dc_table_ids[t];
        if (id < 0 || id > 3) continue;
        HuffTable *ht = &dc_tables[id];
        for (int i = 0; i < 17; i++) {
            ht->mincode[i] = dc_mincode[t * 17 + i];
            ht->maxcode[i] = dc_maxcode[t * 17 + i];
            ht->valptr[i] = dc_valptr[t * 17 + i];
        }
        int hv_count = dc_huffval_counts[t];
        for (int i = 0; i < hv_count && i < 256; i++) {
            ht->huffval[i] = dc_huffval[dc_hv_offset + i];
        }
        ht->huffval_count = hv_count;
        dc_hv_offset += hv_count;

        int ef_len = dc_efuf_len[t];
        for (int i = 0; i < ef_len && i < 256; i++) {
            ht->efufco[i] = dc_efufco[dc_ef_offset + i];
            ht->efufsi[i] = dc_efufsi[dc_ef_offset + i];
        }
        ht->efuf_len = ef_len;
        dc_ef_offset += ef_len;
    }

    int ac_hv_offset = 0;
    int ac_ef_offset = 0;
    for (int t = 0; t < num_ac_tables && t < 4; t++) {
        int id = ac_table_ids[t];
        if (id < 0 || id > 3) continue;
        HuffTable *ht = &ac_tables[id];
        for (int i = 0; i < 17; i++) {
            ht->mincode[i] = ac_mincode[t * 17 + i];
            ht->maxcode[i] = ac_maxcode[t * 17 + i];
            ht->valptr[i] = ac_valptr[t * 17 + i];
        }
        int hv_count = ac_huffval_counts[t];
        for (int i = 0; i < hv_count && i < 256; i++) {
            ht->huffval[i] = ac_huffval[ac_hv_offset + i];
        }
        ht->huffval_count = hv_count;
        ac_hv_offset += hv_count;

        int ef_len = ac_efuf_len[t];
        for (int i = 0; i < ef_len && i < 256; i++) {
            ht->efufco[i] = ac_efufco[ac_ef_offset + i];
            ht->efufsi[i] = ac_efufsi[ac_ef_offset + i];
        }
        ht->efuf_len = ef_len;
        ac_ef_offset += ef_len;

        ht->eob_code = ac_eob_code[t];
        ht->eob_code_length = ac_eob_code_length[t];
    }

    /* Determine MCU layout */
    int max_h = 0, max_v = 0;
    for (int i = 0; i < num_components; i++) {
        if (comp_h_sampling[i] > max_h) max_h = comp_h_sampling[i];
        if (comp_v_sampling[i] > max_v) max_v = comp_v_sampling[i];
    }

    /* Reject structurally invalid scans that would divide by zero or index
       fixed-size tables out of bounds. The Python caller validates these too;
       these guards keep the accelerator memory-safe if it is called directly. */
    if (max_h < 1 || max_v < 1) return 2;
    if (num_scan_components < 1 || num_scan_components > 4) return 2;
    for (int ci = 0; ci < num_scan_components; ci++) {
        if (scan_dc_table_idx[ci] < 0 || scan_dc_table_idx[ci] > 3) return 2;
        if (scan_ac_table_idx[ci] < 0 || scan_ac_table_idx[ci] > 3) return 2;
        if (scan_h_blocks[ci] < 1 || scan_v_blocks[ci] < 1) return 2;
    }

    int mcu_width = max_h * 8;
    int mcu_height = max_v * 8;
    int mcus_per_row = (image_width + mcu_width - 1) / mcu_width;
    int mcus_per_col = (image_height + mcu_height - 1) / mcu_height;
    int total_mcus = mcus_per_row * mcus_per_col;

    BitReader reader;
    br_init(&reader, entropy_data, entropy_len);

    BitWriter writer;
    bw_init(&writer, output, output_capacity);

    int orig_prev_dc[4] = {0};
    int out_prev_dc[4] = {0};
    int mcu_count = 0;

    for (int mcu_idx = 0; mcu_idx < total_mcus; mcu_idx++) {
        int mcu_row = mcu_idx / mcus_per_row;
        int mcu_col = mcu_idx % mcus_per_row;

        for (int ci = 0; ci < num_scan_components; ci++) {
            int dc_tid = scan_dc_table_idx[ci];
            int ac_tid = scan_ac_table_idx[ci];
            const HuffTable *dc_ht = &dc_tables[dc_tid];
            const HuffTable *ac_ht = &ac_tables[ac_tid];
            int h_blocks = scan_h_blocks[ci];
            int v_blocks = scan_v_blocks[ci];

            for (int bv = 0; bv < v_blocks; bv++) {
                for (int bh = 0; bh < h_blocks; bh++) {
                    int h_block_size = 8 * max_h / h_blocks;
                    int v_block_size = 8 * max_v / v_blocks;
                    int block_x = mcu_col * mcu_width + bh * h_block_size;
                    int block_y = mcu_row * mcu_height + bv * v_block_size;

                    int should_blank = block_overlaps_any_region(
                        block_x, block_y, h_block_size, v_block_size,
                        num_regions, regions);

                    /* Decode DC */
                    int dc_size = huff_decode(&reader, dc_ht);
                    int dc_diff = receive_extend(&reader, dc_size);
                    int orig_dc_value = orig_prev_dc[ci] + dc_diff;
                    orig_prev_dc[ci] = orig_dc_value;

                    int new_dc_value = should_blank ? 0 : orig_dc_value;
                    int new_dc_diff = new_dc_value - out_prev_dc[ci];
                    out_prev_dc[ci] = new_dc_value;

                    int new_size, new_amp;
                    size_and_amplitude(new_dc_diff, &new_size, &new_amp);
                    huff_encode(&writer, dc_ht, new_size);
                    if (new_size > 0) {
                        bw_write_bits(&writer, new_amp, new_size);
                    }

                    /* Decode and re-encode AC */
                    if (should_blank) {
                        int k = 1;
                        while (k < 64) {
                            int rs = huff_decode(&reader, ac_ht);
                            int rrrr = (rs >> 4) & 0x0F;
                            int ssss = rs & 0x0F;
                            if (ssss == 0) {
                                if (rrrr == 0x0F) { k += 16; continue; }  /* ZRL */
                                /* EOB (rrrr==0) or an invalid SSSS==0 run/size
                                   code; stop the block to guarantee progress. */
                                break;
                            } else {
                                receive_extend(&reader, ssss);  /* discard */
                                k += rrrr + 1;
                            }
                        }
                        /* Write EOB */
                        huff_encode(&writer, ac_ht, 0x00);
                    } else {
                        int k = 1;
                        while (k < 64) {
                            int rs = huff_decode(&reader, ac_ht);
                            int rrrr = (rs >> 4) & 0x0F;
                            int ssss = rs & 0x0F;
                            huff_encode(&writer, ac_ht, rs);
                            if (ssss == 0) {
                                if (rrrr == 0x0F) { k += 16; continue; }
                                /* EOB (rrrr==0) or an invalid SSSS==0 run/size
                                   code; stop the block to guarantee progress. */
                                break;
                            } else {
                                int val = receive_extend(&reader, ssss);
                                int dummy_size, amp;
                                size_and_amplitude(val, &dummy_size, &amp);
                                bw_write_bits(&writer, amp, ssss);
                                k += rrrr + 1;
                            }
                        }
                    }
                }
            }
        }

        mcu_count++;

        /* Handle restart markers */
        if (restart_interval > 0 &&
            mcu_count % restart_interval == 0 &&
            mcu_idx < total_mcus - 1)
        {
            bw_flush(&writer);
            int rst_num = ((mcu_count / restart_interval) - 1) % 8;
            if (writer.pos < writer.capacity) writer.output[writer.pos++] = 0xFF;
            if (writer.pos < writer.capacity) writer.output[writer.pos++] = (uint8_t)(0xD0 + rst_num);

            /* Reset DC predictions */
            for (int ci = 0; ci < num_scan_components; ci++) {
                orig_prev_dc[ci] = 0;
                out_prev_dc[ci] = 0;
            }

            /* Reset reader bit state */
            reader.bits_available = 0;

            /* Skip RST marker in input */
            while (reader.pos < reader.len) {
                if (reader.data[reader.pos] == 0xFF) {
                    if (reader.pos + 1 < reader.len &&
                        reader.data[reader.pos + 1] >= 0xD0 &&
                        reader.data[reader.pos + 1] <= 0xD7)
                    {
                        reader.pos += 2;
                        break;
                    }
                    else if (reader.pos + 1 < reader.len &&
                             reader.data[reader.pos + 1] == 0x00)
                    {
                        break;
                    }
                }
                break;
            }
        }
    }

    bw_flush(&writer);
    *output_len = writer.pos;
    return 0;
}
""",
)

if __name__ == "__main__":
    ffi.compile(verbose=True)
