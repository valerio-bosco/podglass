# Protocol reference

Everything the daemon needs to talk to AirPods Pro 2. Agents must implement from this file and must
not go looking on the web: if something here is wrong, record the real bytes in `tests/fixtures/`
and fix this file in the same commit.

Sources (reverse engineered by others, verified against AirPods Pro 2 USB-C firmware 7A305):
LibrePods `docs/AAP Definitions.md`, `linux/ble/blemanager.cpp`, `linux/airpods_packets.h`
(https://github.com/kavishdevar/librepods, GPL-3.0). **Protocol facts are reused here; LibrePods
source code is not copied** (see AGENTS.md, "License").

All hex is written as bytes in wire order.

---

## 1. BLE advertisement ("proximity pairing message")

Seen without any connection. AirPods broadcast it while the case lid is open, while a pod is out
of the case, and for a few seconds after the lid closes.

Filter: manufacturer data with company id `0x004C` (Apple) whose payload starts with `07`.
`data` below is the manufacturer payload **after** the 2-byte company id.

| Offset | Meaning |
|---|---|
| 0 | `0x07` = proximity pairing message type |
| 1 | length of the rest |
| 2 | `0x01` = paired device. `0x00` = pairing mode (different layout: only use it to show the "Set up" card) |
| 3..4 | model id, big endian: `data[3] << 8 \| data[4]` |
| 5 | status byte (bits below) |
| 6 | pods battery: two nibbles, see "primary pod" |
| 7 | high nibble = charging flags, low nibble = case battery |
| 8 | lid: bits 0..2 = lid open counter, bit 3 = lid state (meaningful only when "this pod in case") |
| 9 | color |
| 10 | connection state (meaning per value: to be recorded in phase 0, task P0.3) |
| last 16 | encrypted payload (exact battery, see 1.3) |

Model ids (value of `data[3] << 8 | data[4]`):

| Id | Model | podglass id |
|---|---|---|
| `0x2420` | AirPods Pro 2 (USB-C) | `pro2-usbc` |
| `0x1420` | AirPods Pro 2 (Lightning) | `pro2-lightning` |
| `0x0E20` | AirPods Pro | `pro1` |
| `0x0F20` | AirPods 2 | `airpods2` |
| `0x1320` | AirPods 3 | `airpods3` |
| `0x1920` | AirPods 4 | `airpods4` |
| `0x1B20` | AirPods 4 ANC | `airpods4-anc` |
| `0x0A20` / `0x1F20` | AirPods Max (Lightning / USB-C) | `max` |

Status byte `s = data[5]`:

| Bit | Mask | Meaning |
|---|---|---|
| 5 | `0x20` | primary pod is left (1) / right (0) |
| 6 | `0x40` | the broadcasting pod is in the case |
| 4 | `0x10` | one pod in case |
| 2 | `0x04` | both pods in case |
| 3, 1 | `0x08`, `0x02` | in-ear bits, see below |

Decoding (port exactly, it is easy to get the flips wrong):

```
primary_left = (s & 0x20) != 0
flipped      = not primary_left
this_in_case = (s & 0x40) != 0

left_nib  = (data[6] >> 4) & 0xF if flipped else data[6] & 0xF
right_nib = data[6] & 0xF        if flipped else (data[6] >> 4) & 0xF
case_nib  = data[7] & 0xF
level(n)  = None if n == 15 else min(n * 10, 100)        # coarse: steps of 10 %

flags          = (data[7] >> 4) & 0xF
right_charging = (flags & 0x01) if flipped else (flags & 0x02)
left_charging  = (flags & 0x02) if flipped else (flags & 0x01)
case_charging  = flags & 0x04

xor            = flipped ^ this_in_case
left_in_ear    = (s & 0x08) if xor else (s & 0x02)
right_in_ear   = (s & 0x02) if xor else (s & 0x08)

lid_counter = data[8] & 0x07
lid_open    = ((data[8] >> 3) & 0x01) == 0   # VERIFY in P0.3: confirm which value means open
lid_known   = this_in_case
```

### 1.1 Which AirPods are mine (RPA resolution)

AirPods use a random resolvable private address (RPA) that changes every ~15 minutes. An
address belongs to our AirPods when it resolves with our IRK (Identity Resolving Key):

```
addr   = 6 bytes, most significant first (as printed "AA:BB:CC:DD:EE:FF")
prand  = addr[0:3]          # top two bits must be 0b01 for an RPA
hash   = addr[3:6]
ah(k, r) = AES-128-ECB(key=k, block = 13 zero bytes || r)[-3:]
```

Byte order trap: the Bluetooth spec function `e()` works on little-endian values. LibrePods
reverses key and plaintext before AES and reverses the result. Implement `ah()` in
`podglass/crypto.py` and test it with the vector from the Bluetooth Core Spec
(Vol 3, Part H, D.7): IRK `ec0234a357c8ad05341010a60a397d9b`, prand `708194`, expected hash
`0dfbaa`.

### 1.2 Keys

Both keys come from the AirPods over AAP (section 2.6) the first time we are connected, and are
stored in `$XDG_STATE_HOME/podglass/keys.json` (mode 0600):

```json
{ "AA:BB:CC:DD:EE:FF": { "irk": "<32 hex>", "enc_key": "<32 hex>", "model": "pro2-usbc", "name": "..." } }
```

Before the first connection we have no IRK: then any nearby `pro2-*` advertisement whose
RSSI > -60 dBm counts as "probably mine" and the card shows a "Connect" button, never auto-connects.

### 1.3 Exact battery from the encrypted payload

`plain = AES-128-CBC-decrypt(key=enc_key, iv=16 zero bytes, data=last 16 bytes)` (key used as is,
no reversal). The layout of `plain` is not documented yet: task P0.3 records pairs of
(plain, exact battery from AAP) so the layout can be worked out. Until then the UI shows coarse
battery from the advertisement and exact battery from AAP when connected.

---

## 2. AAP (Apple Accessory Protocol) over L2CAP

Only while the AirPods are connected to this PC over classic Bluetooth.

Socket: `socket.socket(AF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP)`, connect to
`(public_mac, 0x1001)`. No root needed. One message = one packet.

### 2.1 Startup sequence (send in this order, wait for each ack if listed)

| Step | Send | Expect |
|---|---|---|
| 1 handshake | `00 00 04 00 01 00 02 00 00 00 00 00 00 00 00 00` | starts with `01 00 04 00` |
| 2 features (enables Adaptive + conversation awareness during playback) | `04 00 04 00 4D 00 FF 00 00 00 00 00 00 00` | starts with `04 00 04 00 2B 00` (may be missing; do not block) |
| 3 notifications | `04 00 04 00 0F 00 FF FF FF FF` | battery, mode, ear packets start arriving |
| 4 keys (only if keys.json lacks this device) | `04 00 04 00 30 00 05 00` | `04 00 04 00 31 00 02 ...` (2.6) |

All "host bound" packets start with `04 00 04 00` followed by a 2-byte little-endian opcode.

### 2.2 Battery (opcode `04 00`)

```
04 00 04 00 04 00 [count] ([component] 01 [level] [status] 01) * count
```
component: `04` left, `02` right, `08` case. status: `00` unknown, `01` charging,
`02` discharging, `04` disconnected (pod missing: show "—").
Example: `04 00 04 00 04 00 03 02 01 64 02 01 04 01 63 01 01 08 01 11 02 01`
= right 100 % discharging, left 99 % charging, case 17 % discharging.

### 2.3 Ear detection (opcode `06 00`)

```
04 00 04 00 06 00 [primary] [secondary]
```
`00` in ear, `01` out of ear, `02` in case. Map primary/secondary to left/right using the
`primary_left` bit from the latest advertisement; if unknown, assume primary = right.

### 2.4 Listening mode (opcode `09 00`, setting `0D`) - read and write

```
04 00 04 00 09 00 0D [mode] 00 00 00
```
mode: `01` off, `02` noise cancellation, `03` transparency, `04` adaptive.
Writing: send the same packet. The AirPods echo it back when applied. If the echo has a different
mode, the features packet (2.1 step 2) was not accepted: show the echoed mode, do not retry.

UI names (same order as on iPhone): Off, Transparency, Adaptive, Noise Cancellation.

### 2.5 Other control settings (same `09 00` frame)

| Setting byte | Values | Meaning |
|---|---|---|
| `28` | `01` on, `02` off | Conversation Awareness |
| `2E` | `00`..`64` | Adaptive noise level (0 = more noise passes, 100 = less) |
| `1A` | bitmask | which modes the stem long press cycles through (bit0 off, bit1 ANC, bit2 transparency, bit3 adaptive) |

Conversation Awareness volume events (opcode `4B 00`):
`04 00 04 00 4B 00 02 00 01 [level]`: `01`/`02` user started speaking, `03` stopped,
`08`/`09` normal. podglass lowers the PipeWire sink volume to 30 % on `01`/`02` and restores it on
`03`/`08`/`09` (setting, default on).

### 2.6 Keys response (opcode `31 00`)

```
04 00 04 00 31 00 02 | 01 00 10 00 [16-byte IRK] | 04 00 10 00 [16-byte ENC key]
```
Total length >= 47. Parse as TLV after the 7-byte header: `[type] 00 [len_lo] 00 [value]`,
type `01` = IRK, `04` = ENC key. Reject the packet if a length is not 16.

### 2.7 Device information (opcode `1D 00`)

`04 00 04 00 1D ...` then NUL-terminated UTF-8 strings: name, model number, manufacturer,
serial, firmware, ... Use only name, model number and firmware (shown in the popover footer).

---

## 3. BlueZ (D-Bus, system bus, service `org.bluez`)

| Need | API |
|---|---|
| Is it paired / connected | `org.bluez.Device1` properties `Paired`, `Connected`, `Address`, `Name`, `Modalias` |
| Connect audio | `Device1.Connect()` (all profiles). Timeout 15 s. |
| Disconnect | `Device1.Disconnect()` |
| Battery in the rest of the desktop | register a `org.bluez.BatteryProvider1` via `org.bluez.BatteryProviderManager1` on `/org/bluez/hci0` (present on this machine, BlueZ 5.87) and publish the lowest pod level |
| Passive LE scanning | `org.bluez.AdvertisementMonitorManager1`: only available with BlueZ `Experimental = true` (P0.1). Fallback: `bleak` active scan with duty cycle (P0.2) |

Find the AirPods device object by matching `Modalias` vendor `v004C` and the model in keys.json,
or by name containing "AirPods".
