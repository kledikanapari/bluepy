"""
Test timeouts, notifications, threads, logging and scan helpers in `btle.py`,
using tests/fake_helper.py instead of bluepy-helper

Run with:
    $ python -m unittest discover -s tests
"""

import contextlib
import io
import logging
import threading
import time
import unittest

from bluepy import btle
from bluepy.btle import (Peripheral, Scanner, ScanEntry, DefaultDelegate, UUID,
                         BTLEDisconnectError, BTLEGattError, BTLETimeoutError)

from test_peripheral import FakeHelperTestCase, ADDR_A

LEVEL_HANDLE = 0x12       # Battery Level value handle in the fake device
OTHER_HANDLE = 0x15       # characteristic without descriptors
NO_REPLY_HANDLE = 0xFFFF


class Recorder(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
        self.received = []

    def handleNotification(self, cHandle, data):
        self.received.append((cHandle, data))


class PeripheralTestCase(FakeHelperTestCase):
    def setUp(self):
        FakeHelperTestCase.setUp(self)
        self.p = Peripheral(ADDR_A)

    def tearDown(self):
        self.p.disconnect()
        FakeHelperTestCase.tearDown(self)

    def battery_level(self):
        svc = self.p.getServiceByUUID(0x180F)
        return svc.getCharacteristics(0x2A19)[0]

    def wait_for(self, condition, timeout=5):
        deadline = time.monotonic() + timeout
        while not condition():
            self.assertLess(time.monotonic(), deadline, "condition not met in time")
            self.p.waitForNotifications(0.1)


class TestTimeouts(PeripheralTestCase):
    def test_default_timeout(self):
        self.p.responseTimeout = 0.3
        start = time.monotonic()
        with self.assertRaises(BTLETimeoutError):
            self.p.readCharacteristic(NO_REPLY_HANDLE)
        self.assertLess(time.monotonic() - start, 3)
        # A late reply must not be taken for the reply to a later command
        self.assertIsNone(self.p._helper)

    def test_timeout_argument(self):
        with self.assertRaises(BTLETimeoutError):
            self.p.readCharacteristic(NO_REPLY_HANDLE, timeout=0.3)

    def test_timeout_is_a_disconnect_error(self):
        # Existing code catching BTLEDisconnectError keeps working
        with self.assertRaises(BTLEDisconnectError):
            self.p.readCharacteristic(NO_REPLY_HANDLE, timeout=0.3)

    def test_constructor_argument(self):
        p = Peripheral(ADDR_A, responseTimeout=0.3)
        with self.assertRaises(BTLETimeoutError):
            p.readCharacteristic(NO_REPLY_HANDLE)

    def test_replies_in_time(self):
        self.p.responseTimeout = 2
        self.assertEqual(self.p.readCharacteristic(LEVEL_HANDLE), b'\x2a')
        self.assertEqual(self.battery_level().read(timeout=2), b'\x2a')


class TestNotifications(PeripheralTestCase):
    def test_enable_with_callback(self):
        got = []
        ch = self.battery_level()
        ch.enableNotifications(lambda c, data: got.append((c, data)))
        self.wait_for(lambda: len(got) >= 3)
        self.assertIs(got[0][0], ch)
        self.assertEqual([d for (c, d) in got[:3]], [b'\x01', b'\x02', b'\x03'])

        ch.disableNotifications()
        time.sleep(0.1)
        self.p.waitForNotifications(0.1)          # deliver what was in flight
        n = len(got)
        self.assertFalse(self.p.waitForNotifications(0.2))
        self.assertEqual(len(got), n)

    def test_enable_without_callback_uses_delegate(self):
        rec = Recorder()
        self.p.withDelegate(rec)
        self.battery_level().enableNotifications()
        self.wait_for(lambda: rec.received)
        self.assertEqual(rec.received[0], (LEVEL_HANDLE, b'\x01'))

    def test_delivered_during_other_commands(self):
        rec = Recorder()
        self.p.withDelegate(rec)
        self.battery_level().enableNotifications()
        deadline = time.monotonic() + 5
        while not rec.received:
            self.assertLess(time.monotonic(), deadline)
            self.p.readCharacteristic(OTHER_HANDLE)

    def test_not_supported(self):
        other = self.p.getServiceByUUID(0x180F).getCharacteristics(0x2A1A)[0]
        with self.assertRaises(BTLEGattError):
            other.enableNotifications()
        with self.assertRaises(BTLEGattError):
            self.battery_level().enableNotifications(indicate=True)

    def test_descriptors_limited_to_characteristic(self):
        chars = self.p.getServiceByUUID(0x180F).getCharacteristics()
        self.assertEqual([d.handle for d in chars[0].getDescriptors()], [0x13])
        # No room for descriptors: no request at all
        self.assertEqual(chars[1].getDescriptors(), [])
        # Empty range: "Attribute Not Found" means no descriptors
        self.assertEqual(self.p.getDescriptors(0x14, 0x15), [])

    def test_remote_disconnect_while_waiting(self):
        self.battery_level().enableNotifications(lambda c, data: None)
        self.p.writeCharacteristic(OTHER_HANDLE, b'\xff')   # device disconnects
        with self.assertRaises(BTLEDisconnectError):
            for _ in range(100):
                self.p.waitForNotifications(0.1)
        self.assertIsNone(self.p._helper)


class TestThreads(PeripheralTestCase):
    def test_wait_does_not_block_commands(self):
        errors = []
        waiting = threading.Event()

        def waiter():
            try:
                waiting.set()
                self.p.waitForNotifications(3)    # nothing comes: notifications are off
            except Exception as e:
                errors.append(e)

        t = threading.Thread(target=waiter)
        t.start()
        waiting.wait()
        time.sleep(0.1)
        start = time.monotonic()
        self.assertEqual(self.p.readCharacteristic(LEVEL_HANDLE), b'\x2a')
        self.assertLess(time.monotonic() - start, 1)
        t.join()
        self.assertEqual(errors, [])

    def test_commands_and_notifications_from_threads(self):
        got = []
        errors = []
        stop = threading.Event()
        self.battery_level().enableNotifications(lambda c, data: got.append(data[0]))

        def listener():
            try:
                while not stop.is_set():
                    self.p.waitForNotifications(0.5)
            except Exception as e:
                errors.append(e)

        def reader(handle, expected):
            try:
                for _ in range(30):
                    if self.p.readCharacteristic(handle) != expected:
                        errors.append("wrong value for handle %X" % handle)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=listener),
                   threading.Thread(target=reader, args=(LEVEL_HANDLE, b'\x2a')),
                   threading.Thread(target=reader, args=(OTHER_HANDLE, b'\x01'))]
        for t in threads:
            t.start()
        for t in threads[1:]:
            t.join()
        time.sleep(0.2)
        stop.set()
        threads[0].join()

        self.assertEqual(errors, [])
        self.assertGreater(len(got), 3)
        # Delivered in order, without gaps or repeats
        self.assertEqual(got, list(range(got[0], got[0] + len(got))))

    def test_disconnect_wakes_waiting_thread(self):
        errors = []

        def waiter():
            try:
                self.p.waitForNotifications(None)
            except BTLEDisconnectError as e:
                errors.append(e)

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.2)
        self.p.disconnect()
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertEqual(len(errors), 1)


