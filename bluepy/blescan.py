#!/usr/bin/env python3
import argparse
import binascii
import struct
import os
import sys
from bluepy import btle

if os.getenv('C', '1') == '0':
    ANSI_RED = ''
    ANSI_GREEN = ''
    ANSI_YELLOW = ''
    ANSI_CYAN = ''
    ANSI_WHITE = ''
    ANSI_OFF = ''
else:
    ANSI_CSI = "\033["
    ANSI_RED = ANSI_CSI + '31m'
    ANSI_GREEN = ANSI_CSI + '32m'
    ANSI_YELLOW = ANSI_CSI + '33m'
    ANSI_CYAN = ANSI_CSI + '36m'
    ANSI_WHITE = ANSI_CSI + '37m'
    ANSI_OFF = ANSI_CSI + '0m'


def dump_services(dev):
    services = sorted(dev.services, key=lambda s: s.hndStart)
    for s in services:
        print ("\t%04x: %s" % (s.hndStart, s))
        if s.hndStart == s.hndEnd:
            continue
        chars = s.getCharacteristics()
        for i, c in enumerate(chars):
            props = c.propertiesToString()
            h = c.getHandle()
            if 'READ' in props:
                val = c.read()
                if c.uuid == btle.AssignedNumbers.device_name:
                    string = ANSI_CYAN + '\'' + \
                        val.decode('utf-8') + '\'' + ANSI_OFF
                elif c.uuid == btle.AssignedNumbers.device_information:
                    string = repr(val)
                else:
                    string = '<s' + binascii.b2a_hex(val).decode('utf-8') + '>'
            else:
                string = ''
            print ("\t%04x:    %-59s %-12s %s" % (h, c, props, string))

            while True:
                h += 1
                if h > s.hndEnd or (i < len(chars) - 1 and h >= chars[i + 1].getHandle() - 1):
                    break
                try:
                    val = dev.readCharacteristic(h)
                    print ("\t%04x:     <%s>" %
                           (h, binascii.b2a_hex(val).decode('utf-8')))
                except btle.BTLEException:
                    break


_FLAG_NAMES = [(0x01, 'LE Limited Discoverable'), (0x02, 'LE General Discoverable'),
               (0x04, 'BR/EDR Not Supported'), (0x08, 'LE + BR/EDR (controller)'),
               (0x10, 'LE + BR/EDR (host)')]

_DECODED = {btle.ScanEntry.FLAGS, btle.ScanEntry.SHORT_LOCAL_NAME, btle.ScanEntry.COMPLETE_LOCAL_NAME,
            btle.ScanEntry.TX_POWER, btle.ScanEntry.APPEARANCE, btle.ScanEntry.MANUFACTURER,
            btle.ScanEntry.SERVICE_DATA_16B, btle.ScanEntry.SERVICE_DATA_32B, btle.ScanEntry.SERVICE_DATA_128B,
            btle.ScanEntry.INCOMPLETE_16B_SERVICES, btle.ScanEntry.COMPLETE_16B_SERVICES,
            btle.ScanEntry.INCOMPLETE_32B_SERVICES, btle.ScanEntry.COMPLETE_32B_SERVICES,
            btle.ScanEntry.INCOMPLETE_128B_SERVICES, btle.ScanEntry.COMPLETE_128B_SERVICES}


def _hex(data):
    return binascii.b2a_hex(data).decode('ascii')


def _uuid_text(uuid):
    name = uuid.getCommonName()
    return name if name == str(uuid) else '%s (%s)' % (name, uuid)


def describe_device(dev):
    """Returns the lines describing everything known about a ScanEntry"""
    lines = ['Address: %s (%s)' % (dev.addr, dev.addrType),
             'RSSI: %d dBm' % dev.rssi,
             'Connectable: %s' % ('yes' if dev.connectable else 'no'),
             'Advertisements received: %d' % dev.updateCount]
    name = dev.getName()
    if name is not None:
        lines.append('Name: %s' % name)
    flags = dev.scanData.get(btle.ScanEntry.FLAGS)
    if flags:
        lines.append('Flags: 0x%02x %s' % (flags[0], ', '.join(n for (bit, n) in _FLAG_NAMES if flags[0] & bit)))
    tx = dev.scanData.get(btle.ScanEntry.TX_POWER)
    if tx:
        lines.append('Tx power: %d dBm' % struct.unpack('<b', tx[:1])[0])
    appearance = dev.scanData.get(btle.ScanEntry.APPEARANCE)
    if appearance and len(appearance) >= 2:
        lines.append('Appearance: 0x%04x' % struct.unpack('<H', appearance[:2])[0])
    manufacturer = dev.getManufacturerData()
    if manufacturer is not None:
        lines.append('Manufacturer: company 0x%04x, data %s' % (manufacturer[0], _hex(manufacturer[1]) or '(none)'))
    for uuid in dev.getServiceUUIDs():
        lines.append('Service: %s' % _uuid_text(uuid))
    for (uuid, data) in dev.getServiceData().items():
        lines.append('Service data: %s = %s' % (_uuid_text(uuid), _hex(data) or '(none)'))
    # Anything else, undecoded
    for (sdid, desc, val) in dev.getScanData():
        if sdid not in _DECODED:
            lines.append('%s: <%s>' % (desc, val))
    if dev.rawData:
        lines.append('Raw advertising data: %s' % _hex(dev.rawData))
    return lines


class ScanPrint(btle.DefaultDelegate):

    def __init__(self, opts):
        btle.DefaultDelegate.__init__(self)
        self.opts = opts

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            status = "new"
        elif isNewData:
            if self.opts.new:
                return
            status = "update"
        else:
            if not self.opts.all:
                return
            status = "old"

        if dev.rssi < self.opts.sensitivity:
            return

        print ('    Device (%s): %s' % (status, ANSI_WHITE + dev.addr + ANSI_OFF))
        for line in describe_device(dev):
            print ('\t' + line)
        print()
        sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--hci', action='store', type=int, default=0,
                        help='Interface number for scan')
    parser.add_argument('-t', '--timeout', action='store', type=int, default=4,
                        help='Scan delay, 0 for continuous')
    parser.add_argument('-s', '--sensitivity', action='store', type=int, default=-128,
                        help='dBm value for filtering far devices')
    parser.add_argument('-d', '--discover', action='store_true',
                        help='Connect and discover service to scanned devices')
    parser.add_argument('-a', '--all', action='store_true',
                        help='Display duplicate adv responses, by default show new + updated')
    parser.add_argument('-n', '--new', action='store_true',
                        help='Display only new adv responses, by default show new + updated')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Increase output verbosity')
    arg = parser.parse_args(sys.argv[1:])

    btle.Debugging = arg.verbose

    scanner = btle.Scanner(arg.hci).withDelegate(ScanPrint(arg))

    print (ANSI_RED + "Scanning for devices..." + ANSI_OFF)
    devices = scanner.scan(arg.timeout)

    if arg.discover:
        print (ANSI_RED + "Discovering services..." + ANSI_OFF)

        for d in devices:
            if not d.connectable or d.rssi < arg.sensitivity:

                continue

            print ("    Connecting to", ANSI_WHITE + d.addr + ANSI_OFF + ":")

            dev = btle.Peripheral(d)
            dump_services(dev)
            dev.disconnect()
            print()

if __name__ == "__main__":
    main()
