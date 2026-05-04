# SPDX-FileCopyrightText: 2025 Chidam
# SPDX-License-Identifier: Apache-2.0

SIM          ?= icarus
TOPLEVEL_LANG ?= verilog

# Source files
VERILOG_SOURCES += $(PWD)/../src/project.v

# cocotb top-level module
TOPLEVEL = tt_um_chidam_secengine

# Python test module
MODULE = test

# Include cocotb's makefile magic
include $(shell cocotb-config --makefiles)/Makefile.sim