class TestDelegateKept(FakeHelperTestCase):
    def test_reconnect_keeps_delegate(self):
        rec = Recorder()
        p = Peripheral(ADDR_A).withDelegate(rec)
        p.disconnect()
        self.assertIs(p.delegate, rec)
        p.connect(ADDR_A)
        try:
            p.getServiceByUUID(0x180F).getCharacteristics(0x2A19)[0].enableNotifications()
            deadline = time.monotonic() + 5
            while not rec.received:
                self.assertLess(time.monotonic(), deadline)
                p.waitForNotifications(0.1)
        finally:
            p.disconnect()


class TestLogging(FakeHelperTestCase):
    def test_debug_goes_to_logging(self):
        out = io.StringIO()
        with self.assertLogs('bluepy.btle', level=logging.DEBUG) as logs, \
             contextlib.redirect_stdout(out):
            p = Peripheral(ADDR_A)
            p.disconnect()
        self.assertTrue(any('Sent:' in m and 'conn' in m for m in logs.output))
        self.assertEqual(out.getvalue(), '')

    def test_debugging_flag_still_prints(self):
        out = io.StringIO()
        btle.Debugging = True
        try:
            with contextlib.redirect_stdout(out):
                Peripheral(ADDR_A).disconnect()
        finally:
            btle.Debugging = False
        self.assertIn('Sent:', out.getvalue())


