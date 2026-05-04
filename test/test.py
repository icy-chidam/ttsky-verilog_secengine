import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ClockCycles
import random

# ------------------------------------------------------------------
# CRC-8 function that matches your Verilog implementation exactly
# (No input reflection, no output reflection, poly 0x8C)
# ------------------------------------------------------------------
def crc8_verilog(byte_in, initial=0x00):
    c = initial ^ byte_in
    for _ in range(8):
        if c & 0x01:
            c = (c >> 1) ^ 0x8C
        else:
            c >>= 1
    return c & 0xFF

# LFSR next state (matches your Verilog)
def lfsr_next(state):
    feedback = state & 0x01
    new_bit = feedback ^ ((state >> 7) & 0x01)
    return ((state >> 1) & 0x7F) | (new_bit << 7)

# ------------------------------------------------------------------
@cocotb.test()
async def test_project(dut):
    """Test all four modes of tt_um_chidam_secengine"""

    # --------------------------------------------------------------
    # 1. Reset and clock start
    # --------------------------------------------------------------
    dut.rst_n.value = 0
    dut.ena.value = 0
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    await Timer(100, units="ns")

    # Start clock AFTER reset is low, to avoid undefined initial edge
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Deassert reset, wait 2 cycles
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    dut.ena.value = 1          # Enable the design
    await ClockCycles(dut.clk, 1)  # Let the enable settle

    # --------------------------------------------------------------
    # MODE 00 : CRC-8 (single byte)
    # --------------------------------------------------------------
    mode = 0b00
    test_data = 0x2A
    expected = crc8_verilog(test_data)
    dut._log.info(f"Mode 00: data=0x{test_data:02X}, expected CRC=0x{expected:02X}")

    dut.ui_in.value = (mode << 6) | test_data
    await RisingEdge(dut.clk)   # 1st edge: crc_reg updates
    await RisingEdge(dut.clk)   # 2nd edge: result_reg (uo_out) updates
    actual = dut.uo_out.value.integer
    dut._log.info(f"Got uo_out = 0x{actual:02X}")
    assert actual == expected, f"CRC mismatch: expected 0x{expected:02X}, got 0x{actual:02X}"

    # --------------------------------------------------------------
    # MODE 01 : LFSR (verify first 3 steps)
    # --------------------------------------------------------------
    mode = 0b01
    seed = 0x1A   # non‑zero 6‑bit seed
    # Compute expected states (loading seed, then 3 steps)
    state = seed if seed != 0 else 0xAC
    expected_states = [lfsr_next(state) for _ in range(3)]

    dut.ui_in.value = (mode << 6) | seed
    await RisingEdge(dut.clk)   # load seed (lfsr_reg <= {2'b01, data})
    await RisingEdge(dut.clk)   # first LFSR step appears on uo_out

    for i, exp in enumerate(expected_states):
        actual = dut.uo_out.value.integer
        dut._log.info(f"LFSR step {i+1}: expected 0x{exp:02X}, got 0x{actual:02X}")
        assert actual == exp, f"LFSR step {i+1} mismatch"
        await RisingEdge(dut.clk)

    # --------------------------------------------------------------
    # MODE 10 : Hamming(8,4) + even parity
    # --------------------------------------------------------------
    mode = 0b10
    data_6b = 0b101011   # d5..d0 = 1,0,1,0,1,1
    # Extract bits
    d0 = (data_6b >> 0) & 1
    d1 = (data_6b >> 1) & 1
    d2 = (data_6b >> 2) & 1
    d3 = (data_6b >> 3) & 1
    d4 = (data_6b >> 4) & 1
    d5 = (data_6b >> 5) & 1
    # Hamming parity bits for lower nibble (d3,d2,d1,d0)
    p1 = d0 ^ d1 ^ d3
    p2 = d0 ^ d2 ^ d3
    p3 = d1 ^ d2 ^ d3
    # Overall even parity
    ep = d0 ^ d1 ^ d2 ^ d3 ^ d4 ^ d5
    expected = (ep << 7) | (p3 << 6) | (p2 << 5) | (p1 << 4) | (d5 << 3) | (d4 << 2) | (d3 << 1) | d2

    dut.ui_in.value = (mode << 6) | data_6b
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    actual = dut.uo_out.value.integer
    dut._log.info(f"Mode 10: expected 0x{expected:02X}, got 0x{actual:02X}")
    assert actual == expected, f"Hamming mismatch"

    # --------------------------------------------------------------
    # MODE 11 : Bit‑reversal + population count
    # --------------------------------------------------------------
    mode = 0b11
    data_6b = 0b110101   # d5..d0 = 1,1,0,1,0,1
    # Bit‑reverse the 6 bits
    rev = int(f"{data_6b:06b}"[::-1], 2)
    # Population count
    pop = bin(data_6b).count('1')
    # Output format: {2'b00, rev[5:4], pop[3:0]}
    expected = ((rev >> 4) & 0x03) << 4 | (pop & 0x0F)

    dut.ui_in.value = (mode << 6) | data_6b
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    actual = dut.uo_out.value.integer
    dut._log.info(f"Mode 11: expected 0x{expected:02X}, got 0x{actual:02X}")
    assert actual == expected, f"Bit‑rev/popcount mismatch"

    # --------------------------------------------------------------
    # Extra: check pipeline register uio_out (1‑cycle delay)
    # --------------------------------------------------------------
    dut._log.info("Checking pipeline stage (uio_out = previous uo_out)")
    test_val = 0x55
    dut.ui_in.value = (0b00 << 6) | test_val   # use mode 00
    await RisingEdge(dut.clk)
    old_uo = dut.uo_out.value.integer
    await RisingEdge(dut.clk)
    new_uo = dut.uo_out.value.integer
    uio = dut.uio_out.value.integer
    dut._log.info(f"old uo_out = 0x{old_uo:02X}, new uo_out = 0x{new_uo:02X}, uio_out = 0x{uio:02X}")
    assert uio == old_uo, f"Pipeline mismatch: expected uio_out = 0x{old_uo:02X}, got 0x{uio:02X}"

    dut._log.info("All tests passed!")
