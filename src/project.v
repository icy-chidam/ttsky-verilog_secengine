/*
 * TinyTapeout Sky130 Submission
 * Project   : Multi-Function Security & Integrity Engine
 * Module    : tt_um_chidam_secengine
 * Author    : Chidam (chidam@vlsi)
 * License   : Apache-2.0
 *
 * Description:
 *   A compact, ASIC-worthy 8-in/8-out security co-processor with three
 *   operating modes selected by ui_in[7:6]:
 *
 *   MODE 00 — CRC-8/MAXIM (poly 0x31, refin=true, refout=true)
 *             ui_in[5:0] = 6-bit data byte (MSBs) + mode bits
 *             Actually: ui_in[5:0] is data; CRC accumulates each clk.
 *             uo_out[7:0] = running CRC-8 checksum
 *
 *   MODE 01 — Galois LFSR PRNG (poly 0xB8, 8-bit maximal)
 *             ui_in[5:0] = seed load bits (loaded when rst_n deasserted)
 *             uo_out[7:0] = LFSR pseudo-random output
 *
 *   MODE 10 — Parity + Hamming(8,4) syndrome generator
 *             ui_in[5:0] = 6 data bits (d0..d5)
 *             uo_out[7:0] = {even_parity, p3, p2, p1, d5,d4,d3,d2}
 *             (4-bit hamming parity bits over lower nibble + full parity)
 *
 *   MODE 11 — Bit-reversal + population count
 *             ui_in[5:0] = data[5:0]
 *             uo_out[7:4] = bit-reversed data[5:0] zero-padded
 *             uo_out[3:0] = popcount of ui_in[5:0]
 *
 *   uio pins: uio_oe = 8'hFF (all outputs)
 *             uio_out[7:0] = registered copy of uo_out (pipeline stage)
 *
 * IO Map:
 *   ui_in[7:6]  — MODE select
 *   ui_in[5:0]  — Data input
 *   uo_out[7:0] — Result output
 *   uio_out[7:0]— Pipelined result (1-cycle delayed)
 *   uio_oe      — 8'hFF (all bidir as output)
 *   clk         — System clock (up to 50 MHz on TT demo board)
 *   rst_n       — Active-low synchronous reset
 *   ena         — Design enable
 */

`default_nettype none

module tt_um_chidam_secengine (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path  (unused)
    output wire [7:0] uio_out,  // IOs: Output path (pipelined result)
    output wire [7:0] uio_oe,   // IOs: Enable path (all outputs)
    input  wire       ena,       // Design enable
    input  wire       clk,       // Clock
    input  wire       rst_n      // Active-low reset
);

    // ----------------------------------------------------------------
    // Pin assignments
    // ----------------------------------------------------------------
    wire [1:0] mode = ui_in[7:6];
    wire [5:0] data = ui_in[5:0];

    // bidir all outputs
    assign uio_oe = 8'hFF;

    // ----------------------------------------------------------------
    // MODE 00 : CRC-8/MAXIM  (poly=0x31, init=0x00, refin, refout)
    // Reflected poly = 0x8C
    // ----------------------------------------------------------------
    reg  [7:0] crc_reg;
    wire [7:0] crc_in = {2'b00, data};   // zero-pad 6-bit data to byte

    function [7:0] crc8_step;
        input [7:0] crc;
        input [7:0] byte_in;
        integer     i;
        reg   [7:0] c;
        begin
            c = crc ^ byte_in;
            for (i = 0; i < 8; i = i + 1) begin
                if (c[0])
                    c = (c >> 1) ^ 8'h8C;
                else
                    c = c >> 1;
            end
            crc8_step = c;
        end
    endfunction

    always @(posedge clk) begin
        if (!rst_n)
            crc_reg <= 8'h00;
        else if (ena && (mode == 2'b00))
            crc_reg <= crc8_step(crc_reg, crc_in);
    end

    // ----------------------------------------------------------------
    // MODE 01 : Galois LFSR PRNG  (8-bit, poly taps at 7,5,4,3 = 0xB8)
    // ----------------------------------------------------------------
    reg  [7:0] lfsr_reg;
    wire       lfsr_feedback = lfsr_reg[0];

    always @(posedge clk) begin
        if (!rst_n)
            lfsr_reg <= (data == 6'h00) ? 8'hAC : {2'b01, data};
        else if (ena && (mode == 2'b01))
            lfsr_reg <= {lfsr_feedback ^ lfsr_reg[7],
                         lfsr_feedback ^ lfsr_reg[6],
                         lfsr_reg[5],
                         lfsr_feedback ^ lfsr_reg[4],
                         lfsr_feedback ^ lfsr_reg[3],
                         lfsr_reg[2],
                         lfsr_reg[1],
                         lfsr_feedback ^ lfsr_reg[0]};
    end

    // ----------------------------------------------------------------
    // MODE 10 : Hamming(8,4) parity + even parity bit
    // d[5:0] = data bits; compute p1,p2,p3 over lower nibble + full even parity
    // ----------------------------------------------------------------
    wire d0 = data[0];
    wire d1 = data[1];
    wire d2 = data[2];
    wire d3 = data[3];
    wire d4 = data[4];
    wire d5 = data[5];

    // Hamming parity bits for [d3,d2,d1,d0] nibble
    wire p1 = d0 ^ d1 ^ d3;
    wire p2 = d0 ^ d2 ^ d3;
    wire p3 = d1 ^ d2 ^ d3;

    // Overall even parity across all 6 data bits
    wire ep = d0 ^ d1 ^ d2 ^ d3 ^ d4 ^ d5;

    wire [7:0] hamming_out = {ep, p3, p2, p1, d5, d4, d3, d2};

    // ----------------------------------------------------------------
    // MODE 11 : Bit-reversal + population count
    // ----------------------------------------------------------------
    wire [5:0] rev = {data[0], data[1], data[2], data[3], data[4], data[5]};

    // 6-bit popcount using adder tree
    wire [2:0] pc0 = data[0] + data[1] + data[2];
    wire [2:0] pc1 = data[3] + data[4] + data[5];
    wire [3:0] popcount = pc0 + pc1;

    wire [7:0] bitrev_out = {2'b00, rev[5:0]};
    wire [7:0] popcnt_out = {bitrev_out[7:4], popcount};

    // ----------------------------------------------------------------
    // Output MUX (combinational)
    // ----------------------------------------------------------------
    reg  [7:0] result_comb;

    always @(*) begin
        case (mode)
            2'b00:   result_comb = crc_reg;
            2'b01:   result_comb = lfsr_reg;
            2'b10:   result_comb = hamming_out;
            2'b11:   result_comb = popcnt_out;
            default: result_comb = 8'h00;
        endcase
    end

    // ----------------------------------------------------------------
    // Output register + pipeline stage
    // ----------------------------------------------------------------
    reg [7:0] result_reg;
    reg [7:0] pipe_reg;

    always @(posedge clk) begin
        if (!rst_n) begin
            result_reg <= 8'h00;
            pipe_reg   <= 8'h00;
        end else if (ena) begin
            result_reg <= result_comb;
            pipe_reg   <= result_reg;   // 1-cycle delayed on uio_out
        end
    end

    assign uo_out  = result_reg;
    assign uio_out = pipe_reg;

    // Suppress unused input warning
    wire _unused = &{uio_in, 1'b0};

endmodule
