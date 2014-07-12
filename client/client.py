#!/usr/bin/env python

import collections
import select
import socket
import subprocess
import sys
from pymouse import PyMouse

def get_screen_resolution():
    return PyMouse().screen_size()

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

    def run(self, listen_port):
        print('eXtend client daemon running')
        print('listening on UDP port %d' % listen_port)
        self.udp_socket.bind(('0.0.0.0', listen_port))

        while True:
            fail_sockets = [ self.tcp_socket ] if self.connected else []
            read_sockets = [ self.udp_socket ] + fail_sockets

            ready, _, failed = select.select(read_sockets, [], fail_sockets)

            if self.udp_socket in ready:
                data, address = self.udp_socket.recvfrom(1024)

                if not self.connected:
                    self.connect((address[0], 6174))

                self.udp_msg_buffer.update(data)
                for msg in self.udp_msg_buffer:
                    self.process_message(msg)

            if self.tcp_socket in ready:
                self.tcp_msg_buffer.update(self.tcp_socket.recv(1024))
                for msg in self.tcp_msg_buffer:
                    self.process_message(msg)

            if self.tcp_socket in failed:
                self.reset()

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

    def vnc_start(self, vnc_host, vnc_port):
        cmd = (self.vnc_command.replace('HOST', vnc_host)
                               .replace('PORT', vnc_port)).split()

        self.vnc_stop()
        self.vnc_process = subprocess.Popen(cmd)

    def set_cursor_pos(self, x, y):
        PyMouse().move(x, y)

    def process_message(self, msg):
        print('message: %s' % msg)

        stripped = msg.strip()
        if not stripped:
            raise ValueError('empty message')

        words = stripped.split()
        handler = {
            'cursor': lambda x, y: self.set_cursor_pos(int(x), int(y)),
            'vnc': lambda host, port: self.vnc_start(host, port)
        }.get(words[0])

        if handler is not None:
            return handler(*words[1:])
        else:
            print('invalid message: %s' % msg)

EXtendClient('vncviewer -viewonly HOST::PORT').run(6174)

