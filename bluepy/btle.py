#!/usr/bin/env python3

"""Bluetooth Low Energy Python interface"""
import sys
import os
import re
import time
import logging
import subprocess
import binascii
import struct
import signal
import threading
from queue import Queue, Empty

def preexec_function():
    # Ignore the SIGINT signal by setting the handler to the standard
    # signal handler SIG_IGN.
    signal.signal(signal.SIGINT, signal.SIG_IGN)

log = logging.getLogger(__name__)

# Deprecated: prints debug output on stdout. Use the logging module instead,
# e.g. logging.getLogger('bluepy.btle').setLevel(logging.DEBUG)
Debugging = False

script_path = os.path.join(os.path.abspath(os.path.dirname(__file__)))
helperExe = os.path.join(script_path, "bluepy-helper")

SEC_LEVEL_LOW = "low"
SEC_LEVEL_MEDIUM = "medium"
SEC_LEVEL_HIGH = "high"

ADDR_TYPE_PUBLIC = "public"
ADDR_TYPE_RANDOM = "random"

def DBG(*args):
    if Debugging:
        print(" ".join([str(a) for a in args]))
    elif log.isEnabledFor(logging.DEBUG):
        log.debug(" ".join([str(a) for a in args]))

# Default for BluepyHelper.responseTimeout, in seconds (None: wait for ever).
# It is longer than the 30 s ATT transaction timeout, after which BlueZ itself
# drops the connection to an unresponsive device.
DEFAULT_RESPONSE_TIMEOUT = 60.0

class _DefaultTimeout:
    def __repr__(self):
        return 'DEFAULT'

# As a timeout argument: use the object's responseTimeout
_DEFAULT_TIMEOUT = _DefaultTimeout()

