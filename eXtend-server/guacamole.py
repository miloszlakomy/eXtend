#!/usr/bin/env python

from xml.dom import minidom
import subprocess
import sys

class Config(object):
    def __init__(self, filename):
        self.filename = filename
        self.xml = minidom.parse(self.filename)
        self.dirty = False

    def _create_node(self, name, value=None, attrs=[], children=[]):
        node = self.xml.createElement(name)

        if value:
            node.appendChild(self.xml.createTextNode(value))

        for attr in attrs:
            node.setAttribute(*attr)

        for child in children:
            node.appendChild(child)

        return node

    def save(self):
        if not self.dirty:
            return

        try:
            with open(self.filename, 'w') as f:
                f.write('\n'.join(l for l in self.xml.toprettyxml().split('\n') if l.strip()))
        except IOError as e:
            if e[0] == 13: # permission denied
                print('cannot modify %s - make sure its owner is the same as the owner of guacamole.py'
                      % self.filename)
            raise

    def _find_connection_by_port(self, vnc_port):
        for node in self.xml.getElementsByTagName('connection'):
            for child in node.childNodes:
                if (child.nodeName == 'param'
                    and child.getAttribute('name') == 'port'
                    and child.childNodes[0].nodeValue == str(vnc_port)):
                        return node
        return None

    def get_connection_name(self, vnc_port, auto_create=False):
        connection = self._find_connection_by_port(vnc_port)
        if not connection:
            if not auto_create:
                return None
            connection = self._add_connection(vnc_port)
            print('added connection to port %d' % vnc_port)

        return connection.getAttribute('name')

    def _count_connections(self):
        return len(self.xml.getElementsByTagName('connection'))

    def _add_connection(self, vnc_port):
        if self._find_connection_by_port(vnc_port):
            return

        connection = self._create_node(
            'connection',
            attrs=[ ('name', str(self._count_connections())) ],
            children=[
                self._create_node('protocol', value='vnc'),
                self._create_node('param', attrs=[ ('name', 'hostname') ], value='localhost'),
                self._create_node('param', attrs=[ ('name', 'port') ], value=str(vnc_port)),
                self._create_node('param', attrs=[ ('name', 'password') ], value=''),
                self._create_node('param', attrs=[ ('name', 'read-only') ], value='true'),
            ])

        self.xml.getElementsByTagName('authorize')[0].appendChild(connection)
        self.dirty = True

        return connection

def print_usage():
    print('usage: %s get <vnc_port_name>' % sys.argv[0])

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] != 'get':
        print_usage()
        sys.exit(1)

    try:
        port = int(sys.argv[2])
    except ValueError:
        print_usage()
        sys.exit(1)

    config = Config('/etc/guacamole/user-mapping.xml')
    print(config.get_connection_name(port, auto_create=True))
    config.save()

