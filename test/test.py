# SPDX-FileCopyrightText: 2025 Chidam
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer


async def reset_dut(dut):
    dut.rst_n.value  = 0
    dut.ena.value    = 1
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value  = 1
    await ClockCycles(dut.clk, 2)


async def tick(dut, n=1):
    """Clock n cycles then wait 1ns so registered outputs settle."""
    await ClockCycles(dut.clk, n)
    await Timer(1, units="ns")


# -----------------------------------------------------------------------
# Reference models
# -----------------------------------------------------------------------
def crc8_maxim_step(crc, byte_val):
    """CRC-8/MAXIM: poly=0x31 (reflected 0x8C), init=0x00"""
    c = crc ^ (byte_val & 0xFF)
    for _ in range(8):
        c = (c >> 1) ^ 0x8C if (c & 1) else c >> 1
    return c & 0xFF


def ref_hamming(data6):
    d = [(data6 >> i) & 1 for i in range(6)]
    p1 = d[0] ^ d[1] ^ d[3]
    p2 = d[0] ^ d[2] ^ d[3]
    p3 = d[1] ^ d[2] ^ d[3]
    ep = d[0] ^ d[1] ^ d[2] ^ d[3] ^ d[4] ^ d[5]
    return (ep<<7)|(p3<<6)|(p2<<5)|(p1<<4)|(d[5]<<3)|(d[4]<<2)|(d[3]<<1)|d[2]


def ref_bitrev_popcnt(data6):
    data6 &= 0x3F
    rev = int(f"{data6:06b}"[::-1], 2)   # 6-bit bit reversal
    popcnt = bin(data6).count('1')
    bitrev_out = rev & 0x3F              # {2'b00, rev[5:0]}
    uo_high = (bitrev_out >> 2) & 0xF   # bits [7:4] of uo_out
    return (uo_high << 4) | (popcnt & 0xF)


# -----------------------------------------------------------------------
# MODE 00 — CRC-8/MAXIM
# -----------------------------------------------------------------------
@cocotb.test()
async def test_mode00_crc8(dut):
    """MODE 00: CRC-8/MAXIM accumulator"""
    Clock(dut.clk, 100, units="ns"); cocotb.start_soon(Clock(dut.clk, 100, units="ns").start())
    await reset_dut(dut)
    dut._log.info("MODE 00: CRC-8/MAXIM")

    crc_ref = 0x00
    for byte_val in [0x01, 0x3F, 0x2A, 0x00, 0x0F, 0x15]:
        data6 = byte_val & 0x3F
        dut.ui_in.value = (0b00 << 6) | data6
        await tick(dut, 1)              # crc_reg updates
        crc_ref = crc8_maxim_step(crc_ref, data6)
        await tick(dut, 1)              # result_reg = crc_reg → uo_out
        got = int(dut.uo_out.value)
        dut._log.info(f"  data=0x{data6:02X}  exp=0x{crc_ref:02X}  got=0x{got:02X}")
        assert got == crc_ref, f"CRC mismatch data=0x{data6:02X}: exp=0x{crc_ref:02X} got=0x{got:02X}"

    dut._log.info("MODE 00 PASSED")


# -----------------------------------------------------------------------
# MODE 01 — Galois LFSR PRNG
# -----------------------------------------------------------------------
@cocotb.test()
async def test_mode01_lfsr(dut):
    """MODE 01: Galois LFSR PRNG — maximal sequence, no lock-up"""
    cocotb.start_soon(Clock(dut.clk, 100, units="ns").start())
    dut.ui_in.value  = (0b01 << 6) | 0b010101
    dut.ena.value    = 1
    dut.uio_in.value = 0
    dut.rst_n.value  = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value  = 1
    await ClockCycles(dut.clk, 2)
    dut._log.info("MODE 01: Galois LFSR PRNG")

    outputs = []
    for i in range(30):
        dut.ui_in.value = (0b01 << 6) | 0b010101
        await tick(dut, 1)
        val = int(dut.uo_out.value)
        outputs.append(val)
        dut._log.info(f"  step {i:2d}: uo_out=0x{val:02X}")

    assert 0x00 not in outputs, "LFSR hit lock-up 0x00!"
    assert len(set(outputs)) > 5,  f"LFSR stuck: unique={set(outputs)}"
    dut._log.info("MODE 01 PASSED")


