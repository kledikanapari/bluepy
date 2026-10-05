.. _characteristic:

The ``Characteristic`` class
============================

A Bluetooth LE "characteristic" represents a short data item which can be read or
written. These can be fixed (e.g. a string representing the manufacturer name) or
change dynamically (such as the current temperature or state of a button). Most
interaction with Bluetooth LE peripherals is done by reading or writing characteristics. 

Constructor
-----------

You should not construct ``Characteristic`` objects directly. Instead, use the
``getCharacteristics()`` method of a connected ``Peripheral`` object.

Instance Methods
----------------

.. function:: read([timeout])

    Reads the current value of a characteristic, as `bytes`. This may be
    used with the `struct` module to extract integer values from the data.
    See the ``Peripheral`` class for *timeout*.


.. function:: write(data, [withResponse=False [, timeout]])

    Writes the given *data* (of type `bytes`) to the characteristic. Bluetooth LE allows the sender to
    request the peripheral to send a response to confirm that the data has been received.
    Setting the *withResponse* parameter to *True* will make this request. A
    `BTLEException` will be raised if the confirmation process fails.

.. function:: enableNotifications([callback=None [, indicate=False [, timeout]]])

    Asks the device to send a notification (or, with *indicate* set to *True*, an
    indication) each time the value changes, by writing the characteristic's Client
    Characteristic Configuration descriptor. With a *callback*, each one is passed to
    ``callback(characteristic, data)``; otherwise to the peripheral's delegate. They
    arrive while the program is in ``Peripheral.waitForNotifications()``, or in any
    other call to the peripheral. Raises ``BTLEGattError`` if the characteristic
    doesn't support them. See :ref:`notifications`.

.. function:: disableNotifications([timeout])

    Stops notifications and indications.

.. function:: getDescriptors([forUUID=None [, hndEnd [, timeout]]])
    :no-index:

    Returns the characteristic's descriptors, optionally only those with UUID
    *forUUID*. When the characteristic was found through
    ``Service.getCharacteristics()``, only the handles up to the next characteristic
    are searched; otherwise up to *hndEnd* (default 0xFFFF).
    
.. function:: supportsRead()

    Returns *True* if the characteristic can be read (as indicated by its properties)
    and *False* otherwise.
 
.. function:: propertiesToString()

    Returns a string describing the characteristic properties ('READ', 'WRITE', etc).

.. function:: getHandle()

    Returns the 16-bit integer value used to identify the characteristic in the
    underlying GATT protocol. This may be useful to distinguish between notifications
    from different characteristics (see :ref:`notifications` for further information).

Properties
----------

All the properties listed below are read-only.

.. py:attribute:: uuid

    The Bluetooth ``UUID`` for this characteristic.
    
.. py:attribute:: peripheral

    The ``Peripheral`` object for the device to which the characteristic belongs.
    
.. py:attribute:: properties

    A bitmask of properties for the characteristic.


