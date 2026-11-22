# How the patches work

All addresses are CPU addresses unless marked "file". The 256 KB image maps
as: `$4000-$7FFF` = file `0x38000`, `$C000-$FFFF` = file `0x3C000`, and the
banked window `$8000-$BFFF` with page `P` = file `(P - $30) * 0x4000`.

Text in all of these clusters is UTF-16, big-endian.

## Why a hook is needed

The cluster owns its text buffers and refills them whenever it redraws. A
value written into the buffer from outside is overwritten almost at once.
Each patch therefore changes what the cluster's own code does at the moment
it selects or draws the text.

## The CAN receive hook (all patches)

The MSCAN0 receive interrupt vector `$FFB2` points at a small jump table at
`$40BE`. The patch changes the first entry to jump to a helper in unused
flash. The helper looks at the received frame in the MSCAN0 receive
registers (`$0160` id, `$0164-$016B` data), acts on frames meant for it, and
then jumps to the original handler, so normal traffic is unaffected.

### P3 clusters: frames on id `0x720`

| Data byte 0 | Meaning |
|---|---|
| `$80` | write: bytes 1-2 = RAM address, bytes 3-7 = five bytes to store there |
| `$81` | read (31327396 builds only): bytes 1-2 = RAM address; the cluster answers on `0x721` with the address and six bytes |

On 31254762 the text of slot 1 is the 64-byte buffer at `$3CFD`, so 13 write
frames replace the whole 32-character slot.

### P1 clusters (C30 family)

Frames whose data starts `CA FE`: byte 2 = offset (0-63), bytes 3-6 = four
bytes stored at `$3A50 + offset`. `$3A50` is a 64-byte text buffer that the
patch substitutes for trip-computer slots 1 and 5. The helper looks only at
the `CA FE` marker, not at the id; the patch was tested with the 29-bit id
`0x000FFFFE` on MS-CAN at 125 kbit/s, which is what `send_text.py` uses.

## Slot hook: 31254762, 31270367, 31254781

The trip computer picks a 64-byte text template by index:
`CLRA; LSLD x6; ADDD #table`. The patch replaces those ten bytes with a
`JSR` to a helper. For the chosen slot the helper returns the address of the
RAM text buffer; for every other slot it performs the original calculation.
On first use it copies a default text into the buffer.

## Coolant on 31254762

The receive helper also watches id `0x490`. Byte 2 is coolant temperature
plus 60. On each such frame it rewrites the slot-1 buffer with
`Coolant NNC` and lets the frame continue to the cluster's own handler, so
the cluster's coolant monitoring still sees it.

## Draw hook: 31327396

This variant keeps two text areas of two 16-character lines each:

| Area | Line 1 | Line 2 | Content ids |
|---|---|---|---|
| 0 | `$27D3` | `$27F3` | `$2853`, `$2854` |
| 1 (visible trip text) | `$2813` | `$2833` | `$2855`, `$2856` |

The routine at page `$38` `$B2C6` draws area 1. Its first instruction is
replaced by a jump to a helper. When the ids are `$13` / `$0B` (the
instant-consumption slot) the helper writes the coolant text into area 1,
then runs the replaced instruction and returns into the routine. The value
comes from the cluster's own copy of the coolant byte at `$116E`, so no CAN
frame is intercepted.

## Finding these places on another software version

1. Search for the slot calculation `87 59 59 59 59 59 59 C3` (P1 and 2008
   P3) to find the slot hook sites and the table address.
2. Read vector `$FFB2` and the jump table it points to; the first entry is
   the receive handler to chain to.
3. Confirm that the flash you plan to use is erased (`FF`) in the stock
   image.
4. Buffers that are reached through pointers cannot be found by searching
   the image. Dump RAM from the running cluster with the read command and
   look for the text that is on the display.
5. Test the helper in an emulator before flashing, and check every case:
   no frame, other ids, other commands, and every value the display code
   can receive.
