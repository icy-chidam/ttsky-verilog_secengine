import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ClockCycles
import random

# ---------- Helper: CRC-8/MAXIM (poly 0x31, refin=True, refout=True) ----------
def crc8_maxim(data_byte, initial=0x00):
    crc = initial
    poly = 0x8C  # reflected polynomial 0x31 -> 0x8C
    byte = data_byte
    # reflect input (refin=True)
    byte = int('{:08b}'.format(byte)[::-1], 2)
    crc ^= byte
    for _ in range(8):
        if crc & 0x01:
            crc = (crc >> 1) ^ poly
        else:
            crc >>= 1
    # no final XOR
    # reflect output (refout=True)
    crc = int('{:08b}'.format(crc)[::-1], 2)
    return crc & 0xFF

# ---------- Helper: LFSR next state (Galois, poly 0xB8) ----------
def lfsr_next(state):
    feedback = state & 0x01
    new_bit = feedback ^ ((state >> 7) & 0x01)
    return ((state >> 1) & 0x7F) | (new_bit << 7)

# ---------- Test Suite ----------
@cocotb.test()
async def test_project(dut):
    """Test all four modes of the security engine"""
    # Start clock (10ns period = 100MHz, but TT runs at 50MHz, this is fine)
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset sequence
    dut.rst_n.value = 0
    dut.ena.value = 0
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    await Timer(100, units="ns")
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    dut.ena.value = 1   # Enable design
    await ClockCycles(dut.clk, 1)

    # ------------------------------------------------------------------
    # MODE 00: CRC-8/MAXIM (running CRC over a single byte)
    # ------------------------------------------------------------------
    mode = 0b00
    test_data = 0x2A   # 6-bit value (0x2A)
    expected_crc = crc8_maxim(test_data)
    dut._log.info(f"Mode 00: data=0x{test_data:02X}, expected CRC=0x{expected_crc:02X}")

    # Apply mode and data
    dut.ui_in.value = (mode << 6) | test_data
    await RisingEdge(dut.clk)   # first clock: result_comb updates
    await RisingEdge(dut.clk)   # second clock: result_reg (uo_out) updates
    actual = dut.uo_out.value.integer
    dut._log.info(f"CRC result: 0x{actual:02X}")
    assert actual == expected_crc, f"CRC mismatch: expected 0x{expected_crc:02X}, got 0x{actual:02X}"

    # ------------------------------------------------------------------
    # MODE 01: LFSR PRNG (verify first 3 steps)
    # ------------------------------------------------------------------
    mode = 0b01
    seed = 0x1A   # any non-zero 6-bit seed
    expected_states = []
    state = seed if seed != 0 else 0xAC
    for _ in range(3):
        state = lfsr_next(state)
        expected_states.append(state)

    dut.ui_in.value = (mode << 6) | seed
    await RisingEdge(dut.clk)   # load seed on the first clock (see reset logic: lfsr_reg <= {2'b01, data})
    await RisingEdge(dut.clk)   # first LFSR step
    for exp in expected_states:
        actual = dut.uo_out.value.integer
        dut._log.info(f"LFSR step: expected 0x{exp:02X}, got 0x{actual:02X}")
        assert actual == exp, f"LFSR mismatch: expected 0x{exp:02X}, got 0x{actual:02X}"
        await RisingEdge(dut.clk)

    # ------------------------------------------------------------------
    # MODE 10: Hamming(8,4) + even parity
    # ------------------------------------------------------------------
    mode = 0b10
    data_6b = 0b101011   # d5=1, d4=0, d3=1, d2=0, d1=1, d0=1
    # Compute manually:
    d0 = data_6b[0]; d1 = data_6b[1]; d2 = data_6b[2]; d3 = data_6b[3]; d4 = data_6b[4]; d5 = data_6b[5]
    p1 = d0 ^ d1 ^ d3
    p2 = d0 ^ d2 ^ d3
    p3 = d1 ^ d2 ^ d3
    ep = d0 ^ d1 ^ d2 ^ d3 ^ d4 ^ d5
    expected_hamming = (ep << 7) | (p3 << 6) | (p2 << 5) | (p1 << 4) | (d5 << 3) | (d4 << 2) | (d3 << 1) | d2
    dut._log.info(f"Mode 10: data=0x{data_6b:02X}, expected Hamming=0x{expected_hamming:02X}")

    dut.ui_in.value = (mode << 6) | data_6b
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)   # wait for register
    actual = dut.uo_out.value.integer
    assert actual == expected_hamming, f"Hamming mismatch: expected 0x{expected_hamming:02X}, got 0x{actual:02X}"

    # ------------------------------------------------------------------
    # MODE 11: Bit-reversal + population count
    # ------------------------------------------------------------------
    mode = 0b11
    data_6b = 0b110101   # bits: d5=1,d4=1,d3=0,d2=1,d1=0,d0=1
    rev = int(f"{data_6b:06b}"[::-1], 2)  # reverse 6 bits
    popcount = bin(data_6b).count('1')
    # Output format: {2'b00, rev[5:4], popcount[3:0]}
    expected = ((rev >> 4) & 0x03) << 4 | (popcount & 0x0F)
    dut._log.info(f"Mode 11: data=0x{data_6b:02X}, rev=0x{rev:02X}, pop={popcount}, expected=0x{expected:02X}")

    dut.ui_in.value = (mode << 6) | data_6b
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    actual = dut.uo_out.value.integer
    assert actual == expected, f"Bitrev/popcount mismatch: expected 0x{expected:02X}, got 0x{actual:02X}"

    # ------------------------------------------------------------------
    # Optional: test pipelined output on uio_out (1 cycle delayed)
    # ------------------------------------------------------------------
    dut._log.info("Checking pipeline register (uio_out) – should be one clock behind uo_out")
    test_val = 0x55
    dut.ui_in.value = (0b00 << 6) | test_val   # mode 00
    await RisingEdge(dut.clk)
    uo_before = dut.uo_out.value.integer
    uio_before = dut.uio_out.value.integer
    await RisingEdge(dut.clk)
    uo_after = dut.uo_out.value.integer
    uio_after = dut.uio_out.value.integer
    dut._log.info(f"Before: uo_out=0x{uo_before:02X}, uio_out=0x{uio_before:02X}")
    dut._log.info(f"After:  uo_out=0x{uo_after:02X}, uio_out=0x{uio_after:02X}")
    # uio_out should be the previous uo_out
    assert uio_after == uo_before, "Pipeline stage mismatch"
