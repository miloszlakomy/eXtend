#!/usr/bin/env python

import shlex
import select
import socket
import websocket
import threading
import message_buffer
import collections
import time
import traceback
import vnc
import guacamole

LOGOUT_URL = '/guacamole/logout'
LOGIN_URL = '/guacamole/login'
LOGIN_USER = 'inz'
LOGIN_PASS = 'inz'

DEBUG = True

def ws_print(*args):
    HEADER = 'WebServer: '

    def decorate(x):
        if isinstance(x, Exception):
            x = traceback.format_exc(x).strip()
        return HEADER + ('\n' + HEADER).join(x.split('\n'))

    print('\n'.join(decorate(x) for x in args))

def ws_print_debug(text):
    if DEBUG:
        ws_print(text)

class SocketClosed(Exception): pass
class ClientReconnected(Exception): pass

class WebClient(object):
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.msg_buffer = message_buffer.MessageBuffer()

        self.id = None
        self.resolution = None
        self.output = None

    def fileno(self):
        """ makes it possible to use WebClient instances in select() calls """
        return self.sock.fileno()

    def update(self):
        data = self.sock.recv(1024)

        if data:
            self.msg_buffer.update(data)

            for msg in self.msg_buffer:
                self._handle_message(msg)
        else:
            raise SocketClosed

    def kill(self):
        ws_print('killing client: %s' % self)
        self.id = None

        if self.output:
            vnc.cleanup(self.output)

    def send(self, commands):
        if not isinstance(commands, list):
            commands = [ commands ]

        for resp in commands:
            ws_print_debug('[%s] << %s' % (self, resp))
            self.sock.send(resp + '\n')

    def _handle_message(self, msg):
        ws_print_debug('[%s] >> %s' % (self, msg.strip()))

        args = shlex.split(msg.strip())
        handler = getattr(WebClient, "_MSG_" + args[0], None)

        if handler:
            try:
                return handler(self, *args[1:])
            except TypeError as e:
                ws_print('ignoring invalid message: "%s", reason:' % msg, e)
        else:
            ws_print('client %s self an unexpected message: %s' % (self, msg))

    def _init_guacamole(self):
        ws_print('init guacamole')
        self.output = vnc.initVirtualOutputAndVNC(self.resolution, None)

        vnc_pass = open(vnc.passwordFile).readline().strip('\n') if vnc.passwordFile else ''
        config = guacamole.Config('/etc/guacamole/user-mapping.xml')
        self.id = config.get_connection_name(self.output.vncPort,
                                             password=vnc_pass,
                                             auto_create=True)
        ws_print('assigned id = %s for VNC at port %d (password = %s)'
                 % (self.id, self.output.vncPort, vnc_pass))

    def _make_guacamole_url(self):
        return '/guacamole/client.xhtml?id=c%2F' + str(self.id)

    def __str__(self):
        if self.id is not None:
            return '<%s @ %s:%d>' % (self.id, self.addr[0], self.addr[1])
        else:
            return '<%s:%d>' % self.addr

    # expected message flow:
    #  .-- CLIENT ---.      .------------------ SERVER ------------------,
    #  connect <w> <h>  -->
    #                                      <setup guacamole>
    #                  <--                 display <id> <url>
    #  <refresh page>
    #  reconnect <id>  -->
    #                       reauth <logout_url> <login_url> <login> <pass>
    #                                      display <id> <url>
    def handle_reconnect(self, old_self):
        ws_print('client %s reconnected (was %s)' % (self, old_self))

        self.addr = old_self.addr
        self.id = old_self.id
        self.resolution = old_self.resolution
        self.output = old_self.output

        # logout is needed to make sure loaded user-mapping.xml is up-to-date
        # otherwise VNC connections with password may not work, since guacamole
        # seems to read it only at every login attempt.
        self.send([ 'reauth %s %s %s %s'
                    % (LOGOUT_URL, LOGIN_URL, LOGIN_USER, LOGIN_PASS),
                    'display %s %s' % (self.id, self._make_guacamole_url()) ])

    def _MSG_connect(self, width, height):
        if not self.id:
            self.resolution = (int(width), int(height))
            self._init_guacamole()
        else:
            ws_print('TODO: handle duplicate connect')

        self.send('display %s %s' % (self.id, self._make_guacamole_url()))

    def _MSG_reconnect(self, prev_id):
        if self.id:
            ws_print('received reconnect message, which is only valid on '
                     'uninitialized clients')
        else:
            raise ClientReconnected(prev_id)

