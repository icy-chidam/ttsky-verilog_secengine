import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

@cocotb.test()
async def test_project(dut):
    # Start clock (10 ns period = 100 MHz)
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.rst_n.value = 0
    dut.ena.value = 0
    await Timer(100, units="ns")
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    dut.ena.value = 1
    await RisingEdge(dut.clk)

    # Test mode 00 (CRC-8) with a simple data byte
    dut.ui_in.value = (0b00 << 6) | 0x2A   # mode 00, data = 0x2A
    await RisingEdge(dut.clk)   # first edge: internal combinational logic updates
    await RisingEdge(dut.clk)   # second edge: result_reg (uo_out) updates

    actual = dut.uo_out.value.integer
    dut._log.info(f"uo_out = {actual:08b} ({actual})")
    # Now you can assert against expected CRC value
    # expected = ... (compute with your Python CRC function)
    # assert actual == expected
