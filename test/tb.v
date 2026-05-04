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

  // Dump waves
  initial begin
    $dumpfile("tb.fst");
    $dumpvars(0, tb);
  end

  // Instantiate the design
  tt_um_chidam_secengine uut (
    .ui_in(ui_in),
    .uo_out(uo_out),
    .uio_in(uio_in),
    .uio_out(uio_out),
    .uio_oe(uio_oe),
    .ena(ena),
    .clk(clk),
    .rst_n(rst_n)
  );

  // Clock generation
  always #10 clk = ~clk;

  // Initial values
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
    // The test will be driven by cocotb, so we just wait forever
    #1000000;
    $finish;
  end

endmodule
