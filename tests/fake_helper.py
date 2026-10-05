"""
Minimal stand-in for bluepy-helper, used by test_peripheral.py

It speaks the same line protocol, and like the original helper it silently
ignores 'conn' unless it is disconnected. Special device addresses:

    11:11:11:11:11:11   never connects (stays in 'tryconn', like a timeout)
    33:33:33:33:33:33   as above, but without even replying 'tryconn'
    22:22:22:22:22:22   connection fails, with an error message
    any other           connects

Every command received is appended to the file named by $FAKE_HELPER_LOG,
prefixed with this process's PID.
"""

import os
import sys

SEP = '\x1e'
NEVER_CONNECTS = '11:11:11:11:11:11'
FAILS = '22:22:22:22:22:22'
NEVER_ANSWERS = '33:33:33:33:33:33'


def send(*fields):
    sys.stdout.write(SEP.join(fields) + '\n')
    sys.stdout.flush()


def main():
    state = 'disc'
    dst = None
    log = os.environ.get('FAKE_HELPER_LOG')
    send('# fake bluepy-helper')

    def status(extra=()):
        fields = ['rsp=$stat', 'state=$' + state]
        if state != 'disc':
            fields.append("dst='" + dst)
        fields += ['mtu=h0', "sec='low"] + list(extra)
        send(*fields)

    for line in iter(sys.stdin.readline, ''):
        if log:
            with open(log, 'a') as f:
                f.write('%d %s' % (os.getpid(), line))
        args = line.split()
        if not args:
            continue
        cmd = args[0]
        if cmd == 'quit':
            break
        elif cmd == 'stat':
            status()
        elif cmd == 'conn':
            if state != 'disc':
                continue                  # what the original helper did
            dst = args[1]
            state = 'tryconn'
            if dst == NEVER_ANSWERS:
                continue
            status()
            if dst == FAILS:
                state = 'disc'
                status(["emsg='Connection refused (111)"])
            elif dst != NEVER_CONNECTS:
                state = 'conn'
                status()
        elif cmd == 'disc':
            state = 'disc'
            status()
        elif cmd == 'svcs':
            send('rsp=$find', 'hstart=h1', 'hend=h5', "uuid='00001800-0000-1000-8000-00805f9b34fb")
        elif cmd == 'le':
            send('rsp=$mgmt', 'code=$success')
        elif cmd in ('scan', 'pasv'):
            send('rsp=$mgmt', 'code=$mgmterr', 'estat=hF', "emsg='Not Powered")
        else:
            send('rsp=$err', 'code=$badcmd')


if __name__ == '__main__':
    main()
