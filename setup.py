"""Builds bluepy-helper (C) along with the Python package.

Package metadata is in pyproject.toml (repeated below for old setuptools).
"""

from setuptools.command.build_py import build_py
from setuptools import setup
import setuptools
import subprocess
import shlex
import sys
import os

VERSION='1.3.0'

def pre_install():
    """Do the custom compiling of the bluepy-helper executable from the makefile"""
    try:
        print("Working dir is " + os.getcwd())
        with open("bluepy/version.h","w") as verfile:
            verfile.write('#define VERSION_STRING "%s"\n' % VERSION)
        for cmd in [ "make -C ./bluepy clean", "make -C bluepy -j1" ]:
            print("execute " + cmd)
            subprocess.check_output(shlex.split(cmd), stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print("Failed to compile bluepy-helper. Exiting install.")
        print("Command was " + repr(cmd) + " in " + os.getcwd())
        print("Return code was %d" % e.returncode)
        print("Output was:\n%s" % e.output.decode(errors='replace'))
        sys.exit(1)

class my_build_py(build_py):
    def run(self):
        pre_install()
        build_py.run(self)

setup_cmdclass = {
    'build_py' : my_build_py,
}

# Force package to be *not* pure Python
# Discusssed at issue #158

try:
    try:
        # Part of setuptools since v70.1; the copy in 'wheel' is deprecated
        from setuptools.command.bdist_wheel import bdist_wheel
    except ImportError:
        from wheel.bdist_wheel import bdist_wheel

    class BluepyBdistWheel(bdist_wheel):
        def finalize_options(self):
            bdist_wheel.finalize_options(self)
            self.root_is_pure = False

    setup_cmdclass['bdist_wheel'] = BluepyBdistWheel
except ImportError:
    pass


# setuptools before 61 (e.g. 52 on Debian 11 / Raspberry Pi OS Bullseye)
# ignore the [project] table: without this, 'python3 setup.py install' would
# install an empty package called UNKNOWN
legacy_metadata = {}
if int(setuptools.__version__.split('.')[0]) < 61:
    legacy_metadata = dict(
        name='bluepy',
        description='Python module for interfacing with BLE devices through Bluez',
        author='Ian Harvey',
        author_email='website-contact@fenditton.org',
        url='https://github.com/IanHarvey/bluepy',
        python_requires='>=3.8',
        packages=['bluepy'],
        package_data={
            'bluepy': ['bluepy-helper', '*.json', 'bluez-src.tgz', 'bluepy-helper.c', 'version.h', 'Makefile']
        },
        entry_points={
            'console_scripts': [
                'thingy52=bluepy.thingy52:main',
                'sensortag=bluepy.sensortag:main',
                'blescan=bluepy.blescan:main',
            ]
        },
    )

setup(
    version=VERSION,
    cmdclass=setup_cmdclass,
    **legacy_metadata
)
