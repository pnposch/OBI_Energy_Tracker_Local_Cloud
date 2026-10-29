import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import serial
from bleak import BleakScanner
from bthome_ble import BTHomeBluetoothDeviceData
from Crypto.Cipher import AES
from habluetooth import BluetoothServiceInfoBleak

parser = argparse.ArgumentParser(description='Check encrypted BTHome over physical BLE.')
parser.add_argument('--port', required=True)
parser.add_argument('--address', required=True)
parser.add_argument('--key-file', required=True, type=Path)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
ROOT = args.output
ROOT.mkdir(parents=True, exist_ok=True)
KEY = bytes.fromhex(json.loads(args.key_file.read_text())['bindkey'])
if len(KEY) != 16:
    parser.error('Bindkey must contain 16 bytes')
ADDRESS = args.address.upper()
PORT = args.port
UUID = '0000fcd2-0000-1000-8000-00805f9b34fb'
decoder = BTHomeBluetoothDeviceData(bindkey=KEY)
packets, errors, logs, checks = [], [], [], []
seen = set()
started = time.monotonic()
last_radio = 0
buffer = ''


def receive(device, advertisement):
    global last_radio
    if device.address.upper() != ADDRESS:
        return
    data = advertisement.service_data.get(UUID)
    if not data:
        return
    last_radio = time.monotonic()
    try:
        assert len(data) == 14 and data[0] == 0x41
        counter = int.from_bytes(data[-8:-4], 'little')
        if counter in seen:
            return
        nonce = bytes.fromhex(ADDRESS.replace(':', '')) + bytes.fromhex('d2fc') + data[:1] + data[-8:-4]
        cipher = AES.new(KEY, AES.MODE_CCM, nonce=nonce, mac_len=4)
        plain = cipher.decrypt_and_verify(data[1:-8], data[-4:])
        assert plain[0] == 0x5c
        watts = int.from_bytes(plain[1:], 'little', signed=True) / 100
        info = BluetoothServiceInfoBleak(
            name=advertisement.local_name or 'OBI-PWR', address=ADDRESS,
            rssi=advertisement.rssi, manufacturer_data=advertisement.manufacturer_data,
            service_data=advertisement.service_data, service_uuids=advertisement.service_uuids,
            source='physical-c3', device=device, advertisement=advertisement,
            connectable=False, time=time.monotonic(), tx_power=advertisement.tx_power,
        )
        update = decoder.update(info)
        ha_power = next((value.native_value for key, value in update.entity_values.items()
                         if key.key == 'power'), None)
        assert ha_power == watts, (ha_power, watts)
        assert not packets or counter > packets[-1]['counter']
        seen.add(counter)
        packet = dict(seconds=round(time.monotonic() - started, 3), counter=counter,
                      watts=watts, ha_watts=ha_power, rssi=advertisement.rssi)
        packets.append(packet)
    except Exception as error:
        errors.append(repr(error))
        print('RADIO ERROR', repr(error), flush=True)


def open_serial():
    connection = serial.Serial()
    connection.port, connection.baudrate, connection.timeout = PORT, 115200, 0
    connection.dtr, connection.rts = False, False
    connection.open()
    connection.dtr = True
    return connection


async def collect(connection, seconds):
    global buffer
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            buffer += connection.read_all().decode(errors='replace')
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                logs.append(line.strip())
        except serial.SerialException:
            connection.close()
            await asyncio.sleep(.5)
            try:
                connection = open_serial()
            except serial.SerialException:
                pass
        await asyncio.sleep(.05)
    return connection


def command(connection, value):
    connection.write((value + '\n').encode())
    connection.flush()


def check(name, passed, **details):
    checks.append(dict(name=name, passed=bool(passed), **details))
    print(json.dumps(checks[-1]), flush=True)
    assert passed, name


