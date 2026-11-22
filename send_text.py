#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Send text to a patched Volvo DIM over the car's MS-CAN bus.

    python send_text.py --list                      show J2534 cables
    python send_text.py xc70 "Hello from CAN"       2008 P3, SW 31254762
    python send_text.py c30 "HELLO FROM CAN"        P1, SW 31270367 / 31254781
    python send_text.py xc70 "Hello" --dry-run      only print the frames

Windows only. It talks to any J2534 cable (DiCE, Mongoose, ...) through the
driver that came with the cable, using nothing but the Python standard
library. Python and the cable's driver must have the same bitness: a
32-bit driver needs 32-bit Python.

The cluster must already carry the matching text patch. On an unpatched
cluster these frames do nothing useful. The coolant patches for SW 31327396
need no sender: they read the temperature inside the cluster.

If you use other CAN hardware, --dry-run prints the exact frames to send.
Both families use MS-CAN, 125 kbit/s (OBD pins 3 and 11).
"""
import argparse
import ctypes
import os
import struct
import sys
import time

LINE_CHARS = 32            # one slot = 32 characters = 64 bytes of UTF-16 BE

# ---- what each cluster family expects ---------------------------------
#  xc70: 11-bit id 0x720, data = 80 hi lo b0 b1 b2 b3 b4
#        -> the patch stores b0..b4 at RAM address hi:lo.
#        The slot-1 text buffer is the 64 bytes at $3CFD.
#  c30 : 29-bit id 0x000FFFFE, data = CA FE off c0 c1 c2 c3 00
#        -> the patch stores c0..c3 at offset `off` (0..60) of its 64-byte
#        text buffer. This is the id the patch was tested with; the patch
#        itself only looks for the CA FE marker.
XC70_ID, XC70_WRITE, XC70_SLOT1 = 0x720, 0x80, 0x3CFD
C30_ID = 0x000FFFFE


def encode(text, upper=False):
    if upper:
        text = text.upper()
    return text[:LINE_CHARS].ljust(LINE_CHARS).encode("utf-16-be", errors="replace")


def frames_xc70(text):
    data = encode(text)
    out = []
    for i in range(0, len(data), 5):
        addr = XC70_SLOT1 + i
        chunk = data[i:i + 5]
        out.append((XC70_ID, False,
                    (bytes([XC70_WRITE, addr >> 8, addr & 0xFF]) + chunk).ljust(8, b"\x00")))
    return out


def frames_c30(text):
    data = encode(text, upper=True)
    return [(C30_ID, True, bytes([0xCA, 0xFE, off]) + data[off:off + 4] + b"\x00")
            for off in range(0, len(data), 4)]


FAMILIES = {"xc70": frames_xc70, "c30": frames_c30}

# ---- J2534 ------------------------------------------------------------
REG_PATH = r"SOFTWARE\PassThruSupport.04.04"
STATUS_NOERROR = 0
CAN, CAN_PS = 0x05, 0x8004
CAN_29BIT_ID = 0x0100
DICE_SECOND_PORT = 0x20000000      # DiCE vendor flag: route to MS-CAN
SET_CONFIG, LOOPBACK, J1962_PINS = 0x02, 0x03, 0x8001
PINS_MS_CAN = 0x030B               # OBD pins 3 and 11
PROCESS_BITS = struct.calcsize("P") * 8


class PASSTHRU_MSG(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("ProtocolID", ctypes.c_ulong), ("RxStatus", ctypes.c_ulong),
                ("TxFlags", ctypes.c_ulong), ("Timestamp", ctypes.c_ulong),
                ("DataSize", ctypes.c_ulong), ("ExtraDataIndex", ctypes.c_ulong),
                ("Data", ctypes.c_ubyte * 4128)]


class SCONFIG(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("Parameter", ctypes.c_ulong), ("Value", ctypes.c_ulong)]


class SCONFIG_LIST(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("NumOfParams", ctypes.c_ulong),
                ("ConfigPtr", ctypes.POINTER(SCONFIG))]


def dll_bits(path):
    try:
        with open(path, "rb") as f:
            head = f.read(0x40)
            if head[:2] != b"MZ":
                return None
            f.seek(int.from_bytes(head[0x3C:0x40], "little"))
            if f.read(4) != b"PE\x00\x00":
                return None
            return {0x014C: 32, 0x8664: 64}.get(int.from_bytes(f.read(2), "little"))
    except OSError:
        return None


def list_devices():
    import winreg
    found, seen = [], set()
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH, 0,
                                  winreg.KEY_READ | view)
        except OSError:
            continue
        with root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(root, sub, 0, winreg.KEY_READ | view) as k:
                        dll = winreg.QueryValueEx(k, "FunctionLibrary")[0]
                        try:
                            name = winreg.QueryValueEx(k, "Name")[0]
                        except OSError:
                            name = sub
                except OSError:
                    continue
                if not dll or dll.lower() in seen:
                    continue
                seen.add(dll.lower())
                found.append({"name": str(name), "dll": str(dll), "bits": dll_bits(dll)})
    return found


class Cable:
    def __init__(self, dev, extended):
        if dev["bits"] and dev["bits"] != PROCESS_BITS:
            raise RuntimeError("%s has a %d-bit driver but this is %d-bit Python."
                               % (dev["name"], dev["bits"], PROCESS_BITS))
        folder = os.path.dirname(os.path.abspath(dev["dll"]))
        if hasattr(os, "add_dll_directory") and os.path.isdir(folder):
            os.add_dll_directory(folder)
        self.lib = ctypes.WinDLL(dev["dll"])
        ul, ulp = ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)
        msgp = ctypes.POINTER(PASSTHRU_MSG)
        for fn, args in (("PassThruOpen", [ctypes.c_void_p, ulp]),
                         ("PassThruClose", [ul]),
                         ("PassThruConnect", [ul, ul, ul, ul, ulp]),
                         ("PassThruDisconnect", [ul]),
                         ("PassThruWriteMsgs", [ul, msgp, ulp, ul]),
                         ("PassThruIoctl", [ul, ul, ctypes.c_void_p, ctypes.c_void_p])):
            f = getattr(self.lib, fn)
            f.argtypes, f.restype = args, ctypes.c_long
        self.dev = ctypes.c_ulong(0)
        self.ch = None
        if self.lib.PassThruOpen(None, ctypes.byref(self.dev)) != STATUS_NOERROR:
            raise RuntimeError("could not open the cable - is it plugged in?")
        ext = CAN_29BIT_ID if extended else 0
        is_dice = os.path.basename(dev["dll"]).lower().startswith("tsdice")
        attempts = ([(CAN, DICE_SECOND_PORT | ext, None)] if is_dice else
                    [(CAN_PS, ext, PINS_MS_CAN), (CAN, ext, PINS_MS_CAN)])
        ch = ctypes.c_ulong(0)
        for proto, flags, pins in attempts:
            if self.lib.PassThruConnect(self.dev.value, proto, flags, 125000,
                                        ctypes.byref(ch)) != STATUS_NOERROR:
                continue
            if pins is not None and self._config(ch.value, J1962_PINS, pins) != STATUS_NOERROR:
                self.lib.PassThruDisconnect(ch.value)
                continue
            self.ch, self.proto = ch.value, proto
            break
        if self.ch is None:
            self.lib.PassThruClose(self.dev.value)
            raise RuntimeError("the cable would not open MS-CAN (125 kbit/s, pins 3/11)")
        self._config(self.ch, LOOPBACK, 0)

    def _config(self, ch, param, value):
        cfg = SCONFIG(param, value)
        lst = SCONFIG_LIST(1, ctypes.pointer(cfg))
        return self.lib.PassThruIoctl(ch, SET_CONFIG, ctypes.byref(lst), None)

    def send(self, can_id, extended, data):
        m = PASSTHRU_MSG()
        m.ProtocolID = self.proto
        m.TxFlags = CAN_29BIT_ID if extended else 0
        for i, b in enumerate(can_id.to_bytes(4, "big") + bytes(data)):
            m.Data[i] = b
        m.DataSize = 4 + len(data)
        n = ctypes.c_ulong(1)
        return self.lib.PassThruWriteMsgs(self.ch, ctypes.byref(m),
                                          ctypes.byref(n), 500) == STATUS_NOERROR

    def close(self):
        if self.ch is not None:
            self.lib.PassThruDisconnect(self.ch)
        self.lib.PassThruClose(self.dev.value)


def send_all(cable, frames, repeat=2, gap=0.002):
    ok = 0
    for can_id, ext, data in frames:
        for _ in range(repeat):
            ok += cable.send(can_id, ext, data)
            time.sleep(gap)
    return ok


def main():
    ap = argparse.ArgumentParser(description="Send text to a patched Volvo DIM.")
    ap.add_argument("family", nargs="?", choices=sorted(FAMILIES))
    ap.add_argument("text", nargs="?")
    ap.add_argument("--list", action="store_true", help="list J2534 cables and exit")
    ap.add_argument("--device", type=int, default=None, help="cable number from --list")
    ap.add_argument("--keep", action="store_true",
                    help="keep re-sending twice a second until Ctrl+C")
    ap.add_argument("--dry-run", action="store_true", help="print the frames, send nothing")
    a = ap.parse_args()

    if a.list:
        devs = list_devices() if sys.platform == "win32" else []
        for i, d in enumerate(devs):
            note = "" if d["bits"] in (None, PROCESS_BITS) else \
                "   (needs %d-bit Python)" % d["bits"]
            print("%d: %s%s" % (i, d["name"], note))
        if not devs:
            print("no J2534 cable drivers found")
        return 0
    if not a.family or a.text is None:
        ap.error("give a family (xc70 or c30) and the text, or use --list")
    frames = FAMILIES[a.family](a.text)
    if a.dry_run:
        for can_id, ext, data in frames:
            print(("%08X" if ext else "%03X") % can_id, data.hex(" "))
        return 0
    if sys.platform != "win32":
        raise SystemExit("J2534 cables need Windows. Use --dry-run to get the frames.")
    devs = list_devices()
    usable = [d for d in devs if d["bits"] in (None, PROCESS_BITS)]
    if a.device is not None:
        if not 0 <= a.device < len(devs):
            raise SystemExit("no such cable; see --list")
        dev = devs[a.device]
    elif usable:
        dev = usable[0]
    else:
        raise SystemExit("no usable J2534 cable found; see --list")
    try:
        cable = Cable(dev, extended=frames[0][1])
    except (RuntimeError, OSError) as e:
        raise SystemExit("%s: %s" % (dev["name"], e))
    try:
        print("using %s" % dev["name"])
        while True:
            sent = send_all(cable, frames)
            print("sent %d of %d frames" % (sent, 2 * len(frames)))
            if not a.keep:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        time.sleep(0.2)
        cable.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
