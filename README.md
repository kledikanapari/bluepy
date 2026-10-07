bluepy
======

Python interface to Bluetooth LE on Linux

This is a project to provide an API to allow access to Bluetooth Low Energy devices
from Python. At present it runs on Linux only; I've mostly developed it using a
Raspberry Pi, but it will also run on x86 Debian Linux.

It needs Python 3.8 or later (Python 2 is no longer supported), and is tested
on Python 3.8 to 3.14. The bundled BlueZ code is from BlueZ 5.87.

There is also code which uses this to talk to a TI SensorTag (www.ti.com/sensortag).

An example to interface the Nordic Semiconductor ASA IoT Sensor Kit, Thingy:52 is available 
in thingy52.py (https://www.nordicsemi.com/eng/Products/Nordic-Thingy-52).

Installation
------------

The code needs an executable `bluepy-helper` to be compiled from C source. This is done
automatically if you use the recommended pip installation method (see below). Otherwise,
you can rebuild it using the Makefile in the `bluepy` directory.

To install the current released version, on most Debian-based systems:

    $ sudo apt-get install python3-pip libglib2.0-dev
    $ sudo pip3 install bluepy

On Fedora do:

    $ sudo dnf install python3-pip glib2-devel

Recent distributions (e.g. Debian 12, Raspberry Pi OS Bookworm) refuse
`sudo pip3 install` ("externally-managed-environment"): install into a virtual
environment instead:

    $ python3 -m venv ~/bluepy-env
    $ ~/bluepy-env/bin/pip install bluepy

*If this fails* you should install from source.

    $ sudo apt-get install git build-essential libglib2.0-dev
    $ git clone https://github.com/IanHarvey/bluepy.git
    $ cd bluepy
    $ pip3 install .

Without pip, `python3 setup.py build` and `sudo python3 setup.py install`
still work (setuptools says they are deprecated). If the install fails with
`AttributeError: install_layout` (Debian/Ubuntu setuptools), run it as
`sudo SETUPTOOLS_USE_DISTUTILS=stdlib python3 setup.py install`. Or skip
installing altogether: run `make -C bluepy` and put the `bluepy` directory
next to your script.

Permissions
-----------

Connecting to devices works for any user, but scanning (`Scanner`, `blescan`)
and pairing need extra rights. Rather than running your program as root, give
them to `bluepy-helper` only:

    $ sudo setcap 'cap_net_raw,cap_net_admin+eip' $(python3 -c "import bluepy.btle; print(bluepy.btle.helperExe)")

This has to be done again after reinstalling or upgrading bluepy. Without it,
scanning fails with `BTLEManagementError` ("Management not available
(permissions problem?)" or "Failed to execute management command").

Debugging
---------

bluepy logs what it sends to and receives from `bluepy-helper` with the
`logging` module, at debug level, under the name `bluepy.btle`:

    import logging
    logging.basicConfig()
    logging.getLogger('bluepy.btle').setLevel(logging.DEBUG)

I would recommend having command-line tools from BlueZ available for debugging. There
are instructions for building BlueZ on the Raspberry Pi at http://www.elinux.org/RPi_Bluetooth_LE.

Running the tests
-----------------

The unit tests don't need Bluetooth hardware (a fake `bluepy-helper` is used
where needed):

    $ python3 -m unittest discover -s tests
    $ make -C bluepy test        # tests for the C code in bluepy-helper

Documentation
-------------

Documentation can be built from the sources in the docs/ directory using Sphinx.

An online version of this is currently available at: http://ianharvey.github.io/bluepy-doc/

License
-------

This project uses code from the bluez project, which is available under the Version 2
of the GNU Public License.

The Python files are released into the public domain by their author, Ian Harvey.

Release Notes
-------------

Release 1.4.0

New:

- Timeouts on all operations: `Peripheral.responseTimeout` (default 60 s,
  also a constructor argument), and a `timeout` argument on each method.
  Without a reply in time, `BTLETimeoutError` (a `BTLEDisconnectError`) is
  raised and the connection is closed. *Changes:* operations no longer wait
  for ever by default (pass `None` for that), and `writeCharacteristic()`
  with a timeout now raises instead of returning `None`.
- `Characteristic.enableNotifications(callback=None, indicate=False)` and
  `disableNotifications()`: no more writing to the 0x2902 descriptor by hand
- A `Peripheral` can be used from several threads, and a thread waiting in
  `waitForNotifications()` no longer holds up the others
- `disconnect()` keeps the delegate, so notifications still work after
  connecting again
- Logging with the `logging` module (`bluepy.btle` logger); `btle.Debugging`
  still works but is deprecated
- Scanning: `ScanEntry.getName()`, `getManufacturerData()`,
  `getServiceData()`, `getServiceUUIDs()`, `matches()`; filters in
  `Scanner.scan()` and `getDevices()`, e.g. `scan(5, name="Foo")`;
  `Scanner` works in a `with` statement
- Passive scans use Bluetooth 5 extended scanning when the adapter supports
  it, so they find devices using extended advertising, and they no longer
  fail where the kernel already uses extended scanning
- The bundled BlueZ code is updated from 5.47 (2017) to 5.87
- Python 2 is no longer supported; Python 3.8 or later is needed. Package
  metadata moved to `pyproject.toml`
- `bluepy.__version__` gives the version
- Tests for the C code (`make -C bluepy test`), and CI on GitHub Actions
- Documentation on permissions (`setcap`), timeouts, threads and logging

Fixes:

- Fix: calling connect() on a Peripheral which was still connected (or still
  trying to connect, after a timeout with no reply) did nothing: bluepy-helper
  silently ignored the request, so the device address was never updated.
  A fresh helper is now used for every connection, and the cached services of
  the previous device are discarded.
- Fix: malformed device addresses (e.g. `str(b'AA:BB:CC:DD:EE:FF')` on Python 3)
  were turned into 00:00:00:00:00:00 by bluepy-helper. They are now rejected
  with ValueError (bluepy-helper also checks them), as is 00:00:00:00:00:00.
- Connection failures now say why (e.g. "Connection refused", or that the
  Bluetooth adapter is down or has no address)
- Peripheral.deviceAddr is now kept up to date (same as Peripheral.addr)
- Fix #425: scanning no longer aborts with "Address type changed during scan"
- Scanner.start() now raises BTLEManagementError if the scan can't be started
- Fix connectable flag of scan results, and passive scan socket handling
  (leaked sockets, duplicate reports, possible 100% CPU)
- Fix crashes in the OOB pairing code (getLocalOOB() on Python 3,
  setRemoteOOB(), and in bluepy-helper)
- bluepy-helper no longer aborts on malformed packets from a peripheral
- Packaging: no more setuptools deprecation warnings; README is the long description

Release 1.3.0

- New getState() method for Peripheral class
- New exception structure / error reporting (#311, #317, #326)
  BTLEException now has subclasses BLTEDisconnectError, BTLEManagementError, etc.
  which report an error code and error message passed up from the lower layers, where
  appropriate.
- Partial merge #311: aids to debugging; bluepy-helper reports version; fix crash
- Partial merge #311 and #302: pair() and unpair() now supported
- Fix #169: 0-byte characteristic writes are now supported
- Merge #302: OOB data now supported
- Merge #312: better comments on sample code in docs, better scanner example
- Fix #292: Unicode string decoding errors in scan data
- Merge #308: don't ignore sensitivity option during discovery
- Merge #301: fix Peripheral documentation
- Fix #286: return list of services from Scan entry


Release 1.2.0
- Merge #245: Update underlying Bluez version to 5.47
- Merge #284: Readme updated with Fedora install instructions
- Merge #283: Fixes for passive scan interruption
- Merge #275, fix #259: non-ASCII device names now don't break decoding
- Fix #263, #278: return UUID in scan results
- Merge #262: Return correct address type in passive scan
 

Release 1.1.4:
- Further attempts to fix #158. setup.py rewritten.

*There was no release 1.1.3 made*

Release 1.1.2: *now deleted*
- Re #158: Try to make PyPI installation more robust
- Merge #214: add passive scan support
- Merge #213: Add Thingy:52 support

Release 1.1.1
- Workaround #200: remove -Werror from Makefile
- Fix #191: generate BTLEException not ValueError, if helper is killed
- Fix #189: error calling getCharacteristics() when Service has no characteristics
- Workaround #192: Use make -j1 explicitly

Release 1.1.0
- Merge #180: Peripheral.connect() can now take ScanEntry object (like constructor)
- Merge #162: Add build_ext builder to setup.py
- Merge #166: Fix crash in getServiceByUUID()
- Fix #148: Add UUIDs for declarations (e.g. 0x2800 = Primary Service Declaration)
- Fix #28: Sensortag accelerometer values now scaled properly
- Merge #89: Add support for descriptors
- Fix #157: make 'services' a property
- Fix #111: make parameter names match documentation
- Fix #128: Characteristic.write() was missing a return value
- Read battery level on Sensortag
- Formatting/style fixes (#170 and others)

Release 1.0.5
- Fix issue #123: Scanner documentation updated
- Fix #125: setup.py error reporting on Python 3 if compilation fails
- Fix for issue #127: setup.py fails to rebuild bluepy-helper 

Release 1.0.4
- Scanner now available as bluepy.blescan module and 'blescan' command
- Fix example scanner code in documentation
- Python 3 installation fixes
- Fix issues #69, #112, #115, #119

Release 1.0.3
- Now available on PyPI as `bluepy`. Installs via pip.

Release 0.9.12
- Support for CC2650 sensortag
- Documentation fixes
- Bug fix: DefaultDelegate has a handleDiscovery method
- Bug fix: keypress now works with both V1.4 and V1.5 firmware 


Release 0.9.11

- Minor consistency improvements & bug fixes
- Scanner now has getDevices() call
- Docs updated

Release 0.9.10

- Now with Scan functionality

Release 0.9.9

- Now based on Bluez r5.29
- UUIDs held in separate JSON file, script added to update from Web
- Added setup.py and __init__.py for use with setuptools
- Allows indications as well as notifications
- Bug fixes (see pull requests #46, #48, #35)

Release 0.9.0
- Support for Notifications
- SensorTag code now supports keypress service
- Bug fix for SetSecurityLevel
- Support for Random address type
- More characteristic and service UUIDs added

Release 0.2.0

- Sphinx-based documentation
- SensorTag optimisations 
- Improved command line interface to sensortag.py
- Added .gitignore file (github issue #17)

Release 0.1.0
- this has received limited testing and bug fixes on Python 3.4.1
- fix for exceptions thrown if peripheral sends notifications

Release dated 2-Jul-2014

- expand AssignedNumbers class definitions
- add getCommonName() to UUID type, returns human-friendly string

Release dated 14-Apr-2014:

- make btle.py useful from the command line
- add AssignedNumbers class

Release dated 12-Mar-2014
- add exceptions, and clean up better on failure

Initial release 19-Oct-2013:

TO DO list
----------

The following are still missing from the current release:
- Peripheral role support



