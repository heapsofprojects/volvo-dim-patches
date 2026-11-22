# Volvo DIM text patches

Small firmware patches for Volvo instrument clusters (DIM) that let the
trip-computer text line show your own content: text sent over CAN, or the
engine coolant temperature.

This repository contains **only the changes** (byte diffs against a known
stock image, with checksums), the logic behind them, and a tool to apply
them to a dump you have read from your own cluster. It contains **no Volvo
firmware** and no flashing tool.

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

## Applying a patch

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

## How it works

See [docs/how-it-works.md](docs/how-it-works.md). In short:

- The cluster builds each text line in RAM and redraws it continuously, so
  writing the text buffer from outside does not hold. Every patch therefore
  hooks the cluster's own code at the point where it picks or draws the text.
- New code goes into unused (erased) flash. A hook is a 2 to 10 byte change
  that jumps to it and returns to the original code.
- `listings/*.lst` is a disassembly of every byte each patch writes.

## Warnings

- A wrong image can leave a cluster unable to boot. Only flash if you can
  recover it, and never flash a patch whose stock checksum does not match.
- The patches do not hide the cluster's own warning messages. Do not change
  them so that they do.
- Text sent over CAN is taken as-is by the patched cluster. Do not connect
  untrusted devices to the car's CAN bus.
- This project is not affiliated with or endorsed by Volvo. Use it on your
  own vehicle and at your own risk.

## Licence

GPL-3.0-or-later. If you distribute a modified version or a tool built on
this, you must publish its source under the same licence.