# -----------------------------------------------------------------------
# MODE 10 — Hamming(8,4) + even parity
# -----------------------------------------------------------------------
@cocotb.test()
async def test_mode10_hamming(dut):
    """MODE 10: Hamming(8,4) syndrome + even parity"""
    cocotb.start_soon(Clock(dut.clk, 100, units="ns").start())
    await reset_dut(dut)
    dut._log.info("MODE 10: Hamming parity")

    for data6 in [0x00, 0x3F, 0x15, 0x2A, 0x01, 0x3E, 0x0F, 0x30]:
        dut.ui_in.value = (0b10 << 6) | (data6 & 0x3F)
        await tick(dut, 2)
        got      = int(dut.uo_out.value)
        expected = ref_hamming(data6 & 0x3F)
        dut._log.info(f"  data=0x{data6:02X}  exp=0x{expected:02X}  got=0x{got:02X}")
        assert got == expected, f"Hamming mismatch 0x{data6:02X}: exp=0x{expected:02X} got=0x{got:02X}"

    dut._log.info("MODE 10 PASSED")


# -----------------------------------------------------------------------
# MODE 11 — Bit-reversal + population count
# -----------------------------------------------------------------------
@cocotb.test()
async def test_mode11_bitrev_popcount(dut):
    """MODE 11: Bit-reversal upper nibble + popcount lower nibble"""
    cocotb.start_soon(Clock(dut.clk, 100, units="ns").start())
    await reset_dut(dut)
    dut._log.info("MODE 11: Bit-reversal + popcount")

    for data6 in [0x00, 0x01, 0x3F, 0x15, 0x2A, 0x07, 0x38, 0x1C]:
        dut.ui_in.value = (0b11 << 6) | (data6 & 0x3F)
        await tick(dut, 2)
        got      = int(dut.uo_out.value)
        expected = ref_bitrev_popcnt(data6)
        dut._log.info(f"  data=0b{data6 & 0x3F:06b}  exp=0x{expected:02X}  got=0x{got:02X}")
        assert got == expected, f"BitRev/PC mismatch 0x{data6:02X}: exp=0x{expected:02X} got=0x{got:02X}"

    dut._log.info("MODE 11 PASSED")


# -----------------------------------------------------------------------
# Pipeline: uio_out = uo_out delayed by 1 clock
# -----------------------------------------------------------------------
@cocotb.test()
async def test_pipeline_uio(dut):
    """uio_out must lag uo_out by exactly one clock"""
    cocotb.start_soon(Clock(dut.clk, 100, units="ns").start())
    await reset_dut(dut)
    dut._log.info("Pipeline: uio_out = delayed uo_out")

    prev_uo = 0
    for data6 in [0x01, 0x0F, 0x3F, 0x15, 0x2A]:
        dut.ui_in.value = (0b10 << 6) | data6
        await tick(dut, 1)
        cur_uo  = int(dut.uo_out.value)
        cur_uio = int(dut.uio_out.value)
        dut._log.info(f"  uo=0x{cur_uo:02X}  uio=0x{cur_uio:02X}  prev=0x{prev_uo:02X}")
        assert cur_uio == prev_uo, f"Pipeline: uio=0x{cur_uio:02X} != prev_uo=0x{prev_uo:02X}"
        prev_uo = cur_uo

    dut._log.info("Pipeline PASSED")


# -----------------------------------------------------------------------
# Reset
# -----------------------------------------------------------------------
@cocotb.test()
async def test_reset(dut):
    """Active-low reset must clear uo_out and uio_out to 0x00"""
    cocotb.start_soon(Clock(dut.clk, 100, units="ns").start())
    dut.ui_in.value = (0b00 << 6) | 0x3F
    dut.ena.value = 1; dut.rst_n.value = 1; dut.uio_in.value = 0
    await ClockCycles(dut.clk, 15)
    dut.rst_n.value = 0
    await tick(dut, 4)
    assert int(dut.uo_out.value)  == 0, f"uo_out not 0: 0x{int(dut.uo_out.value):02X}"
    assert int(dut.uio_out.value) == 0, f"uio_out not 0: 0x{int(dut.uio_out.value):02X}"
    dut._log.info("Reset PASSED")
