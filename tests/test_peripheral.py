"""
Test Peripheral / Scanner handling of device addresses and of the helper
process in `btle.py`, using tests/fake_helper.py instead of bluepy-helper

Run with:
    $ python -m unittest discover -s tests
"""

import os
import shutil
import stat
import sys
import tempfile
import unittest

from bluepy import btle
from bluepy.btle import (Peripheral, Scanner, ScanEntry, BluepyHelper,
                         BTLEDisconnectError, BTLEManagementError)

FAKE_HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fake_helper.py')

ADDR_A = 'AA:BB:CC:DD:EE:01'
ADDR_B = 'AA:BB:CC:DD:EE:02'
NEVER_CONNECTS = '11:11:11:11:11:11'
FAILS = '22:22:22:22:22:22'
NEVER_ANSWERS = '33:33:33:33:33:33'


class TestMACAddressCheck(unittest.TestCase):
    def test_good_addresses(self):
        self.assertEqual(btle._checkMACAddress('AA:BB:CC:DD:EE:FF'), 'AA:BB:CC:DD:EE:FF')
        self.assertEqual(btle._checkMACAddress('aa:bb:cc:dd:ee:ff'), 'aa:bb:cc:dd:ee:ff')
        self.assertEqual(btle._checkMACAddress(' AA:BB:CC:DD:EE:FF\n'), 'AA:BB:CC:DD:EE:FF')
        self.assertEqual(btle._checkMACAddress(b'AA:BB:CC:DD:EE:FF'), 'AA:BB:CC:DD:EE:FF')

    def test_bad_addresses(self):
        # All of these used to reach bluepy-helper, which then connected
        # to 00:00:00:00:00:00
        for addr in ['AA:BB:CC:DD:EE:F', 'AA:BB:CC:DD:EE:FG', 'a:b:c:d:e:f',
                     "b'AA:BB:CC:DD:EE:FF'", 'AA:BB:CC:DD:EE:FF:00',
                     'AA-BB-CC-DD-EE-FF', '00:00:00:00:00:00', '', None, 42]:
            with self.assertRaises(ValueError, msg=repr(addr)):
                btle._checkMACAddress(addr)


class TestParseResp(unittest.TestCase):
    def test_value_containing_equals(self):
        resp = BluepyHelper.parseResp("rsp=$err\x1ecode=$connfail\x1eemsg='a=b\n")
        self.assertEqual(resp['emsg'], ['a=b'])


class TestScanEntry(unittest.TestCase):
    def test_address_type_change_does_not_abort(self):
        dev = ScanEntry('aa:bb:cc:dd:ee:ff', 0)
        dev._update({'type': [1], 'rssi': [60], 'flag': [0], 'd': [b'']})
        self.assertEqual(dev.addrType, btle.ADDR_TYPE_PUBLIC)
        dev._update({'type': [2], 'rssi': [60], 'flag': [0], 'd': [b'']})
        self.assertEqual(dev.addrType, btle.ADDR_TYPE_RANDOM)
        # An unknown type keeps the last known one
        dev._update({'type': [0], 'rssi': [60], 'flag': [0], 'd': [b'']})
        self.assertEqual(dev.addrType, btle.ADDR_TYPE_RANDOM)

    def test_connectable_flag(self):
        dev = ScanEntry('aa:bb:cc:dd:ee:ff', 0)
        dev._update({'type': [1], 'rssi': [60], 'flag': [0x4], 'd': [b'']})
        self.assertFalse(dev.connectable)
        dev._update({'type': [1], 'rssi': [60], 'flag': [0x20], 'd': [b'']})
        self.assertTrue(dev.connectable)


class FakeHelperTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        wrapper = os.path.join(self.tmpdir, 'bluepy-helper')
        with open(wrapper, 'w') as f:
            f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, FAKE_HELPER))
        os.chmod(wrapper, os.stat(wrapper).st_mode | stat.S_IXUSR)
        self.log = os.path.join(self.tmpdir, 'commands.log')
        os.environ['FAKE_HELPER_LOG'] = self.log
        self.saved_helper = btle.helperExe
        btle.helperExe = wrapper

    def tearDown(self):
        btle.helperExe = self.saved_helper
        del os.environ['FAKE_HELPER_LOG']
        shutil.rmtree(self.tmpdir)

    def helper_pids(self):
        with open(self.log) as f:
            return set(line.split()[0] for line in f)


class TestPeripheralConnect(FakeHelperTestCase):
    def test_invalid_address_never_reaches_helper(self):
        with self.assertRaises(ValueError):
            Peripheral("b'AA:BB:CC:DD:EE:FF'")
        self.assertFalse(os.path.exists(self.log))

    def test_connect_sets_addr(self):
        p = Peripheral(' %s\n' % ADDR_A)
        try:
            self.assertEqual(p.addr, ADDR_A)
            self.assertEqual(p.deviceAddr, ADDR_A)
            self.assertEqual(p.status()['dst'], [ADDR_A])
        finally:
            p.disconnect()

    def test_connect_after_timeout_uses_new_address(self):
        for first_addr in [NEVER_CONNECTS, NEVER_ANSWERS]:
            # Without a reply to 'conn' within the timeout, the helper used to
            # be left running in 'tryconn', and it then silently ignored the
            # next 'conn': the address never changed
            if os.path.exists(self.log):
                os.remove(self.log)
            p = Peripheral()
            with self.assertRaises(BTLEDisconnectError):
                p.connect(first_addr, timeout=0.5)
            self.assertIsNone(p._helper)
            p.connect(ADDR_A, timeout=5)
            try:
                self.assertEqual(p.addr, ADDR_A)
                self.assertEqual(p.status()['dst'], [ADDR_A])
                self.assertEqual(len(self.helper_pids()), 2)
            finally:
                p.disconnect()

    def test_reconnect_to_other_device(self):
        p = Peripheral(ADDR_A)
        try:
            self.assertEqual(len(list(p.services)), 1)
            p.connect(ADDR_B, timeout=5)
            self.assertEqual(p.addr, ADDR_B)
            self.assertEqual(p.status()['dst'], [ADDR_B])
            # Services of the previous device must not be reused
            self.assertIsNone(p._serviceMap)
        finally:
            p.disconnect()

    def test_connection_failure_reports_reason(self):
        with self.assertRaises(BTLEDisconnectError) as cm:
            Peripheral(FAILS)
        self.assertIn('Connection refused', str(cm.exception))

    def test_disconnect_after_helper_died(self):
        p = Peripheral(ADDR_A)
        p._helper.kill()
        p._helper.wait()
        p.disconnect()                    # must not raise
        self.assertIsNone(p._helper)


class TestScannerStart(FakeHelperTestCase):
    def test_scan_failure_raises(self):
        s = Scanner(0)
        with self.assertRaises(BTLEManagementError) as cm:
            s.start()
        self.assertIn('Not Powered', str(cm.exception))
        self.assertIsNone(s._helper)


if __name__ == "__main__":
    unittest.main()