class WebServerThread(threading.Thread):
    class Zombie(object):
        RECONNECT_TIMEOUT_S = 5

        def __init__(self, client, time_last_seen):
            self.client = client
            self.time_last_seen = time_last_seen

        def is_dead(self):
            if time.time() - self.time_last_seen > self.RECONNECT_TIMEOUT_S:
                self.client.kill()
                # yep, it's dead
                return True

            return False

        def __str__(self):
            return 'Zombie: %s' % self.client

    def __init__(self, host, port):
        threading.Thread.__init__(self)

        self.local_addr = (host, port)
        self.server_sock = None
        self.clients = []

        # guacamole web client won't work if there is no '?id=###' GET
        # argument in the URL. there seems to be no way to set it without
        # actually reloading the page, so clients have to reconnect to the
        # server.
        self.zombies = [] # disconnected clients that may yet reconnect

    def _remove_client(self, client):
        client.kill()
        self.clients.remove(client)

    def _handle_new_client(self):
        try:
            ws_print('handling new cleint')
            sock, addr = self.server_sock.accept()
            ws_print('accepted new web client connection from %s:%d' % addr)
            wrapped_sock = websocket.ServerWebsocket(sock)
            self.clients.append(WebClient(wrapped_sock, addr))
        except websocket.HandshakeFailed as e:
            ws_print('ignoring %s:%d, websocket handshake failed. reason:' % addr, e)

    def _find_zombie_by_id(self, id):
        ws_print('looking for %s in [ %s ]' % (id, ', '.join(str(s) for s in self.zombies)))
        for z in self.zombies:
            if z.client.id == id:
                return z
        return None

    def _handle_client_reconnect(self, client, id):
        zombie = self._find_zombie_by_id(id)
        if not zombie:
            raise ValueError('invalid reconnect request for client id = %s' % id)

        client.handle_reconnect(zombie.client)
        self.zombies.remove(zombie)

    def _handle_client_disconnect(self, client):
        self.zombies.append(WebServerThread.Zombie(client, time.time()))
        self.clients.remove(client)
        ws_print('client %s disconnected' % client)

    def _handle_client_message(self, client):
        try:
            try:
                client.update()
            except ClientReconnected as e:
                self._handle_client_reconnect(client, e[0])
            except SocketClosed:
                self._handle_client_disconnect(client)
        except Exception as e:
            ws_print('removing client because of error', e)
            self._remove_client(client)

    def _clean_zombies(self):
        self.zombies = [ z for z in self.zombies if not z.is_dead() ]

    def _handle_sockets(self):
        waitables = [ self.server_sock ] + self.clients
        read, _, fail = select.select(waitables, [], waitables, 1)

        for ready in read:
            if self.server_sock is ready:
                self._handle_new_client()
            else:
                self._handle_client_message(ready)

        for failed in fail:
            if self.server_sock is failed:
                ws_print('server socket failed, thread shutting down')
                return False
            if failed in clients:
                ws_print('socket failed for client: %s' % client)
                clients.remove(failed)

        return True

    def run(self):
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_sock.bind(self.local_addr)

            ws_print('starting websocket server on %s:%d'
                     % (self.local_addr[0] or '0.0.0.0', self.local_addr[1]))
            self.server_sock.listen(5)

            try:
                while self._handle_sockets():
                    self._clean_zombies()
            except:
                # socket == None means that the thread got killed
                if self.server_sock is not None:
                    raise
            finally:
                if self.server_sock:
                    self.server_sock.close()
                for client in self.clients:
                    client.kill()
                self.clients = []
                self.zombies = []
        finally:
            ws_print('server thread exiting')

    def kill(self, wait = True):
        server = self.server_sock
        self.server_sock = None
        server.close()

        if wait:
            ws_print('waiting for server to exit')
            self.join()

def start_server(host, port):
    server_thread = WebServerThread(host, port)
    #server_thread.daemon = True
    server_thread.start()
    return server_thread

if __name__ == '__main__':
    import sys

    if len(sys.argv) != 2:
        print('usage: %s <port>' % sys.argv[0])
        sys.exit(1)

    server = start_server('', int(sys.argv[1]))
    try:
        while True:
            time.sleep(1)
    finally:
        server.kill()

