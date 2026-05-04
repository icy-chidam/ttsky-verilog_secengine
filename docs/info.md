# Multi-Function Security & Integrity Engine

## Overview

This is a compact, ASIC-worthy **security and data-integrity co-processor** targeting the TinyTapeout SKY130 shuttle. In a single 160×100 µm tile it packs **four independent hardware engines**, selectable at runtime via two mode bits — no firmware overhead, no soft implementation.

## IO Interface

| Pin | Direction | Description |
|-----|-----------|-------------|
| `ui_in[7:6]` | Input | **Mode select** (00/01/10/11) |
| `ui_in[5:0]` | Input | 6-bit data |
| `uo_out[7:0]` | Output | Result (registered, 1 clock latency) |
| `uio[7:0]` | Output | Pipelined result (1 extra cycle delayed) |
| `clk` | Input | System clock (up to 50 MHz) |
| `rst_n` | Input | Active-low synchronous reset |

## Operating Modes

### MODE 00 — CRC-8/MAXIM Accumulator
- **Polynomial:** `0x31` (reflected → `0x8C`), init `0x00`
- Compatible with Dallas/Maxim 1-Wire family CRC
- Accumulates CRC over incoming 6-bit data words each clock cycle
- `rst_n` resets accumulator; no need to stop clock

### MODE 01 — Galois LFSR PRNG
- **Taps:** bits 7, 4, 3, 0 (poly `0xB8`) — maximal-length 255-period sequence
- Seed is loaded from `ui_in[5:0]` on reset (non-zero guaranteed internally)
- Use for lightweight hardware randomness, spread-spectrum, test-pattern generation

### MODE 10 — Hamming(8,4) Syndrome + Parity
- Computes **3 Hamming parity bits** (p1, p2, p3) over the lower nibble of data
- Also computes **even parity** across all 6 input bits
- Output format: `{EP, p3, p2, p1, d5, d4, d3, d2}`
- Enables single-bit error detection/correction in downstream logic

### MODE 11 — Bit-Reversal + Population Count
- **Upper nibble `uo_out[7:4]`:** bit-reversed input (useful for bit-endian conversion)
- **Lower nibble `uo_out[3:0]`:** 6-bit population count (Hamming weight)
- Full combinational path registered at output — zero glitch propagation

## Architecture Notes

- All safety-critical outputs (CRC, LFSR, Hamming) are **registered** — no combinational glitches reach output pads
- `uio_out` provides a **free pipeline stage** (1-cycle delayed copy of `uo_out`) for back-to-back chaining
- The LFSR avoids the all-zero lock-up state via hardware seed override
- The CRC function is implemented as a synthesisable `for`-loop unrolled fully by synthesis tools — no LUT ROM required
- Design is `\`default_nettype none` — no implicit wire accidents

## How to Test

### Bench Test — CRC-8/MAXIM (MODE 00)
1. Apply reset (`rst_n=0`) for ≥2 cycles, then release
2. Set `ui_in = 8'b00_000001` (mode=00, data=0x01)
3. After 2 clock cycles, `uo_out` should read `0x8C` (first CRC byte for input 0x01)

### Bench Test — LFSR (MODE 01)
1. Reset with `ui_in[5:0] = 0b010101` to seed LFSR
2. Set mode bits `ui_in[7:6] = 2'b01`
3. Clock 20 cycles and verify `uo_out` changes each cycle and never hits `0x00`

### Bench Test — Hamming (MODE 10)
1. Set `ui_in = 8'b10_001111` (mode=10, data=0x0F)
2. Read `uo_out` — compare against reference table below

| data[5:0] | EP | p3 | p2 | p1 | d5 | d4 | d3 | d2 |
|-----------|----|----|----|----|----|----|----|----|
| `000000`  |  0 |  0 |  0 |  0 |  0 |  0 |  0 |  0 |
| `111111`  |  0 |  1 |  1 |  1 |  1 |  1 |  1 |  1 |
| `010101`  |  1 |  0 |  1 |  0 |  0 |  1 |  0 |  1 |

### Bench Test — Bit-Rev + Popcount (MODE 11)
1. Set `ui_in = 8'b11_000001` → popcount = 1, bit-rev of `000001` = `100000`
2. Expected `uo_out` = `{0010, 0001}` = `0x21`

## Use Cases

- **Edge node sensor security:** CRC mode for 1-Wire device integrity over temperature/humidity sensor chains
- **IoT random seeding:** LFSR mode provides hardware entropy for nonces in lightweight AEAD protocols
- **ECC for SRAMs:** Hamming mode generates SEC-DED parity for on-chip SRAM word protection
- **Protocol framing:** Bit-reversal mode handles LSB-first ↔ MSB-first conversion for UART/SPI bridging
