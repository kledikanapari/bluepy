.. _notifications:

Working with notifications
==========================

The simplest way to get notifications is ``Characteristic.enableNotifications()``,
with a function to call for each one::

    from bluepy import btle

    def battery_changed(characteristic, data):
        print("Battery level:", data[0])

    p = btle.Peripheral(address)
    level = p.getServiceByUUID(0x180F).getCharacteristics(0x2A19)[0]
    level.enableNotifications(battery_changed)

    while True:
        p.waitForNotifications(1.0)

Notifications without a callback go to a "delegate" object registered with the
``Peripheral``. A method in the delegate is called whenever
a notification is received from the peripheral, as shown below:

.. function:: handleNotification(cHandle, data)

    Called when a notification has been received from a ``Peripheral``. Normally
    you will call the peripheral's ``waitForNotifications()`` method to allow this,
    but note that a Bluetooth LE device may transmit notifications at any time. This
    means that *handleNotification()* can potentially be called when any BluePy call
    is in progress.

    The *cHandle* parameter is the GATT 'handle' for the characteristic which is 
    sending the notification. If a peripheral sends notifications for more than one
    characteristic, this may be used to distinguish them. The 'handle' value can be
    found by calling the ``getHandle()`` method of a ``Characteristic`` object.

    The *data* parameter is a ``bytes`` value containing the notification data.
    Python's ``struct`` module is handy to unpack it.

It is recommended that the class used for the delegate object is derived from
``btle.DefaultDelegate``. This will ensure that an appropriate default method  
exists for any future calls which may be added to the delegate interface.

Example code
------------

Code to receive notifications from a peripheral can follow the outline below::

    from bluepy import btle

    class MyDelegate(btle.DefaultDelegate):
        def __init__(self, params):
            btle.DefaultDelegate.__init__(self)
            # ... initialise here

        def handleNotification(self, cHandle, data):
            # ... perhaps check cHandle
            # ... process 'data'

    
    # Initialisation  -------

    p = btle.Peripheral( address )
    p.setDelegate( MyDelegate(params) )

    # Setup to turn notifications on, e.g.
    #   svc = p.getServiceByUUID( service_uuid )
    #   ch = svc.getCharacteristics( char_uuid )[0]
    #   ch.enableNotifications()

    # Main loop --------

    while True:
        if p.waitForNotifications(1.0):
            # handleNotification() was called
            continue

        print("Waiting...")
        # Perhaps do something else here


