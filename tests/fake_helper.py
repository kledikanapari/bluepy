"""
Minimal stand-in for bluepy-helper, used by test_peripheral.py

It speaks the same line protocol, and like the original helper it silently
ignores 'conn' unless it is disconnected. Special device addresses:

    11:11:11:11:11:11   never connects (stays in 'tryconn', like a timeout)
    33:33:33:33:33:33   as above, but without even replying 'tryconn'
    22:22:22:22:22:22   connection fails, with an error message
    any other           connects

Once connected, the device has one service (Battery, handles 0x10-0x15):

    0x11/0x12   Battery Level: read, notify; CCCD at 0x13. While notifications
                are on, values 1, 2, 3... are sent every NOTIFY_INTERVAL
    0x14/0x15   characteristic without descriptors: read, write. Writing ff
                to it makes the device disconnect
    0xFFFF      reading it never gets a reply

On interface 1, scanning works and finds two devices; elsewhere it fails.

Every command received is appended to the file named by $FAKE_HELPER_LOG,
prefixed with this process's PID.
"""

import os
import sys
import threading
import time

SEP = '\x1e'
NEVER_CONNECTS = '11:11:11:11:11:11'
FAILS = '22:22:22:22:22:22'
NEVER_ANSWERS = '33:33:33:33:33:33'

NOTIFY_INTERVAL = 0.02
BATTERY_SERVICE = '0000180f-0000-1000-8000-00805f9b34fb'
CHARS = [   # (declaration handle, properties, value handle, UUID)
    (0x11, 0x12, 0x12, '00002a19-0000-1000-8000-00805f9b34fb'),
    (0x14, 0x0A, 0x15, '00002a1a-0000-1000-8000-00805f9b34fb'),
]
DESCRIPTORS = {0x13: '00002902-0000-1000-8000-00805f9b34fb'}
VALUES = {0x12: '2A', 0x15: '01'}

SCAN_RESULTS = [
    # Flags, complete name "Foo", 16-bit services 180F
    ['addr=bAABBCCDDEE01', 'type=h1', 'rssi=h3C', 'flag=h0', 'd=b020106040946' + '6F6F' + '03030F18'],
    # Not connectable, short name "Bar", manufacturer 0x004C data 0102
    ['addr=bAABBCCDDEE02', 'type=h2', 'rssi=h5A', 'flag=h4', 'd=b0408426172' + '05FF4C000102'],
]

out_lock = threading.Lock()


def send(*fields):
    with out_lock:
        sys.stdout.write(SEP.join(fields) + '\n')
        sys.stdout.flush()


def main():
    state = 'disc'
    dst = None
    notifying = threading.Event()
    log = os.environ.get('FAKE_HELPER_LOG')
    iface = sys.argv[1] if len(sys.argv) > 1 else '0'
    send('# fake bluepy-helper')

    def status(extra=()):
        fields = ['rsp=$stat', 'state=$' + state]
        if state != 'disc':
            fields.append("dst='" + dst)
        fields += ['mtu=h0', "sec='low"] + list(extra)
        send(*fields)

    def notifier():
        value = 0
        while True:
            notifying.wait()
            value = (value + 1) % 256
            send('rsp=$ntfy', 'hnd=h12', 'd=b%02X' % value)
            time.sleep(NOTIFY_INTERVAL)

    threading.Thread(target=notifier, daemon=True).start()

    def remote_disconnect():
        nonlocal state
        time.sleep(0.1)
        notifying.clear()
        state = 'disc'
        status()

    for line in iter(sys.stdin.readline, ''):
        if log:
            with open(log, 'a') as f:
                f.write('%d %s' % (os.getpid(), line))
        args = line.split()
        if not args:
            continue
        cmd = args[0]
        if cmd == 'quit':
            break
        elif cmd == 'stat':
            status()
        elif cmd == 'conn':
            if state != 'disc':
                continue                  # what the original helper did
            dst = args[1]
            state = 'tryconn'
            if dst == NEVER_ANSWERS:
                continue
            status()
            if dst == FAILS:
                state = 'disc'
                status(["emsg='Connection refused (111)"])
            elif dst != NEVER_CONNECTS:
                state = 'conn'
                status()
        elif cmd == 'disc':
            notifying.clear()
            state = 'disc'
            status()
        elif cmd == 'svcs':
            send('rsp=$find', 'hstart=h10', 'hend=h15', "uuid='" + BATTERY_SERVICE)
        elif cmd == 'char':
            fields = ['rsp=$find']
            for (hnd, props, vhnd, uuid) in CHARS:
                fields += ['hnd=h%X' % hnd, 'props=h%X' % props, 'vhnd=h%X' % vhnd, "uuid='" + uuid]
            send(*fields)
        elif cmd == 'desc':
            start, end = int(args[1], 16), int(args[2], 16)
            found = [h for h in sorted(DESCRIPTORS) if start <= h <= end]
            if not found:
                send('rsp=$err', 'code=$atterr', 'estat=hA', "emsg='Attribute not found")
                continue
            fields = ['rsp=$desc']
            for h in found:
                fields += ['hnd=h%X' % h, "uuid='" + DESCRIPTORS[h]]
            send(*fields)
        elif cmd == 'rd':
            hnd = int(args[1], 16)
            if hnd in VALUES:
                send('rsp=$rd', 'd=b' + VALUES[hnd])
            elif hnd != 0xFFFF:
                send('rsp=$err', 'code=$atterr', 'estat=h1', "emsg='Invalid handle")
        elif cmd in ('wr', 'wrr'):
            hnd, value = int(args[1], 16), args[2].upper() if len(args) > 2 else ''
            send('rsp=$wr')
            if hnd == 0x13:
                if value == '0100':
                    notifying.set()
                else:
                    notifying.clear()
            elif hnd == 0x15 and value == 'FF':
                threading.Thread(target=remote_disconnect, daemon=True).start()
        elif cmd == 'le':
            send('rsp=$mgmt', 'code=$success')
        elif cmd in ('scan', 'pasv'):
            if iface != '1':
                send('rsp=$mgmt', 'code=$mgmterr', 'estat=hF', "emsg='Not Powered")
                continue
            send('rsp=$mgmt', 'code=$success')
            state = 'scan'
            for result in SCAN_RESULTS:
                send('rsp=$scan', *result)
        elif cmd in ('scanend', 'pasvend'):
            send('rsp=$mgmt', 'code=$success')
            state = 'disc'
            status()
        else:
            send('rsp=$err', 'code=$badcmd')


if __name__ == '__main__':
    main()
