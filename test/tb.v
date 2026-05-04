`default_nettype none
`timescale 1ns / 1ps

module tb();

  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;
  reg [7:0] uio_in;
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;

`ifdef GL_TEST
  // For gate-level simulation - power and ground are required
  wire VPWR = 1'b1;
  wire VGND = 1'b0;
`endif

  initial begin
    $dumpfile("tb.fst");
    $dumpvars(0, tb);
  end

  // Instantiate the design – make sure the module name matches your top-level module
  tt_um_chidam_secengine uut (
`ifdef GL_TEST
    .VPWR(VPWR),
    .VGND(VGND),
`endif
    .ui_in  (ui_in),
    .uo_out (uo_out),
    .uio_in (uio_in),
    .uio_out(uio_out),
    .uio_oe (uio_oe),
    .ena    (ena),
    .clk    (clk),
    .rst_n  (rst_n)
  );

  // Clock generator (50 MHz)
  always #10 clk = ~clk;

  initial begin
    clk = 0;
    rst_n = 0;
    ena = 0;
    ui_in = 0;
    uio_in = 0;
    #100;
    rst_n = 1;
    #20;
    ena = 1;
    // Let cocotb test drive the inputs from now on
    #1000000;
    $finish;
  end

endmodule
