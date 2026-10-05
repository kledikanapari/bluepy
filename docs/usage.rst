.. _usage:

Timeouts, threads, logging and permissions
==========================================

Timeouts
--------

Every operation on a ``Peripheral`` waits for a reply for at most its
``responseTimeout`` (60 seconds unless set otherwise, e.g.
``Peripheral(address, responseTimeout=10)``), or the *timeout* given to that
call. Without a reply in time, ``BTLETimeoutError`` is raised and the
connection is closed: a late reply could otherwise be taken for the reply to
a later command. ``BTLETimeoutError`` is a subclass of ``BTLEDisconnectError``,
so code which handles disconnections handles it too.

The default is longer than the 30 seconds after which Bluetooth itself (BlueZ)
gives up on a device which doesn't answer. ``None`` waits for ever.

Threads
-------

A ``Peripheral`` can be used from several threads: commands are sent one at a
time. A thread waiting in ``waitForNotifications()`` doesn't hold up the
others, so a common pattern is one thread receiving notifications::

    def listen():
        while True:
            p.waitForNotifications(None)

    threading.Thread(target=listen, daemon=True).start()
    # ... other threads read and write characteristics

Notifications are delivered one at a time, in order, by the thread waiting
in ``waitForNotifications()``, or else by whichever thread is running a
command. When a thread calls ``disconnect()``, a thread waiting for
notifications gets ``BTLEDisconnectError``.

A ``Scanner`` should be used from one thread only.

Logging
-------

``bluepy`` logs what it sends to and receives from ``bluepy-helper`` at debug
level, with the ``logging`` module, under the name ``bluepy.btle``::

    import logging
    logging.basicConfig()
    logging.getLogger('bluepy.btle').setLevel(logging.DEBUG)

Setting ``btle.Debugging = True`` still prints the same messages, but is
deprecated.

Permissions
-----------

Connecting to devices works for any user, but scanning and pairing use the
Bluetooth management interface, which needs more rights. Rather than running
everything as root, give them to ``bluepy-helper`` only::

    sudo setcap 'cap_net_raw,cap_net_admin+eip' /path/to/bluepy/bluepy-helper

(``python3 -c "import bluepy.btle; print(bluepy.btle.helperExe)"`` prints the
path). This has to be done again after reinstalling or upgrading bluepy.
Without it, ``Scanner`` raises ``BTLEManagementError`` ("Management not
available (permissions problem?)" or "Failed to execute management command").