_MAC_ADDR_RE = re.compile(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\Z')

def _checkMACAddress(addr):
    '''Returns addr without surrounding whitespace, or raises ValueError if it
       is not of the form XX:XX:XX:XX:XX:XX. bluepy-helper silently turns any
       malformed address into 00:00:00:00:00:00, so it must be checked here.'''
    try:
        if isinstance(addr, bytes):
            addr = addr.decode('ascii')
        addr = addr.strip()
    except (AttributeError, UnicodeDecodeError):
        raise ValueError("Expected MAC address, got %s" % repr(addr))
    if not _MAC_ADDR_RE.match(addr):
        raise ValueError("Expected MAC address, got %s" % repr(addr))
    if addr == "00:00:00:00:00:00":
        raise ValueError("00:00:00:00:00:00 is not a valid device address")
    return addr


class BTLEException(Exception):
    """Base class for all Bluepy exceptions"""
    def __init__(self, message, resp_dict=None):
        self.message = message

        # optional messages from bluepy-helper
        self.estat = None
        self.emsg = None
        if resp_dict:
            self.estat = resp_dict.get('estat',None)
            if isinstance(self.estat,list):
                self.estat = self.estat[0]
            self.emsg = resp_dict.get('emsg',None)
            if isinstance(self.emsg,list):
                self.emsg = self.emsg[0]


    def __str__(self):
        msg = self.message
        if self.estat or self.emsg:
            msg = msg + " ("
            if self.estat:
                msg = msg + "code: %s" % self.estat
            if self.estat and self.emsg:
                msg = msg + ", "
            if self.emsg:
                msg = msg + "error: %s" % self.emsg
            msg = msg + ")"

        return msg

class BTLEInternalError(BTLEException):
    def __init__(self, message, rsp=None):
        BTLEException.__init__(self, message, rsp)

class BTLEDisconnectError(BTLEException):
    def __init__(self, message, rsp=None):
        BTLEException.__init__(self, message, rsp)

class BTLEManagementError(BTLEException):
    def __init__(self, message, rsp=None):
        BTLEException.__init__(self, message, rsp)

class BTLEGattError(BTLEException):
    def __init__(self, message, rsp=None):
        BTLEException.__init__(self, message, rsp)

class BTLETimeoutError(BTLEDisconnectError):
    """No reply in time. The connection has been closed: a late reply could
       otherwise be taken for the reply to a later command."""
    def __init__(self, message, rsp=None):
        BTLEDisconnectError.__init__(self, message, rsp)



class UUID:
    def __init__(self, val, commonName=None):
        '''We accept: 32-digit hex strings, with and without '-' characters,
           4 to 8 digit hex strings, and integers'''
        if isinstance(val, int):
            if (val < 0) or (val > 0xFFFFFFFF):
                raise ValueError(
                    "Short form UUIDs must be in range 0..0xFFFFFFFF")
            val = "%04X" % val
        elif isinstance(val, self.__class__):
            val = str(val)
        else:
            val = str(val)  # Do our best

        val = val.replace("-", "")
        if len(val) <= 8:  # Short form
            val = ("0" * (8 - len(val))) + val + "00001000800000805F9B34FB"

        self.binVal = binascii.a2b_hex(val.encode('utf-8'))
        if len(self.binVal) != 16:
            raise ValueError(
                "UUID must be 16 bytes, got '%s' (len=%d)" % (val,
                                                              len(self.binVal)))
        self.commonName = commonName

    def __str__(self):
        s = binascii.b2a_hex(self.binVal).decode('utf-8')
        return "-".join([s[0:8], s[8:12], s[12:16], s[16:20], s[20:32]])

    def __eq__(self, other):
        return self.binVal == UUID(other).binVal

    def __hash__(self):
        return hash(self.binVal)

    def getCommonName(self):
        s = AssignedNumbers.getCommonName(self)
        if s:
            return s
        s = str(self)
        if s.endswith("-0000-1000-8000-00805f9b34fb"):
            s = s[0:8]
            if s.startswith("0000"):
                s = s[4:]
        return s

ATT_ECODE_ATTR_NOT_FOUND = 0x0A

class Service:
    def __init__(self, *args):
        (self.peripheral, uuidVal, self.hndStart, self.hndEnd) = args
        self.uuid = UUID(uuidVal)
        self.chars = None
        self.descs = None

    def getCharacteristics(self, forUUID=None, timeout=_DEFAULT_TIMEOUT):
        if not self.chars: # Unset, or empty
            self.chars = [] if self.hndEnd <= self.hndStart else self.peripheral.getCharacteristics(self.hndStart, self.hndEnd, timeout=timeout)
            # A characteristic's descriptors end where the next one starts
            for (ch, nextCh) in zip(self.chars, self.chars[1:]):
                ch._hndEnd = nextCh.handle - 1
            if self.chars:
                self.chars[-1]._hndEnd = self.hndEnd
        if forUUID is not None:
            u = UUID(forUUID)
            return [ch for ch in self.chars if ch.uuid==u]
        return self.chars

    def getDescriptors(self, forUUID=None, timeout=_DEFAULT_TIMEOUT):
        if not self.descs:
            # Grab all descriptors in our range, except for the service
            # declaration descriptor
            all_descs = self.peripheral.getDescriptors(self.hndStart+1, self.hndEnd, timeout=timeout)
            # Filter out the descriptors for the characteristic properties
            # Note that this does not filter out characteristic value descriptors
            self.descs = [desc for desc in all_descs if desc.uuid != 0x2803]
        if forUUID is not None:
            u = UUID(forUUID)
            return [desc for desc in self.descs if desc.uuid == u]
        return self.descs

    def __str__(self):
        return "Service <uuid=%s handleStart=%s handleEnd=%s>" % (self.uuid.getCommonName(),
                                                                 self.hndStart,
                                                                 self.hndEnd)

class Characteristic:
    # Currently only READ is used in supportsRead function,
    # the rest is included to facilitate supportsXXXX functions if required
    props = {"BROADCAST":    0b00000001,
             "READ":         0b00000010,
             "WRITE_NO_RESP":0b00000100,
             "WRITE":        0b00001000,
             "NOTIFY":       0b00010000,
             "INDICATE":     0b00100000,
             "WRITE_SIGNED": 0b01000000,
             "EXTENDED":     0b10000000,
    }

    propNames = {0b00000001 : "BROADCAST",
                 0b00000010 : "READ",
                 0b00000100 : "WRITE NO RESPONSE",
                 0b00001000 : "WRITE",
                 0b00010000 : "NOTIFY",
                 0b00100000 : "INDICATE",
                 0b01000000 : "WRITE SIGNED",
                 0b10000000 : "EXTENDED PROPERTIES",
    }

    CCCD_UUID = 0x2902   # Client Characteristic Configuration descriptor

    def __init__(self, *args):
        (self.peripheral, uuidVal, self.handle, self.properties, self.valHandle) = args
        self.uuid = UUID(uuidVal)
        self.descs = None
        # Last handle which can belong to this characteristic; known when it
        # was found through Service.getCharacteristics()
        self._hndEnd = 0xFFFF

    def read(self, timeout=_DEFAULT_TIMEOUT):
        return self.peripheral.readCharacteristic(self.valHandle, timeout=timeout)

    def write(self, val, withResponse=False, timeout=_DEFAULT_TIMEOUT):
        return self.peripheral.writeCharacteristic(self.valHandle, val, withResponse, timeout=timeout)

    def getDescriptors(self, forUUID=None, hndEnd=None, timeout=_DEFAULT_TIMEOUT):
        if not self.descs:
            # Descriptors (not counting the value descriptor) begin after
            # the handle for the value descriptor and stop when we reach
            # the handle for the next characteristic or service
            if hndEnd is None:
                hndEnd = self._hndEnd
            self.descs = []
            if self.valHandle < hndEnd:
                for desc in self.peripheral.getDescriptors(self.valHandle+1, hndEnd, timeout=timeout):
                    if desc.uuid in (0x2800, 0x2801, 0x2803):
                        # Stop if we reach another characteristic or service
                        break
                    self.descs.append(desc)
        if forUUID is not None:
            u = UUID(forUUID)
            return [desc for desc in self.descs if desc.uuid == u]
        return self.descs

    def enableNotifications(self, callback=None, indicate=False, timeout=_DEFAULT_TIMEOUT):
        """Asks the device to send notifications (or, with indicate=True,
           indications) of this characteristic's value. With a callback, each
           one is passed to callback(characteristic, data); otherwise to the
           peripheral's delegate, as before. They are delivered while waiting
           in Peripheral.waitForNotifications() or for any other command."""
        kind = "INDICATE" if indicate else "NOTIFY"
        if not self.properties & Characteristic.props[kind]:
            raise BTLEGattError("%s does not support %s" %
                                (self, "indications" if indicate else "notifications"))
        cccd = self._getCCCD(timeout)
        # Register before enabling, not to miss the first notifications
        self.peripheral._setNotificationCallback(self, callback)
        try:
            cccd.write(struct.pack('<H', 0x0002 if indicate else 0x0001),
                       withResponse=True, timeout=timeout)
        except BTLEException:
            self.peripheral._setNotificationCallback(self, None)
            raise

    def disableNotifications(self, timeout=_DEFAULT_TIMEOUT):
        """Stops notifications and indications of this characteristic's value"""
        self._getCCCD(timeout).write(struct.pack('<H', 0x0000), withResponse=True,
                                     timeout=timeout)
        self.peripheral._setNotificationCallback(self, None)

    def _getCCCD(self, timeout):
        cccds = self.getDescriptors(forUUID=Characteristic.CCCD_UUID, timeout=timeout)
        if not cccds:
            raise BTLEGattError("%s has no Client Characteristic Configuration descriptor" % self)
        return cccds[0]

    def __str__(self):
        return "Characteristic <%s>" % self.uuid.getCommonName()

    def supportsRead(self):
        if (self.properties & Characteristic.props["READ"]):
            return True
        else:
            return False

    def propertiesToString(self):
        propStr = ""
        for p in Characteristic.propNames:
           if (p & self.properties):
               propStr += Characteristic.propNames[p] + " "
        return propStr

    def getHandle(self):
        return self.valHandle

class Descriptor:
    def __init__(self, *args):
        (self.peripheral, uuidVal, self.handle) = args
        self.uuid = UUID(uuidVal)

    def __str__(self):
        return "Descriptor <%s>" % self.uuid.getCommonName()


    def read(self, timeout=_DEFAULT_TIMEOUT):
        return self.peripheral.readCharacteristic(self.handle, timeout=timeout)

    def write(self, val, withResponse=False, timeout=_DEFAULT_TIMEOUT):
        return self.peripheral.writeCharacteristic(self.handle, val, withResponse, timeout=timeout)

class DefaultDelegate:
    def __init__(self):
        pass

    def handleNotification(self, cHandle, data):
        DBG("Notification:", cHandle, "sent data", binascii.b2a_hex(data))

    def handleDiscovery(self, scanEntry, isNewDev, isNewData):
        DBG("Discovered device", scanEntry.addr)

_NOTIFICATION_PREFIXES = ('rsp=$ntfy\x1e', 'rsp=$ind\x1e')
_MTU_RE = re.compile('\x1emtu=h([0-9A-Fa-f]+)')
_HELPER_EXITED = 'exited'

class _HelperLink:
    """What we share with the thread reading one bluepy-helper's output. That
       thread doesn't hold on to the BluepyHelper itself, so that a dropped
       Peripheral is still garbage collected (and disconnects)."""
    def __init__(self, process, routeNotifications):
        self.process = process
        self.lines = Queue()      # replies and status; None once the helper exited
        # Notifications and indications, kept apart so that waiting for them
        # doesn't hold up commands from other threads. None wakes up waiters
        # when 'closed' gets set.
        self.notifications = Queue() if routeNotifications else None
        self.mtu = 0
        self.closed = None        # the 'disc' status line, or _HELPER_EXITED

class BluepyHelper:
    _routeNotifications = False

    def __init__(self):
        self._helper = None
        self._link = None
        self._stderr = None
        self._lock = threading.RLock()        # one command at a time
        self.responseTimeout = DEFAULT_RESPONSE_TIMEOUT
        self.delegate = DefaultDelegate()

    def withDelegate(self, delegate_):
        self.delegate = delegate_
        return self

    def _timeoutValue(self, timeout):
        return self.responseTimeout if timeout is _DEFAULT_TIMEOUT else timeout

    def _startHelper(self,iface=None):
        if self._helper is None:
            DBG("Running ", helperExe)
            self._stderr = open(os.devnull, "w")
            args=[helperExe]
            if iface is not None: args.append(str(iface))
            self._helper = subprocess.Popen(args,
                                            stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE,
                                            stderr=self._stderr,
                                            universal_newlines=True,
                                            preexec_fn = preexec_function)
            self._link = _HelperLink(self._helper, self._routeNotifications)
            t = threading.Thread(target=self._readToQueue, args=(self._link,))
            t.daemon = True               # don't wait for it to exit
            t.start()

    @staticmethod
    def _readToQueue(link):
        """Thread to read lines from stdout and insert in queue."""
        while True:
            line = link.process.stdout.readline()
            if not line:                  # EOF
                break
            if link.notifications is not None and line.startswith(_NOTIFICATION_PREFIXES):
                link.notifications.put(line)
                continue
            if line.startswith('rsp=$stat\x1e'):
                m = _MTU_RE.search(line)
                if m:
                    link.mtu = int(m.group(1), 16)
                if '\x1estate=$disc' in line and link.notifications is not None:
                    link.closed = line
                    link.notifications.put(None)
            link.lines.put(line)
        link.process.stdout.close()
        if link.closed is None:
            link.closed = _HELPER_EXITED
        link.lines.put(None)
        if link.notifications is not None:
            link.notifications.put(None)

    def _stopHelper(self):
        if self._helper is not None:
            DBG("Stopping ", helperExe)
            try:
                self._helper.stdin.write("quit\n")
                self._helper.stdin.flush()
            except (OSError, ValueError):
                pass                      # helper has already exited
            try:
                self._helper.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._helper.kill()
                self._helper.wait()
            try:
                self._helper.stdin.close()
            except OSError:
                pass
            self._helper = None
            self._link = None
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None

    def _writeCmd(self, cmd):
        if self._helper is None:
            raise BTLEInternalError("Helper not started (did you call connect()?)")
        DBG("Sent: ", cmd)
        try:
            self._helper.stdin.write(cmd)
            self._helper.stdin.flush()
        except (OSError, ValueError):
            self._stopHelper()
            raise BTLEInternalError("Helper exited")

    def _command(self, cmd, wantType, timeout=_DEFAULT_TIMEOUT):
        """Sends cmd to bluepy-helper and returns its reply"""
        timeout = self._timeoutValue(timeout)
        with self._lock:
            self._writeCmd(cmd + "\n")
            resp = self._getResp(wantType, timeout)
            if resp is None:
                self._stopHelper()
                raise BTLETimeoutError("No reply to '%s' within %s seconds; disconnected"
                                       % (cmd.split()[0], timeout))
            return resp

    def _mgmtCmd(self, cmd, timeout=_DEFAULT_TIMEOUT):
        rsp = self._command(cmd, 'mgmt', timeout)
        if rsp['code'][0] != 'success':
            self._stopHelper()
            raise BTLEManagementError("Failed to execute management command '%s'" % (cmd), rsp)

    @staticmethod
    def parseResp(line):
        resp = {}
        for item in line.rstrip().split('\x1e'):
            (tag, tval) = item.split('=', 1)
            if len(tval)==0:
                val = None
            elif tval[0]=="$" or tval[0]=="'":
                # Both symbols and strings as Python strings
                val = tval[1:]
            elif tval[0]=="h":
                val = int(tval[1:], 16)
            elif tval[0]=='b':
                val = binascii.a2b_hex(tval[1:].encode('utf-8'))
            else:
                raise BTLEInternalError("Cannot understand response value %s" % repr(tval))
            if tag not in resp:
                resp[tag] = [val]
            else:
                resp[tag].append(val)
        return resp

    def _getResp(self, wantType, timeout=None):
        return self._waitResp(wantType, timeout)

    def _waitResp(self, wantType, timeout=None):
        if isinstance(wantType, str):
            wantType = [wantType]
        # The timeout is for the whole wait, however many lines are skipped
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            link = self._link
            if link is None:
                raise BTLEInternalError("Helper not started (did you call connect()?)")
            remain = None if deadline is None else max(0.0, deadline - time.monotonic())
            try:
                rv = link.lines.get(timeout=remain)
            except Empty:
                DBG("Select timeout")
                return None

            if rv is None:                # helper's output closed
                self._stopHelper()
                raise BTLEInternalError("Helper exited")
            DBG("Got:", repr(rv))
            if rv.startswith('#') or rv == '\n' or len(rv)==0:
                continue

            resp = BluepyHelper.parseResp(rv)
            if 'rsp' not in resp:
                raise BTLEInternalError("No response type indicator", resp)

            respType = resp['rsp'][0]
            if respType in wantType:
                return resp
            elif respType == 'stat':
                if 'state' in resp and len(resp['state']) > 0 and resp['state'][0] == 'disc':
                    self._stopHelper()
                    raise BTLEDisconnectError("Device disconnected", resp)
            elif respType == 'err':
                errcode=resp['code'][0]
                if errcode=='nomgmt':
                    raise BTLEManagementError("Management not available (permissions problem?)", resp)
                elif errcode=='atterr':
                    raise BTLEGattError("Bluetooth command failed", resp)
                else:
                    raise BTLEException("Error from bluepy-helper (%s)" % errcode, resp)
            elif respType == 'scan':
                # Scan response when we weren't interested. Ignore it
                continue
            else:
                raise BTLEInternalError("Unexpected response (%s)" % respType, resp)

    def status(self, timeout=_DEFAULT_TIMEOUT):
        return self._command("stat", 'stat', timeout)


class Peripheral(BluepyHelper):
    """A connection to a Bluetooth LE device. Its methods can be called from
       several threads; commands are then sent one at a time."""

    _routeNotifications = True

    def __init__(self, deviceAddr=None, addrType=ADDR_TYPE_PUBLIC, iface=None,
                 timeout=_DEFAULT_TIMEOUT, responseTimeout=_DEFAULT_TIMEOUT):
        BluepyHelper.__init__(self)
        if responseTimeout is not _DEFAULT_TIMEOUT:
            self.responseTimeout = responseTimeout
        self._serviceMap = None # Indexed by UUID
        self._notifyCallbacks = {} # Indexed by value handle
        # Held while notifications are delivered, so that they are delivered
        # in order, by one thread at a time
        self._dispatchLock = threading.RLock()
        # deviceAddr is kept as an alias of addr for backwards compatibility
        (self.addr, self.deviceAddr, self.addrType, self.iface) = (None, None, None, None)

        if isinstance(deviceAddr, ScanEntry):
            self._connect(deviceAddr.addr, deviceAddr.addrType, deviceAddr.iface, timeout)
        elif deviceAddr is not None:
            self._connect(deviceAddr, addrType, iface, timeout)

    def setDelegate(self, delegate_): # same as withDelegate(), deprecated
        return self.withDelegate(delegate_)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.disconnect()

    def _getResp(self, wantType, timeout=None):
        resp = self._waitResp(wantType, timeout)
        self._deliverNotifications()
        return resp

    def _setNotificationCallback(self, characteristic, callback):
        if callback is None:
            self._notifyCallbacks.pop(characteristic.valHandle, None)
        else:
            self._notifyCallbacks[characteristic.valHandle] = (characteristic, callback)

    def _deliverNotification(self, line):
        DBG("Got:", repr(line))
        resp = self.parseResp(line)
        hnd = resp['hnd'][0]
        data = resp['d'][0]
        entry = self._notifyCallbacks.get(hnd)
        if entry is not None:
            entry[1](entry[0], data)
        elif self.delegate is not None:
            self.delegate.handleNotification(hnd, data)

    def _deliverNotifications(self):
        """Delivers the notifications received so far, unless another thread
           is waiting for them in waitForNotifications()"""
        link = self._link
        if link is None or not self._dispatchLock.acquire(blocking=False):
            return
        try:
            while True:
                try:
                    line = link.notifications.get_nowait()
                except Empty:
                    return
                # None only wakes up waitForNotifications(); link.closed stays set
                if line is not None:
                    self._deliverNotification(line)
        finally:
            self._dispatchLock.release()

    def _linkClosed(self, link):
        with self._lock:
            if self._link is link:
                self._stopHelper()
        if link.closed == _HELPER_EXITED:
            raise BTLEInternalError("Helper exited")
        raise BTLEDisconnectError("Device disconnected", self.parseResp(link.closed))

    def _connect(self, addr, addrType=ADDR_TYPE_PUBLIC, iface=None, timeout=_DEFAULT_TIMEOUT):
        addr = _checkMACAddress(addr)
        if addrType not in (ADDR_TYPE_PUBLIC, ADDR_TYPE_RANDOM):
            raise ValueError("Expected address type public or random, got {}".format(addrType))
        timeout = self._timeoutValue(timeout)
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._lock:
            # Never reuse a helper from an earlier connection or attempt: while it
            # is still connected (or connecting, after a timeout) it ignores 'conn',
            # so we would silently keep talking to the previous device.
            self._stopHelper()
            self._serviceMap = None
            self._notifyCallbacks = {}
            self._startHelper(iface)
            self.addr = self.deviceAddr = addr
            self.addrType = addrType
            self.iface = iface
            if iface is not None:
                self._writeCmd("conn %s %s %s\n" % (addr, addrType, "hci"+str(iface)))
            else:
                self._writeCmd("conn %s %s\n" % (addr, addrType))
            try:
                while True:
                    remain = None if deadline is None else max(0.0, deadline - time.monotonic())
                    rsp = self._getResp('stat', remain)
                    if rsp is None or rsp['state'][0] != 'tryconn':
                        break
            except BTLEException:
                self._stopHelper()
                raise
            if rsp is None or rsp['state'][0] != 'conn':
                self._stopHelper()
                if rsp is None:
                    raise BTLETimeoutError(
                        "Timed out while trying to connect to peripheral %s, addr type: %s" %
                        (addr, addrType))
                else:
                    raise BTLEDisconnectError("Failed to connect to peripheral %s, addr type: %s"
                                              % (addr, addrType), rsp)

    def connect(self, addr, addrType=ADDR_TYPE_PUBLIC, iface=None, timeout=_DEFAULT_TIMEOUT):
        if isinstance(addr, ScanEntry):
            self._connect(addr.addr, addr.addrType, addr.iface, timeout)
        elif addr is not None:
            self._connect(addr, addrType, iface, timeout)

    def disconnect(self):
        # The delegate is kept, for when we connect again
        with self._lock:
            if self._helper is None:
                return
            timeout = self._timeoutValue(_DEFAULT_TIMEOUT)
            try:
                self._command("disc", 'stat', 10 if timeout is None else min(timeout, 10))
            except (BTLEException, OSError):
                pass                      # helper already gone or disconnected
            finally:
                self._stopHelper()

    def discoverServices(self, timeout=_DEFAULT_TIMEOUT):
        rsp = self._command("svcs", 'find', timeout)
        starts = rsp['hstart']
        ends   = rsp['hend']
        uuids  = rsp['uuid']
        nSvcs = len(uuids)
        assert(len(starts)==nSvcs and len(ends)==nSvcs)
        self._serviceMap = {}
        for i in range(nSvcs):
            self._serviceMap[UUID(uuids[i])] = Service(self, uuids[i], starts[i], ends[i])
        return self._serviceMap

    def getState(self, timeout=_DEFAULT_TIMEOUT):
        status = self.status(timeout)
        return status['state'][0]

    @property
    def services(self):
        return self.getServices()

    def getServices(self, timeout=_DEFAULT_TIMEOUT):
        if self._serviceMap is None:
            self.discoverServices(timeout)
        return self._serviceMap.values()

    def getServiceByUUID(self, uuidVal, timeout=_DEFAULT_TIMEOUT):
        uuid = UUID(uuidVal)
        if self._serviceMap is not None and uuid in self._serviceMap:
            return self._serviceMap[uuid]
        rsp = self._command("svcs %s" % uuid, 'find', timeout)
        if 'hstart' not in rsp:
            raise BTLEGattError("Service %s not found" % (uuid.getCommonName()), rsp)
        svc = Service(self, uuid, rsp['hstart'][0], rsp['hend'][0])

        if self._serviceMap is None:
            self._serviceMap = {}
        self._serviceMap[uuid] = svc
        return svc

    def _getIncludedServices(self, startHnd=1, endHnd=0xFFFF, timeout=_DEFAULT_TIMEOUT):
        # TODO: No working example of this yet
        return self._command("incl %X %X" % (startHnd, endHnd), 'find', timeout)

    def getCharacteristics(self, startHnd=1, endHnd=0xFFFF, uuid=None, timeout=_DEFAULT_TIMEOUT):
        cmd = 'char %X %X' % (startHnd, endHnd)
        if uuid:
            cmd += ' %s' % UUID(uuid)
        rsp = self._command(cmd, 'find', timeout)
        nChars = len(rsp['hnd'])
        return [Characteristic(self, rsp['uuid'][i], rsp['hnd'][i],
                               rsp['props'][i], rsp['vhnd'][i])
                for i in range(nChars)]

    def getDescriptors(self, startHnd=1, endHnd=0xFFFF, timeout=_DEFAULT_TIMEOUT):
        # Historical note:
        # Certain Bluetooth LE devices are not capable of sending back all
        # descriptors in one packet due to the limited size of MTU. So the
        # guest needs to check the response and make retries until all handles
        # are returned.
        # In bluez 5.25 and later, gatt_discover_desc() in attrib/gatt.c does the retry
        # so bluetooth_helper always returns a full list.
        # This was broken in earlier versions.
        try:
            resp = self._command("desc %X %X" % (startHnd, endHnd), 'desc', timeout)
        except BTLEGattError as e:
            if e.estat == ATT_ECODE_ATTR_NOT_FOUND:
                return []                 # nothing in that range
            raise
        ndesc = len(resp['hnd'])
        return [Descriptor(self, resp['uuid'][i], resp['hnd'][i]) for i in range(ndesc)]

    def readCharacteristic(self, handle, timeout=_DEFAULT_TIMEOUT):
        resp = self._command("rd %X" % handle, 'rd', timeout)
        return resp['d'][0]

    def _readCharacteristicByUUID(self, uuid, startHnd, endHnd, timeout=_DEFAULT_TIMEOUT):
        # Not used at present
        return self._command("rdu %s %X %X" % (UUID(uuid), startHnd, endHnd), 'rd', timeout)

    def writeCharacteristic(self, handle, val, withResponse=False, timeout=_DEFAULT_TIMEOUT):
        # Without response, a value too long for one packet will be truncated,
        # but with response, it will be sent as a queued write
        cmd = "wrr" if withResponse else "wr"
        return self._command("%s %X %s" % (cmd, handle, binascii.b2a_hex(val).decode('utf-8')),
                             'wr', timeout)

    def setSecurityLevel(self, level, timeout=_DEFAULT_TIMEOUT):
        return self._command("secu %s" % level, 'stat', timeout)

    def unpair(self, timeout=_DEFAULT_TIMEOUT):
        self._mgmtCmd("unpair", timeout)

    def pair(self, timeout=_DEFAULT_TIMEOUT):
        self._mgmtCmd("pair", timeout)

    def getMTU(self):
        link = self._link
        return link.mtu if link is not None else 0

    def setMTU(self, mtu, timeout=_DEFAULT_TIMEOUT):
        return self._command("mtu %x" % mtu, 'stat', timeout)

    def waitForNotifications(self, timeout):
        """Waits up to timeout seconds (None: for ever) for a notification or
           indication, and passes it on. Returns True if one was received.
           Other threads can send commands meanwhile."""
        link = self._link
        if link is None:
            raise BTLEDisconnectError("Not connected")
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._dispatchLock:
            while True:
                if link.closed is not None:
                    remain = 0.0          # deliver what was received, then stop
                elif deadline is None:
                    remain = None
                else:
                    remain = max(0.0, deadline - time.monotonic())
                try:
                    line = link.notifications.get(timeout=remain)
                except Empty:
                    if link.closed is not None:
                        self._linkClosed(link)
                    return False
                if line is not None:      # None: woken up, the link closed
                    self._deliverNotification(line)
                    return True

    def _setRemoteOOB(self, address, address_type, oob_data, iface=None):
        with self._lock:
            if self._helper is None:
                self._startHelper(iface)
            self.addr = self.deviceAddr = address
            self.addrType = address_type
            self.iface = iface
            cmd = "remote_oob " + address + " " + address_type
            if oob_data.get('C_192') is not None and oob_data.get('R_192') is not None:
                cmd += " C_192 " + oob_data['C_192'] + " R_192 " + oob_data['R_192']
            if oob_data.get('C_256') is not None and oob_data.get('R_256') is not None:
                cmd += " C_256 " + oob_data['C_256'] + " R_256 " + oob_data['R_256']
            self._mgmtCmd(cmd)

    def setRemoteOOB(self, address, address_type, oob_data, iface=None):
        if isinstance(address, ScanEntry):
            (address, address_type, iface) = (address.addr, address.addrType, address.iface)
        address = _checkMACAddress(address)
        if address_type not in (ADDR_TYPE_PUBLIC, ADDR_TYPE_RANDOM):
            raise ValueError("Expected address type public or random, got {}".format(address_type))
        return self._setRemoteOOB(address, address_type, oob_data, iface)

    def getLocalOOB(self, iface=None, timeout=_DEFAULT_TIMEOUT):
        with self._lock:
            if self._helper is None:
                self._startHelper(iface)
            self.iface = iface
            resp = self._command("local_oob", ['oob', 'mgmt'], timeout)
        if resp is not None:
            data = resp.get('d', [None])[0]
            if resp['rsp'][0] != 'oob' or not data:
                raise BTLEManagementError(
                                "Failed to get local OOB data.", resp)
            if len(data) < 51:
                raise BTLEManagementError(
                                "Malformed local OOB data (length %d)." % len(data))
            if struct.unpack_from('<B',data,0)[0] != 8 or struct.unpack_from('<B',data,1)[0] != 0x1b:
                raise BTLEManagementError(
                                "Malformed local OOB data (address).")
            address = data[2:8]
            address_type = data[8:9]
            if struct.unpack_from('<B',data,9)[0] != 2 or struct.unpack_from('<B',data,10)[0] != 0x1c:
                raise BTLEManagementError(
                                "Malformed local OOB data (role).")
            role = data[11:12]
            if struct.unpack_from('<B',data,12)[0] != 17 or struct.unpack_from('<B',data,13)[0] != 0x22:
                raise BTLEManagementError(
                                "Malformed local OOB data (confirm).")
            confirm = data[14:30]
            if struct.unpack_from('<B',data,30)[0] != 17 or struct.unpack_from('<B',data,31)[0] != 0x23:
                raise BTLEManagementError(
                                "Malformed local OOB data (random).")
            random = data[32:48]
            if struct.unpack_from('<B',data,48)[0] != 2 or struct.unpack_from('<B',data,49)[0] != 0x1:
                raise BTLEManagementError(
                                "Malformed local OOB data (flags).")
            flags = data[50:51]
            # Iterating over bytes gives ints on Python 3, so don't use struct here
            hexstr = lambda b: binascii.b2a_hex(b).decode('ascii').upper()
            return {'Address' : hexstr(address),
                    'Type' : hexstr(address_type),
                    'Role' : hexstr(role),
                    'C_256' : hexstr(confirm),
                    'R_256' : hexstr(random),
                    'Flags' : hexstr(flags),
                    }

    def __del__(self):
        try:
            self.disconnect()
        except Exception:
            pass                          # e.g. while the interpreter exits

class ScanEntry:
    addrTypes = { 1 : ADDR_TYPE_PUBLIC,
                  2 : ADDR_TYPE_RANDOM
                }

    FLAGS                     = 0x01
    INCOMPLETE_16B_SERVICES   = 0x02
    COMPLETE_16B_SERVICES     = 0x03
    INCOMPLETE_32B_SERVICES   = 0x04
    COMPLETE_32B_SERVICES     = 0x05
    INCOMPLETE_128B_SERVICES  = 0x06
    COMPLETE_128B_SERVICES    = 0x07
    SHORT_LOCAL_NAME          = 0x08
    COMPLETE_LOCAL_NAME       = 0x09
    TX_POWER                  = 0x0A
    SERVICE_SOLICITATION_16B  = 0x14
    SERVICE_SOLICITATION_32B  = 0x1F
    SERVICE_SOLICITATION_128B = 0x15
    SERVICE_DATA_16B          = 0x16
    SERVICE_DATA_32B          = 0x20
    SERVICE_DATA_128B         = 0x21
    PUBLIC_TARGET_ADDRESS     = 0x17
    RANDOM_TARGET_ADDRESS     = 0x18
    APPEARANCE                = 0x19
    ADVERTISING_INTERVAL      = 0x1A
    MANUFACTURER              = 0xFF

    dataTags = {
        FLAGS                     : 'Flags',
        INCOMPLETE_16B_SERVICES   : 'Incomplete 16b Services',
        COMPLETE_16B_SERVICES     : 'Complete 16b Services',
        INCOMPLETE_32B_SERVICES   : 'Incomplete 32b Services',
        COMPLETE_32B_SERVICES     : 'Complete 32b Services',
        INCOMPLETE_128B_SERVICES  : 'Incomplete 128b Services',
        COMPLETE_128B_SERVICES    : 'Complete 128b Services',
        SHORT_LOCAL_NAME          : 'Short Local Name',
        COMPLETE_LOCAL_NAME       : 'Complete Local Name',
        TX_POWER                  : 'Tx Power',
        SERVICE_SOLICITATION_16B  : '16b Service Solicitation',
        SERVICE_SOLICITATION_32B  : '32b Service Solicitation',
        SERVICE_SOLICITATION_128B : '128b Service Solicitation',
        SERVICE_DATA_16B          : '16b Service Data',
        SERVICE_DATA_32B          : '32b Service Data',
        SERVICE_DATA_128B         : '128b Service Data',
        PUBLIC_TARGET_ADDRESS     : 'Public Target Address',
        RANDOM_TARGET_ADDRESS     : 'Random Target Address',
        APPEARANCE                : 'Appearance',
        ADVERTISING_INTERVAL      : 'Advertising Interval',
        MANUFACTURER              : 'Manufacturer',
    }

    def __init__(self, addr, iface):
        self.addr = addr
        self.iface = iface
        self.addrType = None
        self.rssi = None
        self.connectable = False
        self.rawData = None
        self.scanData = {}
        self.updateCount = 0

    def _update(self, resp):
        addrType = self.addrTypes.get(resp['type'][0], None)
        if addrType is None:
            addrType = self.addrType
        elif (self.addrType is not None) and (addrType != self.addrType):
            # Seen with real devices (#425); not worth aborting the whole
            # scan for, so just keep the most recently reported type
            DBG("Address type changed during scan, for address %s" % self.addr)
        self.addrType = addrType
        self.rssi = -resp['rssi'][0]
        self.connectable = ((resp['flag'][0] & 0x4) == 0)
        data = resp.get('d', [''])[0]
        self.rawData = data

        # Note: bluez is notifying devices twice: once with advertisement data,
        # then with scan response data. Also, the device may update the
        # advertisement or scan data
        isNewData = False
        while len(data) >= 2:
            sdlen, sdid = struct.unpack_from('<BB', data)
            val = data[2 : sdlen + 1]
            if (sdid not in self.scanData) or (val != self.scanData[sdid]):
                isNewData = True
            self.scanData[sdid] = val
            data = data[sdlen + 1:]

        self.updateCount += 1
        return isNewData

    def _decodeUUID(self, val, nbytes):
        if len(val) < nbytes:
            return None
        bval=bytearray(val)
        rs=""
        # Bytes are little-endian; convert to big-endian string
        for i in range(nbytes):
            rs = ("%02X" % bval[i]) + rs
        return UUID(rs)

    def _decodeUUIDlist(self, val, nbytes):
        result = []
        for i in range(0, len(val), nbytes):
            if len(val) >= (i+nbytes):
                result.append(self._decodeUUID(val[i:i+nbytes],nbytes))
        return result

    def getDescription(self, sdid):
        return self.dataTags.get(sdid, hex(sdid))

    def getValue(self, sdid):
        val = self.scanData.get(sdid, None)
        if val is None:
            return None
        if sdid in [ScanEntry.SHORT_LOCAL_NAME, ScanEntry.COMPLETE_LOCAL_NAME]:
            try:
                # Beware! Vol 3 Part C 18.3 doesn't give an encoding. Other references
                # to 'local name' (e.g. vol 3 E, 6.23) suggest it's UTF-8 but in practice
                # devices sometimes have garbage here. See #259, #275, #292.
                return val.decode('utf-8')
            except UnicodeDecodeError:
                bbval = bytearray(val)
                return ''.join( [ (chr(x) if (x>=32 and x<=127) else '?') for x in bbval ] )
        elif sdid in [ScanEntry.INCOMPLETE_16B_SERVICES, ScanEntry.COMPLETE_16B_SERVICES]:
            return self._decodeUUIDlist(val,2)
        elif sdid in [ScanEntry.INCOMPLETE_32B_SERVICES, ScanEntry.COMPLETE_32B_SERVICES]:
            return self._decodeUUIDlist(val,4)
        elif sdid in [ScanEntry.INCOMPLETE_128B_SERVICES, ScanEntry.COMPLETE_128B_SERVICES]:
            return self._decodeUUIDlist(val,16)
        else:
            return val

    def getValueText(self, sdid):
        val = self.getValue(sdid)
        if val is None:
            return None
        if sdid in [ScanEntry.SHORT_LOCAL_NAME, ScanEntry.COMPLETE_LOCAL_NAME]:
            return val
        elif isinstance(val, list):
            return ','.join(str(v) for v in val)
        else:
            return binascii.b2a_hex(val).decode('ascii')

    def getScanData(self):
        '''Returns list of tuples [(tag, description, value)]'''
        return [ (sdid, self.getDescription(sdid), self.getValueText(sdid))
                    for sdid in self.scanData.keys() ]

    # Only the last value of each kind of advertising data is kept, so for
    # example only one manufacturer data block

    def getName(self):
        '''Returns the device's complete local name, or else its short name, or None'''
        name = self.getValue(ScanEntry.COMPLETE_LOCAL_NAME)
        if name is None:
            name = self.getValue(ScanEntry.SHORT_LOCAL_NAME)
        return name

    def getManufacturerData(self):
        '''Returns (company identifier, data) from the manufacturer specific data, or None'''
        val = self.scanData.get(ScanEntry.MANUFACTURER)
        if val is None or len(val) < 2:
            return None
        return (struct.unpack_from('<H', val)[0], val[2:])

    def getServiceData(self):
        '''Returns a dict mapping service UUIDs to their service data'''
        result = {}
        for (sdid, nbytes) in [(ScanEntry.SERVICE_DATA_16B, 2), (ScanEntry.SERVICE_DATA_32B, 4),
                               (ScanEntry.SERVICE_DATA_128B, 16)]:
            val = self.scanData.get(sdid)
            if val is not None and len(val) >= nbytes:
                result[self._decodeUUID(val[:nbytes], nbytes)] = val[nbytes:]
        return result

    def getServiceUUIDs(self):
        '''Returns the UUIDs of the services the device advertises, including
           those it gives service data for'''
        uuids = []
        for sdid in [ScanEntry.INCOMPLETE_16B_SERVICES, ScanEntry.COMPLETE_16B_SERVICES,
                     ScanEntry.INCOMPLETE_32B_SERVICES, ScanEntry.COMPLETE_32B_SERVICES,
                     ScanEntry.INCOMPLETE_128B_SERVICES, ScanEntry.COMPLETE_128B_SERVICES]:
            uuids += self.getValue(sdid) or []
        uuids += self.getServiceData().keys()
        unique = []
        for u in uuids:
            if u not in unique:
                unique.append(u)
        return unique

    def matches(self, name=None, serviceUUID=None, minRSSI=None, connectable=None):
        '''True if the device has all the given properties: an exact name, an
           advertised service, a signal at least minRSSI dBm, connectable or not'''
        if name is not None and self.getName() != name:
            return False
        if serviceUUID is not None and UUID(serviceUUID) not in self.getServiceUUIDs():
            return False
        if minRSSI is not None and (self.rssi is None or self.rssi < minRSSI):
            return False
        if connectable is not None and self.connectable != connectable:
            return False
        return True


class Scanner(BluepyHelper):
    def __init__(self,iface=0):
        BluepyHelper.__init__(self)
        self.scanned = {}
        self.iface=iface
        self.passive=False

    def _cmd(self):
        return "pasv" if self.passive else "scan"

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        # Make sure scanning stops, whatever happened
        if self._helper is not None:
            try:
                self.stop()
            except BTLEException:
                self._stopHelper()

    def start(self, passive=False):
        self.passive = passive
        self._startHelper(iface=self.iface)
        self._mgmtCmd("le on")
        rsp = self._command(self._cmd(), 'mgmt')
        if rsp["code"][0] == "success":
            return
        # Sometimes previous scan still ongoing
        if rsp["code"][0] == "busy":
            self._mgmtCmd(self._cmd()+"end")
            rsp = self._waitResp("stat", self._timeoutValue(_DEFAULT_TIMEOUT))
            if rsp is None or rsp["state"][0] != "disc":
                self._stopHelper()
                raise BTLEManagementError("Failed to stop the previous scan", rsp)
            self._mgmtCmd(self._cmd())
            return
        self._stopHelper()
        raise BTLEManagementError("Failed to start scan", rsp)

    def stop(self):
        self._mgmtCmd(self._cmd()+"end")
        self._stopHelper()

    def clear(self):
        self.scanned = {}

    def process(self, timeout=10.0):
        if self._helper is None:
            raise BTLEInternalError(
                                "Helper not started (did you call start()?)")
        start = time.time()
        while True:
            if timeout:
                remain = start + timeout - time.time()
                if remain <= 0.0:
                    break
            else:
                remain = None
            resp = self._waitResp(['scan', 'stat'], remain)
            if resp is None:
                break

            respType = resp['rsp'][0]
            if respType == 'stat':
                # if scan ended, restart it
                if resp['state'][0] == 'disc':
                    self._mgmtCmd(self._cmd())

            elif respType == 'scan':
                # device found
                addr = binascii.b2a_hex(resp['addr'][0]).decode('utf-8')
                addr = ':'.join([addr[i:i+2] for i in range(0,12,2)])
                if addr in self.scanned:
                    dev = self.scanned[addr]
                else:
                    dev = ScanEntry(addr, self.iface)
                    self.scanned[addr] = dev
                isNewData = dev._update(resp)
                if self.delegate is not None:
                    self.delegate.handleDiscovery(dev, (dev.updateCount <= 1), isNewData)

            else:
                raise BTLEInternalError("Unexpected response: " + respType, resp)

    def getDevices(self, **filters):
        '''Returns the devices found. With filters (the arguments of
           ScanEntry.matches(), e.g. name="Thingy"), only those which match.'''
        if not filters:
            return self.scanned.values()
        return [dev for dev in self.scanned.values() if dev.matches(**filters)]

    def scan(self, timeout=10, passive=False, **filters):
        self.clear()
        self.start(passive=passive)
        try:
            self.process(timeout)
        except BaseException:
            self.__exit__(None, None, None)   # stop, without hiding the error
            raise
        self.stop()
        return self.getDevices(**filters)


def capitaliseName(descr):
    words = descr.replace("("," ").replace(")"," ").replace('-',' ').split(" ")
    capWords =  [ words[0].lower() ]
    capWords += [ w[0:1].upper() + w[1:].lower() for w in words[1:] ]
    return "".join(capWords)

class _UUIDNameMap:
    # Constructor sets self.currentTimeService, self.txPower, and so on
    # from names.
    def __init__(self, idList):
        self.idMap = {}

        for uuid in idList:
            attrName = capitaliseName(uuid.commonName)
            vars(self) [attrName] = uuid
            self.idMap[uuid] = uuid

    def getCommonName(self, uuid):
        if uuid in self.idMap:
            return self.idMap[uuid].commonName
        return None

def get_json_uuid():
    import json
    with open(os.path.join(script_path, 'uuids.json'),"rb") as fp:
        uuid_data = json.loads(fp.read().decode("utf-8"))
    for k in uuid_data.keys():
        for number,cname,name in uuid_data[k]:
            yield UUID(number, cname)
            yield UUID(number, name)

AssignedNumbers = _UUIDNameMap( get_json_uuid() )

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit("Usage:\n  %s <mac-address> [random]" % sys.argv[0])

    if not os.path.isfile(helperExe):
        raise ImportError("Cannot find required executable '%s'" % helperExe)

    devAddr = sys.argv[1]
    if len(sys.argv) == 3:
        addrType = sys.argv[2]
    else:
        addrType = ADDR_TYPE_PUBLIC
    print("Connecting to: {}, address type: {}".format(devAddr, addrType))
    conn = Peripheral(devAddr, addrType)
    try:
        for svc in conn.services:
            print(str(svc), ":")
            for ch in svc.getCharacteristics():
                print("    {}, hnd={}, supports {}".format(ch, hex(ch.handle), ch.propertiesToString()))
                chName = AssignedNumbers.getCommonName(ch.uuid)
                if (ch.supportsRead()):
                    try:
                        print("    ->", repr(ch.read()))
                    except BTLEException as e:
                        print("    ->", e)

    finally:
        conn.disconnect()
