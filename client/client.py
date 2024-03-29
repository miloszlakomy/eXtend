#!/usr/bin/env python

import collections
import errno
import os
import shlex
import signal
import select
import socket
import subprocess
import sys
import argparse
import struct
import tempfile

sys.path += [ os.path.join(os.path.dirname(__file__), 'libs') ]

from pymouse import PyMouse
from message_buffer import MessageBuffer
from runAndWait import runAndWait
import ifutils
import pyfiglet

DEFAULT_PORT = int(os.getenv('EXTEND_PORT') or 0x7e5d)
DEFAULT_MCAST_GROUP = os.getenv('EXTEND_MCAST_GROUP') or '224.0.126.93'
DEFAULT_LOCK_PREFIX = os.getenv('HOME') or '/tmp'
DEFAULT_LOCK_FILE = DEFAULT_LOCK_PREFIX + '/.eXtend-client.lock'

class VNCViewer(object):
    def start(self, host, port, passwd_file): raise NotImplementedError()
    def stop(self): raise NotImplementedError()
    def is_running(self): raise NotImplementedError()

class GenericVNCViewer(VNCViewer):
    def __init__(self, vnc_client_cmd):
        self.client_cmd = vnc_client_cmd
        self.vnc_process = None

    def start_process(self, host, port):
        if self.is_running():
            self.stop()

        cmd = (self.client_cmd.replace('HOST', host)
                              .replace('PORT', port)
                              .split())

        print('starting VNC viewer: %s' % self.client_cmd)
        self.vnc_process = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def stop(self):
        if not self.is_running():
            return

        print('stopping vnc client')
        try:
            self.vnc_process.terminate()
        except:
            print('cannot terminate VNC client')

        self.vnc_process = None

    def is_running(self):
        return self.vnc_process is not None

class TightVNCViewer(GenericVNCViewer):
    def __init__(self):
        GenericVNCViewer.__init__(self,
                'vncviewer -fullscreen -viewonly -autopass HOST::PORT')

    def start(self, host, port, passwd_file):
        self.start_process(host, port)

        with open(passwd_file) as f:
            self.vnc_process.stdin.write(f.read() + '\n')
            self.vnc_process.stdin.flush()

class TigerVNCViewer(GenericVNCViewer):
    def __init__(self):
        _, self.encrypted_password_file = tempfile.mkstemp()
        GenericVNCViewer.__init__(self,
                ('vncviewer -FullScreen -ViewOnly -PasswordFile %s HOST::PORT' %
                 self.encrypted_password_file))

    def start(self, host, port, passwd_file):
        with open(passwd_file) as f:
            passwd = f.read()
            passwd += '\n' + passwd + '\n'
        runAndWait('vncpasswd %s' % self.encrypted_password_file, stdin=passwd)

        self.start_process(host, port)

def get_vnc_viewer(vnc_client_cmd = None):
    if vnc_client_cmd:
        return GenericVNCViewer(vnc_client_cmd)

    _, _, exit_code = runAndWait('which vncviewer')
    if exit_code:
        raise ValueError('`vncviewer` command not available')

    stdout, stderr, _ = runAndWait('vncviewer --help')

    stdout = stdout.strip()
    stderr = stderr.strip()

    if stdout:
        name = stdout.split()[0]
    elif stderr:
        name = stderr.split()[0]
    else:
        raise ValueError('Cannot determine installed VNC viewer')

    print('VNC client command not specified, auto-detecting')
    if name == 'TightVNC':
        print('detected TightVNC viewer')
        return TightVNCViewer()
    if name == 'TigerVNC':
        print('detected TigerVNC viewer')
        return TigerVNCViewer()
    else:
        raise NotImplementedError('Installed VNC viewer (%s) is not supported' % name)

#DEFAULT_VNCCLIENT_CMD = 'vncviewer -viewonly HOST::PORT -autopass' # windowed
DEFAULT_VNCCLIENT_CMD = 'vncviewer -fullscreen -viewonly HOST::PORT -autopass' # fullscreen

parser = argparse.ArgumentParser(description='eXtend client daemon.')
parser.add_argument('-g', '--multicast-group',
                    action='store',
                    dest='mcast_group',
                    default=DEFAULT_MCAST_GROUP,
                    help='set multicast group address to listen for cursor '
                         'coordinates on. If not specified, the value of '
                         'EXTEND_MCAST_GROUP environment variable will be '
                         'used, or 224.0.126.93 if EXTEND_MCAST_GROUP is not '
                         'set.')
parser.add_argument('-p', '--port',
                    action='store',
                    dest='port',
                    default=DEFAULT_PORT,
                    type=lambda x: int(x, 0),
                    help='set port used for communication. If not specified, '
                         'the value of EXTEND_PORT environment variable will '
                         'be used, or 0x7e5d (32349) if EXTEND_PORT is not set.')
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
                    default=None,
                    help='set a shell command used to spawn VNC client. The '
                         'HOST and PORT substrings will be replaced with the '
                         'IP and port used to connect to the VNC server. '
                         'If not specified, the client will attempt to '
                         'determine the VNC client from its help message.')
