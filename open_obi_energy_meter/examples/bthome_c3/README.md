# ESP32-C3 radio bench

This example runs the actual `bthome_core.cpp` and `bthome_ble.cpp` on a plain
ESP32-C3 with native USB, without a LoRa transceiver. It injects simulated reader
values: +1234, 0 and -850 W, changing every ten seconds. It is not meter firmware
and must not be installed on an OBI gateway.

Back up existing firmware before flashing. Create `bench_secrets.h` beside
`main.cpp` (the file is ignored by Git):

```cpp
#pragma once
#define BENCH_BINDKEY "REPLACE_WITH_32_RANDOM_HEX_CHARACTERS"
#define BENCH_AP_PASSWORD "REPLACE_WITH_PRIVATE_WIFI_PASSWORD"
```

Generate a fresh key, for example with
`python3 -c 'import secrets; print(secrets.token_hex(16))'`. Use an AP password
of at least eight characters. Keep the key for your BTHome receiver. Build from
`open_obi_energy_meter`:

```sh
pio run -e bthome_c3_bench
pio run -e bthome_c3_bench -t upload --upload-port /dev/ttyACM0
pio device monitor --port /dev/ttyACM0 --baud 115200
```

The board advertises as `OBI-PWR`; serial output prints its Bluetooth MAC.
It also starts the password-protected AP `OBI-BLE-Test`.
`http://192.168.4.1/api/bthome` returns status without secrets.
The bench uses reader ID `010203` and a five-second freshness timeout.

Send these commands over USB serial, followed by a newline:

| Command | Effect |
| --- | --- |
| `power 1234`, `power 0`, `power -850` | Hold a simulated reading |
| `pause` | Stop new samples; BLE expires after five seconds |
| `resume` | Resume sampling |
| `auto` | Resume the ten-second value cycle |
| `wifi off`, `wifi on` | Disable/enable the test AP |
| `reboot` | Restart and reserve a new counter block |
| `block` | Block web processing for twelve seconds; samples continue |
| `block stale` | Block web processing and pause samples |

Free/minimum heap and Wi-Fi mode are logged every five seconds.
Configuration uses the same NVS namespaces as production. Rebooting retains the
counter high-water mark; do not erase NVS or restore old backups with the same
bindkey. Use a new key after either operation.

Acceptance requires receiving actual advertisements and independently checking
authenticated decryption, signed power, stale-data shutdown and monotonically
increasing counters across restart. This validates the BLE path on a generic C3.
LoRa reception, OBI OTA installation, full gateway memory use and operation under
network traffic still require the real OBI gateway and reader.

The simulated reader runs in a separate FreeRTOS task. The two `block` commands
hold the same loop that calls `server.handleClient()` for twelve seconds. The
production BLE worker must keep transmitting fresh readings throughout `block`
and expire old data during `block stale`.

For reproducible radio acceptance, install the packages from `tests/requirements.txt`
and `pyserial`, then use the host Bluetooth adapter:

```sh
python examples/bthome_c3/radio_acceptance.py \
  --port /dev/ttyACM0 --address AA:BB:CC:DD:EE:FF \
  --key-file /private/bench-secrets.json --output /private/radio-results
```

The private JSON file must contain `{"bindkey":"YOUR_32_HEX_CHARACTERS"}` matching
the firmware key. The script never prints it. It checks signed power, blocked
web processing with fresh and stale samples, Wi-Fi on/off, restart counters,
independent authenticated HA decoding and one minute of heap stability. Results
and serial logs are written into the specified output directory.

## Physical worker acceptance

Tested on a generic ESP32-C3 with an Intel host Bluetooth adapter on 2026-10-29.
All thirteen acceptance checks passed, with 147 distinct received packets and
no authentication or Home Assistant decoder errors. The twelve-second web-loop
block retained ten fresh packets in the measured ten-second inner window;
the largest inter-packet gap was 1.154 seconds. With samples paused during the
block, the last advertisement arrived after 4.068 seconds (five-second limit).
The counter advanced from 32837 to 36864 after restart. The one-minute stability
window received sixty packets with constant free heap of 155444 bytes.

These measurements use simulated input and the small bench firmware. They do
not establish OBI LoRa coexistence, OTA/history behavior, full-gateway memory
headroom or long-term reliability. No key or firmware binary is published.