def scan_entry(data, addrType=1, rssi=60, flag=0):
    dev = ScanEntry('aa:bb:cc:dd:ee:ff', 0)
    dev._update({'type': [addrType], 'rssi': [rssi], 'flag': [flag], 'd': [data]})
    return dev


class TestScanEntry(unittest.TestCase):
    def test_name(self):
        self.assertEqual(scan_entry(bytes.fromhex('0409466F6F')).getName(), 'Foo')
        self.assertEqual(scan_entry(bytes.fromhex('0408426172')).getName(), 'Bar')
        # The complete name wins over the short one
        self.assertEqual(scan_entry(bytes.fromhex('0408426172' '0409466F6F')).getName(), 'Foo')
        self.assertIsNone(scan_entry(bytes.fromhex('020106')).getName())

    def test_manufacturer_data(self):
        dev = scan_entry(bytes.fromhex('05FF4C000102'))
        self.assertEqual(dev.getManufacturerData(), (0x004C, b'\x01\x02'))
        self.assertIsNone(scan_entry(b'').getManufacturerData())

    def test_service_data_and_uuids(self):
        # 16-bit service data for 0x181A, 16-bit service list 0x180F, 0x181A
        dev = scan_entry(bytes.fromhex('05161A18AABB' '05030F181A18'))
        self.assertEqual(dev.getServiceData(), {UUID(0x181A): b'\xaa\xbb'})
        self.assertEqual(dev.getServiceUUIDs(), [UUID(0x180F), UUID(0x181A)])

    def test_matches(self):
        dev = scan_entry(bytes.fromhex('0409466F6F' '03030F18'), rssi=60)
        self.assertTrue(dev.matches())
        self.assertTrue(dev.matches(name='Foo', serviceUUID=0x180F, minRSSI=-70, connectable=True))
        self.assertFalse(dev.matches(name='Bar'))
        self.assertFalse(dev.matches(serviceUUID=0x181A))
        self.assertFalse(dev.matches(minRSSI=-50))
        self.assertFalse(dev.matches(connectable=False))


class TestScanner(FakeHelperTestCase):
    def test_scan_with_filters(self):
        scanner = Scanner(1)
        found = scanner.scan(0.5)
        self.assertEqual(sorted(d.addr for d in found), ['aa:bb:cc:dd:ee:01', 'aa:bb:cc:dd:ee:02'])
        self.assertEqual([d.addr for d in scanner.getDevices(name='Foo')], ['aa:bb:cc:dd:ee:01'])
        self.assertEqual([d.addr for d in scanner.getDevices(connectable=False)], ['aa:bb:cc:dd:ee:02'])
        self.assertEqual([d.getManufacturerData() for d in Scanner(1).scan(0.5, name='Bar')],
                         [(0x004C, b'\x01\x02')])

    def test_context_manager_stops_scanning(self):
        with self.assertRaises(RuntimeError):
            with Scanner(1) as scanner:
                scanner.start()
                scanner.process(0.2)
                raise RuntimeError("stop")
        self.assertIsNone(scanner._helper)


if __name__ == "__main__":
    unittest.main()