async def main():
    connection = open_serial()
    try:
        async with BleakScanner(receive):
            connection = await collect(connection, 6)
            check('startup', bool(packets))
            for power in [1234, 0, -850]:
                offset = len(packets)
                command(connection, f'power {power}')
                connection = await collect(connection, 5)
                matching = [p for p in packets[offset:] if p['watts'] == power]
                check(f'power_{power}', len(matching) >= 3, received=len(matching))
            command(connection, 'wifi off')
            offset, log_offset = len(packets), len(logs)
            connection = await collect(connection, 12)
            check('wifi_off', len(packets) - offset >= 4 and any('wifi=0' in s for s in logs[log_offset:]),
                  received=len(packets) - offset, serial_lines=logs[log_offset:])
            command(connection, 'wifi on')
            offset, log_offset = len(packets), len(logs)
            connection = await collect(connection, 7)
            check('wifi_ap_on', len(packets) - offset >= 4 and any('wifi=2' in s for s in logs[log_offset:]))
            offset, log_offset = len(packets), len(logs)
            blocked_at = time.monotonic() - started
            command(connection, 'block')
            connection = await collect(connection, 14)
            during = [p for p in packets[offset:] if 1 <= p['seconds'] - blocked_at <= 11]
            gaps = [b['seconds'] - a['seconds'] for a, b in zip(during, during[1:])]
            block_log = logs[log_offset:]
            check('blocked_web_fresh_samples', len(during) >= 8 and bool(gaps) and max(gaps) < 2.5
                  and 'BLOCK start mode=fresh' in block_log
                  and any(s.startswith('BLOCK end elapsed=12') for s in block_log),
                  packets=len(during), max_gap_seconds=round(max(gaps), 3) if gaps else None,
                  serial_lines=block_log)
            log_offset = len(logs)
            blocked_at = time.monotonic()
            command(connection, 'block stale')
            connection = await collect(connection, 14)
            check('blocked_web_stale_stops', last_radio - blocked_at <= 5.5
                  and 'BLOCK start mode=stale' in logs[log_offset:]
                  and any(s.startswith('BLOCK end elapsed=12') for s in logs[log_offset:]),
                  last_radio_after_block=round(last_radio - blocked_at, 3))
            command(connection, 'resume')
            connection = await collect(connection, 3)
            command(connection, 'pause')
            paused_at = time.monotonic()
            connection = await collect(connection, 9)
            check('stale_stops_radio', last_radio - paused_at <= 5.5,
                  last_radio_after_pause=round(last_radio - paused_at, 3))
            offset = len(packets)
            command(connection, 'resume')
            connection = await collect(connection, 5)
            check('resume', len(packets) - offset >= 3)
            previous = packets[-1]['counter']
            offset = len(packets)
            command(connection, 'reboot')
            connection = await collect(connection, 10)
            following = packets[offset:]
            check('persistent_counter_after_restart', bool(following) and
                  following[0]['counter'] >= ((previous // 4096) + 1) * 4096,
                  before=previous, after=following[0]['counter'] if following else None)
            command(connection, 'power -850')
            connection = await collect(connection, 6)
            offset, log_offset = len(packets), len(logs)
            for interval in range(3):
                connection = await collect(connection, 20)
                print(f'Stability: {(interval + 1) * 20} seconds', flush=True)
            heaps = [int(match.group(1)) for line in logs[log_offset:]
                     if (match := re.search(r' heap=(\d+)', line))]
            check('one_minute_stability', len(packets) - offset >= 45 and len(heaps) >= 10
                  and max(heaps) - min(heaps) < 8192,
                  packets=len(packets) - offset,
                  heap_min=min(heaps) if heaps else None, heap_max=max(heaps) if heaps else None)
            check('authenticated_ha_decoding', not errors, packets=len(packets), errors=errors)
            command(connection, 'auto')
            connection = await collect(connection, 2)
    finally:
        connection.close()
        (ROOT / 'radio-results.json').write_text(json.dumps(dict(
            address=ADDRESS, elapsed_seconds=round(time.monotonic() - started, 2),
            checks=checks, errors=errors, packets=packets), indent=2) + '\n')
        (ROOT / 'radio-serial.log').write_text('\n'.join(logs) + '\n')


if __name__ == '__main__':
    asyncio.run(main())
