# Volvo DIM text patches

Custom text on the Volvo P1 / P3 instrument cluster (DIM).

## Why this exists

I started this project because I found it frustrating that I could not
display custom text in the P1 / P3 DIM. The display is right there in front
of the driver, the car already knows things worth showing on it (coolant
temperature, for one), and there was no way to put them there.

So I worked out how the cluster draws its text and wrote small patches that
make it show what I want. This repository is the result, published so that
others can use it, check it and build on it.

Follow the project: [YouTube](https://www.youtube.com/@HeapsofProjects) · [Instagram](https://www.instagram.com/heapsofprojects/)

## What it is

Small firmware patches for Volvo instrument clusters (DIM) that let the
trip-computer text line show your own content: text sent over CAN, or the
engine coolant temperature.

This repository contains **only the changes** (byte diffs against a known
stock image, with checksums), the logic behind them, and a tool to apply
them to a dump you have read from your own cluster. It contains **no Volvo
firmware** and no flashing tool.

## Try it online

**[heapsofprojects.github.io/volvo-dim-patches](https://heapsofprojects.github.io/volvo-dim-patches/)**

Pick your flash dump, and the page tells you whether a patch exists for it
and gives you the patched file. Everything happens in your browser. Your
file is not uploaded anywhere.

## How it works, in plain words

1. **The cluster is a small computer.** Its program sits in a 256 KB memory
   chip. Reading that chip gives you one file, the "flash dump".
2. **Somewhere in that program the cluster decides which text to show** on
   the trip-computer line. It is a few instructions that pick one of the
   stored texts by its number.
3. **The chip has unused space**, areas that were never written and read as
   `FF`.
4. **A small new routine goes into that unused space.** It says: "if this is
   the line I care about, use my text; otherwise do exactly what the
   original did."
5. **A handful of original bytes are changed** so that the cluster calls the
   new routine at that point and then carries on as before. Depending on
   the cluster that is between 5 and 22 bytes in total.
6. **The text has to come from somewhere.** The cluster already listens to
   the car's CAN network, so a second small routine watches the incoming
   messages. When it sees one addressed to it, it stores the text in the
   cluster's memory. For coolant temperature no extra hardware is needed:
   the value is already there, and the routine turns the number into
   characters.

Nothing else in the cluster is touched. Gauges, warnings and mileage work
as before, and flashing the original dump back removes the patch.

## How it was done

- Read the flash and take the program apart with a disassembler to find
  the place where the text is chosen.
- When a text buffer could not be found in the program itself, add a
  temporary read command, dump the running cluster's memory, and look for
  the words that were on the display at that moment.
- Write the new routines by hand in HCS12 machine code.
- Run every routine in an emulator with every possible input before it
  went near a real cluster, then test on a bench cluster, then in the car.

## Where to look

| If you want to see... | Look at |
|---|---|
| exactly which bytes change | [`patches/`](patches/), one JSON file per patch |
| what the new routines do, instruction by instruction | [`listings/`](listings/) |
| addresses, CAN frame formats and the hook points | [docs/how-it-works.md](docs/how-it-works.md) |
| how to find the same places in another software version | [the last section of that document](docs/how-it-works.md#finding-these-places-on-another-software-version) |
| the patching logic of the online tool | [`assets/patcher.js`](assets/patcher.js) |
| the same thing as a command-line tool | [`apply_patch.py`](apply_patch.py) |
| how text is sent to a patched cluster | [`send_text.py`](send_text.py) |

## Supported clusters

| Patch id | Cluster | SW part no. | What it does | Status |
|---|---|---|---|---|
| `c30_31270367_text` | C30 / S40 / V50 (P1), MC9S12DP256 | 31270367 | Trip-computer slot shows text sent over CAN | confirmed on a bench cluster |
| `c30_31254781_text` | C30 / S40 / V50 (P1), MC9S12DP256 | 31254781 | Same, ported | confirmed on a car |
| `xc70_31254762_text` | XC70 / V70 / S80 (P3) 2008, MC9S12H256 | 31254762 | Slot 1 text writable over CAN | confirmed on a car |
| `xc70_31254762_coolant` | same | 31254762 | Text patch plus automatic `Coolant NNC` | confirmed on a car |
| `p3de_31327396_coolant` | P3, German-market 256K variant, MC9S12H256 | 31327396 | Instant-consumption slot shows `COOL NNNC` | confirmed on a car |
| `p3de_31327396_coolant_v4` | same | 31327396 | Same, shows `Coolant 35C`, fixes a byte shift | emulator-tested only |

Volvo reused some software part numbers for different builds. The apply tool
therefore matches on the SHA-256 of the whole stock image, not on the part
number. If your dump does not match, the patch is not for your cluster.

Each `patches/*.json` file carries a `notes` list. Read it: two of the
confirmed patches have known flaws that are documented there.

## Applying a patch offline

You need a full 256 KB flash dump of your own cluster, and your own means of
writing a 256 KB image back.

```bash
python apply_patch.py --list
python apply_patch.py xc70_31254762_coolant my_stock_dump.bin patched.bin
```

The tool checks your dump against the expected stock checksum, checks every
location it is about to change, writes the patched image to a new file, and
checks the result. It never modifies your dump.

Keep your stock dump. Flashing it back restores the cluster.

## Sending text to a patched cluster

Once a text patch is in the cluster, it shows whatever text arrives on the
car's MS-CAN bus (125 kbit/s, OBD pins 3 and 11) in the format below.
[`send_text.py`](send_text.py) does this from a Windows PC with any J2534
cable (DiCE, Mongoose and similar), using only the Python standard library:

```bash
python send_text.py --list
python send_text.py xc70 "Hello from CAN"
python send_text.py c30 "HELLO FROM CAN"
python send_text.py xc70 "Hello" --dry-run
```

`--list` shows the cables Windows knows about, `--keep` re-sends twice a
second until you stop it, and `--dry-run` prints the frames without
sending, which is what you need if you use other hardware such as an ESP32
or an Arduino with a CAN shield. Python and the cable's driver must have
the same bitness (a 32-bit driver needs 32-bit Python).

| Patch | CAN id | Data bytes | Frames for 32 characters |
|---|---|---|---|
| `xc70_31254762_text`, `xc70_31254762_coolant` | `0x720` (11-bit) | `80 hi lo b0 b1 b2 b3 b4`: store five bytes at RAM address `hi:lo`; slot 1 starts at `$3CFD` | 13 |
| `c30_31270367_text`, `c30_31254781_text` | `0x000FFFFE` (29-bit) | `CA FE off c0 c1 c2 c3 00`: store four bytes at offset `off` (0 to 60) of the text buffer | 16 |

Text is UTF-16, big-endian, 32 characters, padded with spaces. The C30
sender upper-cases the text. Sending each frame twice makes the update
reliable.

The coolant patches for SW 31327396 need no sender: they read the
temperature inside the cluster. With `xc70_31254762_coolant` slot 1 is
rewritten with the temperature on every coolant frame, so text you send
there does not stay; use `xc70_31254762_text` if you want your own text.

The frame builders in `send_text.py` were checked against the tools used
on the car and against an emulated patched cluster. The J2534 part follows
those tools as well, but this script itself has not yet been run on a real
cable. If you try it, please report how it went.

## Warning: this can brick your cluster

Writing a modified image to an instrument cluster can leave it **unable to
start**. A failed or interrupted write, a wrong file or a patch that does
not suit your cluster can all do that. Until it is recovered you would have
no speedometer, gauges or warning messages.

Only go ahead if you have a verified copy of your original dump and know
how to write it back to a cluster that no longer responds.

**You do this entirely at your own risk. The author takes no responsibility
for any damage, cost or loss that results from using this tool or these
patches.** They are provided as they are, with no warranty of any kind (see
sections 15 and 16 of the licence).

## Other things to know

- Never flash a patch whose stock checksum does not match your dump.
- The patches do not hide the cluster's own warning messages. Do not change
  them so that they do.
- Text sent over CAN is taken as-is by the patched cluster. Do not connect
  untrusted devices to the car's CAN bus.
- This project is not affiliated with or endorsed by Volvo. Use it on your
  own vehicle and at your own risk.

## Contact

Questions, results from your own cluster, or a software version that is not
covered yet: open an issue here or write to heapsofprojects@gmail.com.
Please do not send or attach firmware files.

## Licence

GPL-3.0-or-later. If you distribute a modified version or a tool built on
this, you must publish its source under the same licence.