parser.add_argument('-w', '--vnc-passwd-file',
                    action='store',
                    dest='vnc_password_file',
                    default='',
                    help='path to the file containing a password used to '
                         'authenticate with the VNC server. If not specified, '
                         'no password will be used.')
parser.add_argument('-i', '--interface',
                    action='store',
                    dest='interface',
                    default=None,
                    help='name of the interface that will be used for '
                         'communication')

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

class EXtendClient(object):
    def __init__(self, vnc_command, vnc_password_file):
        self.udp_socket = None
        self.tcp_socket = None
        self.tcp_msg_buffer = MessageBuffer()

        self.vnc_viewer = get_vnc_viewer(vnc_command)
        self.vnc_password_file = vnc_password_file
        self.display_offset = (0, 0)

        if not self.vnc_password_file:
            self.vnc_password_file = os.path.expanduser('~/.eXtend_vncPwd')
            if not os.path.exists(self.vnc_password_file):
                fd = os.open(self.vnc_password_file, os.O_WRONLY | os.O_CREAT, 0600)
                os.write(fd, 'lubieplacki')
                os.close(fd)

        self.reset()

    def init_multicast(self, ifname, group, port):
        print('listening for multicast messages to %s:%d' % (group, port))
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8)
        self.udp_socket.bind((group, port))

        if ifname:
            local_addr = socket.inet_aton(ifutils.get_ip_for_iface(ifname))
            mreq = struct.pack('4s4s', socket.inet_aton(group), local_addr)
        else:
            mreq = struct.pack('4sl', socket.inet_aton(group), socket.INADDR_ANY)

        self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def on_udp_socket_ready(self, port):
        data, address = self.udp_socket.recvfrom(1024)

        if not self.tcp_socket:
            self.connect((address[0], port))

        self.process_udp_message(data)

    def on_tcp_socket_ready(self):
        data = self.tcp_socket.recv(1024)
        if not data:
            print('server disconnected, resetting')
            self.reset()
            return

        self.tcp_msg_buffer.update(data)
        for msg in self.tcp_msg_buffer:
            self.process_tcp_message(msg)

    def run(self, ifname, mcast_group, port, server_ip=None):
        print('eXtend client daemon running')
        self.init_multicast(ifname, mcast_group, port)

        if server_ip is not None:
            self.connect((server_ip, port))

        while True:
            fail_sockets = [ self.tcp_socket ] if self.tcp_socket else []
            read_sockets = [ self.udp_socket ] + fail_sockets

            try:
                ready, _, failed = select.select(read_sockets, [], fail_sockets)

                if self.udp_socket in ready:
                    self.on_udp_socket_ready(port)

                if self.tcp_socket in ready:
                    self.on_tcp_socket_ready()

                if self.tcp_socket in failed:
                    self.reset()
            except select.error as e:
                if e[0] != errno.EINTR:
                    raise

    def connect(self, address):
        print('connecting to %s:%d' % address)
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.connect(address)
        self.tcp_socket.send('resolution %s %s\n' % get_screen_resolution())
        self.tcp_socket.makefile().flush()
        print('resolution sent')

    def reset(self):
        if self.tcp_socket:
            self.tcp_socket.close()
        self.tcp_socket = None
        self.vnc_viewer.stop()

    def vnc_start(self, vnc_host, vnc_port, offset_x, offset_y):
        self.display_offset = (int(offset_x), int(offset_y))
        self.vnc_viewer.start(vnc_host, vnc_port, self.vnc_password_file)

    def vnc_stop(self):
        self.vnc_viewer.stop()

    def id_assigned(self, new_id):
        print('got ID: %s' % new_id)
        pyfiglet.print_figlet(new_id, 'doh')
        self.id = new_id

    def set_cursor_pos(self, x, y):
        PyMouse().move(x - self.display_offset[0],
                       y - self.display_offset[1])
        #PyMouse().move(x, y)

    def process_message(self, msg, handlers):
        print('message: %s' % msg)

        stripped = msg.strip()
        if not stripped:
            raise ValueError('empty message')

        words = shlex.split(stripped)
        handler = handlers.get(words[0])

        if handler is not None:
            return handler(*words[1:])
        else:
            print('invalid message: %s' % msg)

    def process_udp_message(self, msg):
        x, y = struct.unpack('!II', msg)
        self.set_cursor_pos(x, y)

    def process_tcp_message(self, msg):
        print('TCP >> %s' % msg)
        return self.process_message(msg, {
            'vnc': lambda *args: self.vnc_start(*args),
            'id': lambda *args: self.id_assigned(*args)
        })

def sighandler(*args):
    raise KeyboardInterrupt

lock()

for sig in [ signal.SIGTERM, signal.SIGHUP ]:
    signal.signal(sig, sighandler)

client = None

try:
    client = EXtendClient(ARGS.vnc_client_cmd,
                          ARGS.vnc_password_file)
    client.run(ifname=ARGS.interface,
               mcast_group=ARGS.mcast_group,
               port=ARGS.port,
               server_ip=ARGS.server_ip)
except KeyboardInterrupt:
    pass
finally:
    if client:
        client.vnc_stop()

    unlock()

