#!/usr/bin/env python

import collections
import errno
import os
import select
import signal
import socket
import subprocess
import sys
from pymouse import PyMouse

TCP_PORT = int(os.getenv('TCP_PORT') or 0x7e5d)
UDP_PORT = int(os.getenv('UDP_PORT') or TCP_PORT)
TMP_PREFIX = os.getenv('TMPDIR') or '/tmp'

LOCK_FILE = TMP_PREFIX + '/.eXtend-client.lock'

def get_screen_resolution():
    return PyMouse().screen_size()

def lock():
    if os.path.isfile(LOCK_FILE):
        print('Another eXtend-client instance is running or previous one '
              'crashed. Ensure there is no other client running or delete '
              '%s file in case it crashed.' % LOCK_FILE)
        sys.exit(1)

    open(LOCK_FILE, 'w').close()

def unlock():
    os.remove(LOCK_FILE)

class MessageBuffer(object):
    def __init__(self):
        self.messages = []
        self.data = ''

    def update(self, data):
        self.data += data

        lines = self.data.split('\n')
        self.data = lines[-1]
        self.messages += [ line for line in lines[:-1] ]

    def __iter__(self):
        return self

    def next(self):
        if not self.messages:
            raise StopIteration

        ret = self.messages[0]
        self.messages.pop(0)
        return ret

class EXtendClient(object):
    def __init__(self, vnc_command):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, 0)
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.connected = False
        self.udp_msg_buffer = MessageBuffer()
        self.tcp_msg_buffer = MessageBuffer()

        self.vnc_command = vnc_command
        self.vnc_process = None

    def running(self):
        return (self.connected
                or (self.vnc_process and self.vnc_process.poll is not None))

    def run(self, listen_port):
        print('eXtend client daemon running')
        print('listening on UDP port %d' % listen_port)
        self.udp_socket.bind(('0.0.0.0', listen_port))

        while True:
            fail_sockets = [ self.tcp_socket ] if self.running() else []
            read_sockets = [ self.udp_socket ] + fail_sockets

            try:
                print('select')
                ready, _, failed = select.select(read_sockets, [], fail_sockets)

                if self.udp_socket in ready:
                    data, address = self.udp_socket.recvfrom(1024)

                    if not self.connected:
                        self.connect((address[0], 6174))

                    self.udp_msg_buffer.update(data)
                    for msg in self.udp_msg_buffer:
                        self.process_udp_message(msg)

                if self.tcp_socket in ready:
                    self.tcp_msg_buffer.update(self.tcp_socket.recv(1024))
                    for msg in self.tcp_msg_buffer:
                        self.process_tcp_message(msg)

                if self.tcp_socket in failed:
                    self.reset()
            except select.error as e:
                if e[0] != errno.EINTR:
                    raise

    def connect(self, address):
        print('connecting to %s:%d' % address)
        self.tcp_socket.connect(address)
        self.connected = True
        self.tcp_socket.send('resolution %s %s' % get_screen_resolution())

    def reset(self):
        self.tcp_socket.close()
        self.connected = False
        self.vnc_stop()

    def vnc_stop(self):
        if self.vnc_process:
            self.vnc_process.terminate()
            self.vnc_process = None

    def vnc_start(self, vnc_host, vnc_port, offset_x, offset_y):
        cmd = (self.vnc_command.replace('HOST', vnc_host)
                               .replace('PORT', vnc_port)).split()

        self.display_offset_x = int(offset_x)
        self.display_offset_y = int(offset_y)

        self.vnc_stop()
        self.vnc_process = subprocess.Popen(cmd)

    def set_cursor_pos(self, x, y):
        PyMouse().move(x - self.display_offset_x,
                       y - self.display_offset_y)

    def process_message(self, msg, handlers):
        print('message: %s' % msg)

        stripped = msg.strip()
        if not stripped:
            raise ValueError('empty message')

        words = stripped.split()
        handler = handlers.get(words[0])

        if handler is not None:
            return handler(*words[1:])
        else:
            print('invalid message: %s' % msg)

    def process_udp_message(self, msg):
        return self.process_message(msg, {
            'cursor': lambda x, y: self.set_cursor_pos(int(x), int(y)),
        })

    def process_tcp_message(self, msg):
        return self.process_message(msg, {
            'vnc': lambda *args: self.vnc_start(*args)
        })

def signal_handler(sig, stack_frame):
    unlock()
    sys.exit(1)

for sig in [ signal.SIGTERM, signal.SIGINT, signal.SIGHUP ]:
    signal.signal(sig, signal_handler)

lock()
EXtendClient('vncviewer -viewonly HOST::PORT').run(TCP_PORT)

