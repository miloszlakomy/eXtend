from __future__ import print_function
import base64
import socket
import select
import hashlib
import struct
import os

DEBUG = os.getenv('DEBUG')
WS_DEBUG = os.getenv('WS_DEBUG')

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

def ws_debug_print(*args, **kwargs):
    if WS_DEBUG:
        print(*args, **kwargs)

class StructStream(object):
    def __init__(self, buf):
        self.buf = buf
        self.at = 0

    def _countAdvance(self, format):
        bytes = 0

        if format[0] in '@=<>!':
            format = format[1:]

        at = 0
        numberString = ''
        while at < len(format):
            c = format[at]
            at += 1

            if c in '0123456789': numberString += c
            elif c in 'xcbB': bytes += 1
            elif c in 'hH': bytes += 2
            elif c in 'iIlLf': bytes += 4
            elif c in 'qQd': bytes += 8
            elif c in 's':
                bytes += int(numberString)
                numberString = ''
            elif c in 'pP':
                raise NotImplementedError()
            else:
                raise AssertionError('unknown format character: %s' % c)

        ws_debug_print('bytes for %s: %d' % (format, bytes))
        return bytes

    def unpack(self, format):
        num_bytes = self._countAdvance(format)

        if self.at + num_bytes > len(self.buf):
            raise AssertionError('not enough data')

        ret = struct.unpack(format, self.buf[self.at:self.at+num_bytes])
        self.at += num_bytes
        if len(ret) > 1:
            return ret
        return ret[0]

    def get_data(self):
        return self.buf[self.at:]

class Websocket(socket.socket):
    MIN_FRAME_LENGTH = 2

    def __init__(self, mask, sock):
        self._socket = sock
        self._mask = mask

    def send(self, *args, **kwargs):
        return self._socket.send(*args, **kwargs)

    def recv(self, *args, **kwargs):
        return self._socket.recv(*args, **kwargs)

    def bind(self, *args, **kwargs):
        return self._socket.bind(*args, **kwargs)

    def listen(self, *args, **kwargs):
        return self._socket.listen(*args, **kwargs)

    def accept(self, *args, **kwargs):
        return self._socket.accept(*args, **kwargs)

    def connect(self, *args, **kwargs):
        return self._socket.connect(*args, **kwargs)

    def close(self, *args, **kwargs):
        return self._socket.close(*args, **kwargs)

    def fileno(self, *args, **kwargs):
        return self._socket.fileno(*args, **kwargs)

    def _split(self, data):
        ret = []
        i = 0
        while i < len(data):
            ret.append(data[i:i+125])
            i += 125
        return ret

    def _make_length_header_field(self, length, mask):
        if length <= 125:
            return chr((128 if mask else 0) + length)
        elif length < 65536:
            return (chr((128 if mask else 0) + 126)
                    + struct.pack('!H', length))
        else:
            return (chr((128 if mask else 0) + 127)
                    + struct.pack('!Q', length))

    def _make_header(self,
                     is_last_frame,
                     mask,
                     dataLength):
        TYPE_TEXT = 1

        return (chr((128 if is_last_frame else 0)
                    + TYPE_TEXT)
                + self._make_length_header_field(dataLength, bool(mask))
                + (mask if mask else ''))


    def wrap(self, data, mask):
        parts = self._split(data)
        wrappedParts = []
        for part in parts[:-1]:
            wrappedParts.append(self._make_header(False, mask, len(part)) + bytes(part))
        wrappedParts.append(self._make_header(True, mask, len(parts[-1])) + bytes(parts[-1]))
        return ''.join(wrappedParts)

    def _extract_headers(self, data):
        ws_debug_print('_extract_headers')
        stream = StructStream(data)
        flags, maskAndLength = stream.unpack('!BB')

        isLast = bool(flags & 128)
        type = flags & 15
        hasMask = bool(maskAndLength & 128)
        length = maskAndLength & 127

        if length == 126:
            length = stream.unpack('!H')
        elif length == 127:
            length = stream.unpack('!Q')

        mask = None
        if hasMask:
            mask = stream.unpack('!4s')

        return isLast, type, length, mask, stream.get_data()

    def _unwrap_some(self, data):
        ws_debug_print('_unwrap_some')
        isLast, type, length, mask, data = self._extract_headers(data)
        rest = ''

        if len(data) != length:
            rest = data[length:]
            data = data[:length]

        if mask:
            data = ''.join([ chr(ord(c) ^ ord(mask[i % 4]))
                             for i, c in enumerate(data) ])

        ws_debug_print('unmasked data: ' + data)
        return data, rest

    def unwrap(self, data):
        ws_debug_print('unwrap')
        unwrapped, rest = self._unwrap_some(data)
        while rest:
            ws_debug_print('%d bytes to go' % len(rest))
            frame_data, rest = self._unwrap_some(rest)
            unwrapped += frame_data

        if len(rest) > 0:
            raise NotImplementedError()

        return unwrapped

#class ClientWebsocket(Websocket):
#    def __init__(self, socket):
#        Websocket.__init__(self, True, socket)
#
#    def send(self, data):
#        Websocket.sen(self, Websocket.wrap(self, data,
#                                           struct.pack('!I', random.randint())))
#
#    def recv(self, maxBytes):
#        data = Websocket.recv(self, maxBytes)
#
#        if (len(data) > Websocket.MIN_FRAME_LENGTH):
#            return Websocket.unwrap(self, data)

class ServerWebsocket(Websocket):
    HANDSHAKE_MAGIC_STRING = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    HANDSHAKE_MSG_FORMAT = """
HTTP/1.1 101 Switching Protocols\r
Upgrade: WebSocket\r
Connection: Upgrade\r
Sec-WebSocket-Accept: %s
    """.strip() + "\r\n\r\n"

    def __init__(self, socket):
        Websocket.__init__(self, False, socket)

        self._handshake_completed = False
        self._client_key = None
        self._do_handshake()

    def send(self, data):
        debug_print('<< %s' % data)
        Websocket.send(self, self.wrap(data, None))

    def recv(self, maxBytes):
        data = Websocket.recv(self, maxBytes)

        if len(data) > Websocket.MIN_FRAME_LENGTH:
            unwrapped = Websocket.unwrap(self, data)
            debug_print('>> %s' % unwrapped)
            return unwrapped

    def _do_handshake(self):
        buf = Websocket.recv(self, 2048)

        for line in buf.split('\r\n'):
            if self._handshake_completed:
                break

            self._process_handshake_line(line.strip())

    def _gen_accept_key(self):
        if self._client_key is None:
            raise AssertionError('client_key must be set')

        return base64.b64encode(
            hashlib.sha1(self._client_key
                         + ServerWebsocket.HANDSHAKE_MAGIC_STRING).digest())

    def _process_handshake_line(self, line):
        if self._client_key and not line:
            self._socket.send(ServerWebsocket.HANDSHAKE_MSG_FORMAT
                              % self._gen_accept_key())
            self._handshake_completed = True
            ws_debug_print('handshake completed')
            return

        words = line.split()
        if words[0] == 'Sec-WebSocket-Key:':
            self._client_key = words[1]
            ws_debug_print('client key: %s' % words[1])

