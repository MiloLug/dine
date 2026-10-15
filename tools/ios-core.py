#!/usr/bin/env python3
"""Write a synthetic arm64 Mach-O core for an iOS app binary, for lldb with no device.

The core maps the app's segments at their file vmaddrs (slide 0) plus a zeroed stack, and holds
one thread stopped at <pc>. lldb then has a real frame there, so the Swift expression context
(SDK, module imports) can be checked offline. Nothing in the "process" can run.

Usage: ios-core.py <Mach-O> <out.core> <pc>
"""
import struct
import sys

LC_SEGMENT_64, LC_THREAD, MH_CORE = 0x19, 0x4, 4
ARM_THREAD_STATE64, ARM_THREAD_STATE64_COUNT = 6, 68

exe, out, pc = sys.argv[1], sys.argv[2], int(sys.argv[3], 0)
data = open(exe, "rb").read()
magic, cputype, cpusubtype, _, ncmds = struct.unpack_from("<IiiII", data, 0)
if magic != 0xFEEDFACF:
    sys.exit(f"{exe}: not a thin 64-bit Mach-O")

segs, off = [], 32
for _ in range(ncmds):
    cmd, size = struct.unpack_from("<II", data, off)
    if cmd == LC_SEGMENT_64:
        name, vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<16sQQQQ", data, off + 8)
        if vmsize and name.rstrip(b"\0") != b"__PAGEZERO":
            segs.append((vmaddr, data[fileoff:fileoff + filesize].ljust(vmsize, b"\0")))
    off += size
stack_top = 0x16F100000
segs.append((stack_top - 0x100000, bytes(0x100000)))

# x0-x28, fp, lr, sp, pc; fp = lr = 0 ends the backtrace at frame 0.
regs = [0] * 31 + [stack_top - 0x8000, pc]
state = struct.pack("<II", ARM_THREAD_STATE64, ARM_THREAD_STATE64_COUNT)
state += struct.pack("<33QII", *regs, 0, 0)
thread_cmd = struct.pack("<II", LC_THREAD, 8 + len(state)) + state

seg_cmd_size = 72
fileoff = (32 + seg_cmd_size * len(segs) + len(thread_cmd) + 0x3FFF) & ~0x3FFF
seg_cmds, placed = b"", []
for vmaddr, blob in segs:
    seg_cmds += struct.pack("<II16sQQQQiiII", LC_SEGMENT_64, seg_cmd_size, b"", vmaddr,
                            len(blob), fileoff, len(blob), 7, 7, 0, 0)
    placed.append((fileoff, blob))
    fileoff += len(blob)

header = struct.pack("<IiiIIIII", 0xFEEDFACF, cputype, cpusubtype, MH_CORE, len(segs) + 1,
                     len(seg_cmds) + len(thread_cmd), 0, 0)
with open(out, "wb") as f:
    f.write(header + seg_cmds + thread_cmd)
    for o, blob in placed:
        f.seek(o)
        f.write(blob)
