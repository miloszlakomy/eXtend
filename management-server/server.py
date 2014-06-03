#!/usr/bin/env python
import base64

import sys
import socket
import select
import hashlib

SERVER_PORT = 4242

if len(sys.argv) > 1:
    SERVER_PORT = int(sys.argv[1])

WEBSOCKET_HANDSHAKE_MAGIC_STRING = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
WEBSOCKET_HANDSHAKE_MSG_FORMAT = """
HTTP/1.1 101 Switching Protocols\r
Upgrade: WebSocket\r
Connection: Upgrade\r
Sec-WebSocket-Accept: %s
""".strip() + "\r\n\r\n"


#def findLocalIP():
#    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
#    sock.connect(('example.com', 80))
#    ip = sock.getsockname()[0]
#    sock.close()
#    return ip
#
#LOCAL_IP = findLocalIP()


class Client(object):
    def __init__(self,
                 socket,
                 remoteAddress):
        self.socket = socket
        self.address = remoteAddress
        self.buffer = ''
        self.handshake_completed = False
        self.client_key = None

        print('connection accepted: %s, sending handshake' % ':'.join(str(e) for e in remoteAddress))
        self.do_handshake()

    def do_handshake(self):
        while not self.handshake_completed:
            self.update()

    def __gen_accept_key(self):
        if self.client_key is None:
            raise AssertionError('client_key must be set')

        return base64.b64encode(
            hashlib.sha1(self.client_key
                         + WEBSOCKET_HANDSHAKE_MAGIC_STRING).digest())

    def __process_handshake_line(self, line):
        if not line:
            self.socket.send(WEBSOCKET_HANDSHAKE_MSG_FORMAT
                             % self.__gen_accept_key())
            self.handshake_completed = True
            print('handshake completed')
            self.socket.send('dupa\n')
            return

        words = line.split()
        if words[0] == 'Sec-WebSocket-Key:':
            self.client_key = words[1]
            print('client key: %s' % words[1])
        else:
            pass #print('ignoring header: %s' % line)

    def __process_line(self, line):
        if not self.handshake_completed:
            self.__process_handshake_line(line)
        else:
            print('received line: %s' % line)

    def __process_lines(self):
        if '\n' in self.buffer:
            lines = self.buffer.split('\n')
            self.buffer = lines[-1]
            lines.pop()

            for line in lines:
                print('processing line: %s' % line)
                self.__process_line(line.strip())

    def update(self):
        print('updating socket: %s:%d' % self.address)
        self.buffer += self.socket.recv(1024)
        print('buffer is: ' + self.buffer)
        self.__process_lines()

serverSocket = socket.socket()
serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
serverSocket.bind(('', SERVER_PORT))
serverSocket.listen(5)

sockets = {
    serverSocket: None
}

try:
    while True:
        print('waiting')
        ready, _, errors = select.select([ s for s in sockets ],
                                         [],
                                         [ s for s in sockets ])
        for sock in ready:
            if sockets[sock] is None:
                clientSock, clientAddr = sock.accept()
                sockets[clientSock] = Client(clientSock, clientAddr)
                print('added socket: %s:%d' % clientAddr)
            else:
                sockets[sock].update()

        for sock in errors:
            print('error for socket: %s' % ':'.join(str(e) for e in sockets[sock].address))
            del sockets[sock]
except KeyboardInterrupt:
    pass
