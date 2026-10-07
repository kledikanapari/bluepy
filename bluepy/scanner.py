#!/usr/bin/env python3
"""Scans for 10 seconds, printing every device found, with all its details,
as soon as it is seen (and again whenever its data changes)."""

from time import strftime
import sys

from bluepy.btle import Scanner, DefaultDelegate
from bluepy.blescan import describe_device


class ScanDelegate(DefaultDelegate):

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if not (isNewDev or isNewData):
            return
        print("%s %s device:" % (strftime("%H:%M:%S"), "New" if isNewDev else "Updated"))
        for line in describe_device(dev):
            print("    " + line)
        print()
        sys.stdout.flush()


if __name__ == "__main__":
    scanner = Scanner().withDelegate(ScanDelegate())
    # listen for ADV_IND packages for 10s, then exit
    scanner.scan(10.0, passive=True)
