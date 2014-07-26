#!/usr/bin/env python

import collections
import errno
import os
import signal
import select
import socket
import subprocess
import sys
import argparse
import struct
from pymouse import PyMouse

DEFAULT_TCP_PORT = int(os.getenv('EXTEND_TCP_PORT') or 0x7e5d)
DEFAULT_MCAST_GROUP = os.getenv('EXTEND_MCAST_GROUP') or '224.0.126.93'
DEFAULT_MCAST_PORT = int(os.getenv('EXTEND_MCAST_PORT') or 0x7e5d)
DEFAULT_LOCK_PREFIX = os.getenv('HOME') or '/tmp'
DEFAULT_LOCK_FILE = DEFAULT_LOCK_PREFIX + '/.eXtend-client.lock'

DEFAULT_VNCCLIENT_CMD = 'vncviewer -viewonly HOST::PORT' # windowed
#DEFAULT_VNCCLIENT_CMD = 'vncviewer -fullscreen -viewonly HOST::PORT' # fullscreen

def parse_int(val):
    if val.startswith('0x'):
        return int(val, 16)
    return int(val)

parser = argparse.ArgumentParser(description='eXtend client daemon.')
parser.add_argument('-t', '--tcp-port',
                    action='store',
                    dest='tcp_port',
                    default=DEFAULT_TCP_PORT,
                    type=parse_int,
                    help='set TCP port used to communicate with the server. If '
                         'not specified, the value of EXTEND_TCP_PORT '
                         'environment variable will be used, or 0x7e5d (32349) '
                         'if EXTEND_TCP_PORT is not set.')
parser.add_argument('-g', '--multicast-group',
                    action='store',
                    dest='mcast_group',
                    default=DEFAULT_MCAST_GROUP,
                    help='set multicast group address to listen for cursor '
                         'coordinates on. If not specified, the value of '
                         'EXTEND_MCAST_GROUP environment variable will be '
                         'used, or 224.0.126.93 if EXTEND_MCAST_GROUP is not '
                         'set.')
parser.add_argument('-p', '--multicast-port',
                    action='store',
                    dest='mcast_port',
                    default=DEFAULT_MCAST_PORT,
                    type=parse_int,
                    help='set multicast port to listen for cursor coordinates '
                         'on. If not specified, the value of EXTEND_MCAST_PORT '
                         'environment variable will be used, or 0x7e5d (32349) '
                         'if EXTEND_MCAST_GROUP is not set.')
parser.add_argument('-l', '--lock-file',
                    action='store',
                    dest='lock_file',
                    default=DEFAULT_LOCK_FILE,
                    help='set path to the lock file used. If not specified, '
                         'the .eXtend-client.lock file will be placed in user '
                         'home directory (HOME environment variable), or /tmp/ '
                         'if HOME is not set.')
parser.add_argument('-s', '--server-ip',
                    action='store',
                    dest='server_ip',
                    default=None,
                    help='attempt to connect to given IP instead of listening '
                         'for activity on UDP port.')
parser.add_argument('-v', '--vnc-client-cmd',
                    action='store',
                    dest='vnc_client_cmd',
                    default=DEFAULT_VNCCLIENT_CMD,
                    help='set a shell command used to spawn VNC client. The '
                         'HOST and PORT substrings will be replaced with the '
                         'IP and port of the VNC server. Default: `%s`'
                         % DEFAULT_VNCCLIENT_CMD)

ARGS = parser.parse_args()

def get_screen_resolution():
    return PyMouse().screen_size()

def lock():
    if os.path.isfile(ARGS.lock_file):
        print('Another eXtend-client instance is running or previous one '
              'crashed. Ensure there is no other client running or delete '
              '%s file in case it crashed.' % ARGS.lock_file)
        sys.exit(1)

    open(ARGS.lock_file, 'w').close()

def unlock():
    os.remove(ARGS.lock_file)

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
        self.display_offset = (0, 0)

    def running(self):
        return (self.connected
                or (self.vnc_process and self.vnc_process.poll is not None))

    def init_multicast(self, group, port):
        print('listening for multicast messages to %s:%d' % (group, port))
        join_req = struct.pack('4sl', socket.inet_aton(group), socket.INADDR_ANY)
        self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, join_req)
        self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.bind((group, port))

        mreq = struct.pack('4sl', socket.inet_aton(group), socket.INADDR_ANY)
        self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def on_udp_socket_ready(self, tcp_connect_port):
        data, address = self.udp_socket.recvfrom(1024)

        if not self.connected:
            self.connect((address[0], tcp_connect_port))

        self.udp_msg_buffer.update(data)
        for msg in self.udp_msg_buffer:
            self.process_udp_message(msg)

    def on_tcp_socket_ready(self):
        data = self.tcp_socket.recv(1024)
        if not data:
            print('server disconnected, resetting')
            self.reset()
            return

        self.tcp_msg_buffer.update(data)
        for msg in self.tcp_msg_buffer:
            self.process_tcp_message(msg)

    def run(self, mcast_group, mcast_port, tcp_connect_port, server_ip=None):
        print('eXtend client daemon running')
        self.init_multicast(mcast_group, mcast_port)

        if server_ip is not None:
            self.connect((server_ip, tcp_connect_port))

        while True:
            fail_sockets = [ self.tcp_socket ] if self.running() else []
            read_sockets = [ self.udp_socket ] + fail_sockets

            try:
                ready, _, failed = select.select(read_sockets, [], fail_sockets)

                if self.udp_socket in ready:
                    self.on_udp_socket_ready(tcp_connect_port)

                if self.tcp_socket in ready:
                    self.on_tcp_socket_ready()

                if self.tcp_socket in failed:
                    self.reset()
            except select.error as e:
                if e[0] != errno.EINTR:
                    raise

    def connect(self, address):
        print('connecting to %s:%d' % address)
        self.tcp_socket.connect(address)
        self.connected = True
        self.tcp_socket.send('resolution %s %s\n' % get_screen_resolution())
        self.tcp_socket.makefile().flush()
        print('resolution sent')

    def reset(self):
        self.tcp_socket.close()
        self.connected = False
        self.vnc_stop()

    def vnc_stop(self):
        if self.vnc_process:
            print('stopping vnc client')
            self.vnc_process.terminate()
            self.vnc_process = None

    def vnc_start(self, vnc_host, vnc_port, offset_x, offset_y):
        cmd = (self.vnc_command.replace('HOST', vnc_host)
                               .replace('PORT', vnc_port)).split()

        print('starting vnc viewer (%s)' % cmd)
        self.display_offset = (int(offset_x), int(offset_y))

        self.vnc_stop()
        self.vnc_process = subprocess.Popen(cmd)

    def set_cursor_pos(self, x, y):
        #PyMouse().move(x - self.display_offset[0],
                       #y - self.display_offset[1])
        PyMouse().move(x, y)

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
        print('TCP >> %s' % msg)
        return self.process_message(msg, {
            'vnc': lambda *args: self.vnc_start(*args)
        })

def sighandler(*args):
    raise KeyboardInterrupt

lock()

for sig in [ signal.SIGTERM, signal.SIGHUP ]:
    signal.signal(sig, sighandler)

client = None

try:
    client = EXtendClient(ARGS.vnc_client_cmd)
    client.run(mcast_group=ARGS.mcast_group,
               mcast_port=ARGS.mcast_port,
               tcp_connect_port=ARGS.tcp_port,
               server_ip=ARGS.server_ip)
except KeyboardInterrupt:
    pass
finally:
    if client:
        client.vnc_stop()

    unlock()

