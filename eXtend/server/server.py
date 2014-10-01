#!/usr/bin/env python

import argparse
import fcntl
import itertools
import json
import os
import re
import setproctitle
import socket
import stat
import struct
import subprocess
import sys
import time
import threading
import traceback

from libs import pymouse
from libs import vnc
from libs import ifutils
from libs.runAndWait import runAndWait

parser = argparse.ArgumentParser()

parser.add_argument('-p', '--port', type = lambda x: int(x, 0))
parser.add_argument('-s', '--start', action = 'store_true')
parser.add_argument('-S', '--stop', action = 'store_true')
parser.add_argument('-o', '--port-web', type = lambda x: int(x, 0))
parser.add_argument('-w', '--start-web', action = 'store_true')
parser.add_argument('-P', '--password-file')
parser.add_argument('-m', '--manual-arrange', action = 'store_true')
parser.add_argument('-l', '--log-file')
parser.add_argument('-i', '--interface')
parser.add_argument('-a', '--arrange', type = lambda x: map(int, x.split(' ')[:3]))

# there's a second "if __name__ == '__main__':" at the end of this file
if __name__ == '__main__':
  parsedArgs = parser.parse_args()
else:
  parsedArgs = parser.parse_args(None)

inetSocketPort = parsedArgs.port if parsedArgs.port != None else 0X7E5D #xtend
inetSocketAddress = ('', inetSocketPort)
inetSocketBacklog = 128
mcastGroup = '224.0.126.93'
mcastPort = inetSocketPort

daemonProcessName = 'eXtend-server_0X%X' % inetSocketPort

daemonSpawnLockFile = os.path.expanduser('~/.' + daemonProcessName + '.lock')

unixSocketPath = os.path.expanduser('~/.' + daemonProcessName + '.socket')
unixSocketBacklog = 128
unixClientSocketConnectTimeout = 5

websocketServer = None

inetSocketsStarted = False

vnc.initPasswordFile(parsedArgs.password_file)

manualArrange = parsedArgs.manual_arrange

logFile = (
  os.path.expanduser(parsedArgs.log_file) if
  parsedArgs.log_file != None else
  os.path.expanduser('~/.' + daemonProcessName + '.log')
)

arrangementSharedMap = {}


def processRunning(name):
  command = 'ps -u `whoami` -o command'
  ps = runAndWait(command)

  return re.findall('\n *' + name + ' *\n', '\n' + ps[0] + '\n') != []

def formatResult(result):
  return reduce(lambda x, y: str(x) + ' : ' + str(y), result)

def suicide():
  print 'commiting suicide...\n'
  if websocketServer:
    websocketServer.kill()

  os.kill(os.getpid(), 1)

def startInetSockets():
  if inetSocketsStarted:
    return 1, 'already started'

  inetSocketStarted = True

  inetAcceptorHandler = threading.Thread(target = handleInetAcceptor)
#  inetAcceptorHandler.daemon = True
  inetAcceptorHandler.start()

  inetMulticastHandler = MouseThread()
#  inetMulticastHandler.daemon = True
  inetMulticastHandler.start()

def arrange(clientId, position):
  arrangementMapEntry = arrangementSharedMap[clientId]
  l = arrangementMapEntry[0]
  arrangementMapEntry[1] = position
  l.release()

def executeCommand(parsedArgs):
  print 'args:\n  ' + '\n  '.join('%s = %s' % x for x in parsedArgs.items())

  returnCode = 0
  errorMessage = 'success'

  result = None

  if parsedArgs['stop']:
    suicide()

  if parsedArgs['start']:
    result = startInetSockets()

  if parsedArgs['start_web']:
    from libs import web_server
    print('starting')
    websocketServer = web_server.start_server('', parsedArgs['port_web'] or (inetSocketPort + 1))
    print('started')

  if parsedArgs['password_file'] != None:
    vnc.initPasswordFile(parsedArgs['password_file'])

  global manualArrange
  manualArrange = parsedArgs['manual_arrange']

  if parsedArgs['arrange'] != None:
    position = [0, 0]
    clientId, position[0], position[1] = parsedArgs['arrange']
    result = arrange(clientId, position)

  if result != None:
    returnCode, errorMessage = result

  return returnCode, errorMessage

def handleUnixClient(unixServerSocket):
  f = unixServerSocket.makefile()

  parsedArgs = json.loads(f.readline())

  try:
    returnCode, errorMessage = executeCommand(parsedArgs)
  except Exception as e:
    returnCode = -1
    errorMessage = traceback.format_exc(e)

  f.write(json.dumps((returnCode, errorMessage)))

  f.close()
  unixServerSocket.close()

def handleUnixAcceptor(unixAcceptorSocket):
  while True:
    unixServerSocket = unixAcceptorSocket.accept()[0]
    print 'new unix socket connection accepted'

    unixClientHandler = threading.Thread(target = handleUnixClient, args = (unixServerSocket, ))
#    unixClientHandler.daemon = True
    unixClientHandler.start()

counter = itertools.count()

def handleInetClient(inetServerSocket):
  f = inetServerSocket.makefile()

  resolution = f.readline().split()

  print resolution

  assert resolution[0] == 'resolution'
  resolution = map(int, resolution[1:])

  clientId = counter.next()
  f.write('id %d\n' % clientId)

  position = None

  if manualArrange:
    l = threading.Lock()
    global arrangementSharedMap
    arrangementSharedMap[clientId] = [l, None]
    print 'client %d waiting for screen position\n' % clientId
    l.acquire()
    l.acquire()
    position = arrangementSharedMap[clientId][1]
    print ('client %d arranged on position ' + str(position) + '\n') % clientId

  output = vnc.initVirtualOutputAndVNC(resolution, position)

  try:
    f.write('vnc %s %d %d %d\n' % ((inetServerSocket.getsockname()[0], output.vncPort) +  output.offset))
    f.close()
    output.vncSubprocess.wait()
  finally:
    vnc.cleanup(output)
    inetServerSocket.close()

def handleInetAcceptor():
  inetAcceptorSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  inetAcceptorSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  inetAcceptorSocket.bind(inetSocketAddress)
  print 'tcp socket bound to %s:0X%X' % (
    'INADDR_ANY' if inetSocketAddress[0] == '' else str(inetSocketAddress[0]), inetSocketAddress[1])

  inetAcceptorSocket.listen(inetSocketBacklog)
  print 'tcp socket started listening'

  while True:
    inetServerSocket, inetClientAddress = inetAcceptorSocket.accept()
    print 'new tcp socket connection accepted from %s:0X%X' % (str(inetClientAddress[0]), inetClientAddress[1])

#    if inetClientAddress not in whitelist: return

    inetClientHandler = threading.Thread(target = handleInetClient, args = (inetServerSocket, ))
#    inetClientHandler.daemon = True
    inetClientHandler.start()

def setupMulticastSocket(multicastGroup, multicastPort):
  sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
  sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)

  if parsedArgs.interface:
    ip = ifutils.get_ip_for_iface(parsedArgs.interface)
    print('using interface %s (%s)' % (parsedArgs.interface, ip))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))

  return sock

class MouseThread(pymouse.PyMouseEvent):
  def __init__(self):
    pymouse.PyMouseEvent.__init__(self)

    global mcastGroup, mcastPort
    self.sock = setupMulticastSocket(mcastGroup, mcastPort)

    self.spammer = threading.Thread(target = self.spam)
    self.spammer.start()

  def wait():
    self.spammer.wait()
    pymouse.PyMouseEvent.wait(self)

  def sendCoords(self, x, y):
    global mcastGroup, mcastPort

    msg = struct.pack('!II', x, y)
    self.sock.sendto(msg, (mcastGroup, mcastPort))

  def move(self, x, y):
    self.sendCoords(x, y)

  def spam(self):
    pm = pymouse.PyMouse()

    while True:
      time.sleep(2.5)
      self.sendCoords(*pm.position())

#def handleInetBroadcast(mcastGroup, mcastPort):
  #sock = setupBroadcastSocket(mcastGroup, mcastPort)

  #print 'udp multicast started on %s:%d' % (mcastGroup, mcastPort)
  #mouse = pymouse.PyMouse()
  #while True:
    #sock.sendto('cursor %d %d\n' % mouse., (mcastGroup, mcastPort))
    #time.sleep(0.02)

def spawnDaemon(func, args):
  try:
    pid = os.fork()
    if pid > 0:
      return
  except OSError, e:
    print >>sys.stderr, "fork #1 failed: %d (%s)" % (e.errno, e.strerror)
    sys.exit(1)

  os.setsid()

  try:
    pid = os.fork()
    if pid > 0:
      sys.exit(0)
  except OSError, e:
    print >>sys.stderr, "fork #2 failed: %d (%s)" % (e.errno, e.strerror)
    sys.exit(1)

  func(*args)

  os._exit(os.EX_OK)

def daemon(daemonSpawnLock):
  setproctitle.setproctitle(daemonProcessName)
  print 'starting eXtend-server daemon'

  for i in [1, 2]:
    os.close(i)
    os.open(logFile, os.O_CREAT | os.O_WRONLY | os.O_APPEND)

  print '\n' + '#' * 50 + '\n'

  if os.path.exists(unixSocketPath):
    if stat.S_ISSOCK(os.stat(unixSocketPath).st_mode):
      os.unlink(unixSocketPath)
    else:
      raise Exception(unixSocketPath + ' already exists and is not a socket')

  unixAcceptorSocket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  unixAcceptorSocket.bind(unixSocketPath)
  print 'unix socket bound to ' + unixSocketPath

  os.close(daemonSpawnLock) # release lock, fcntl.flock(daemonSpawnLock, fcntl.LOCK_UN) happens automatically on close

  unixAcceptorSocket.listen(unixSocketBacklog)
  print 'unix socket started listening'

  unixAcceptorHandler = threading.Thread(target = handleUnixAcceptor, args = (unixAcceptorSocket, ))
#  unixAcceptorHandler.daemon = True
  unixAcceptorHandler.start()

  unixAcceptorHandler.join()


if __name__ == '__main__':

  daemonSpawnLock = os.open(daemonSpawnLockFile, os.O_CREAT)

  hasDaemonSpawnLock = False
  try:
    fcntl.flock(daemonSpawnLock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    hasDaemonSpawnLock = True
  except OSError as e:
    if e.errno != 11: raise # not 'Resource temporarily unavailable'
  if hasDaemonSpawnLock and not processRunning(daemonProcessName):
    spawnDaemon(daemon, (daemonSpawnLock, ))

  os.close(daemonSpawnLock)

  daemonSpawnLock = os.open(daemonSpawnLockFile, 0)
  fcntl.flock(daemonSpawnLock, fcntl.LOCK_SH) # Ensure that the daemon's AF_UNIX socket is bound
  os.close(daemonSpawnLock)

  unixClientSocket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  unixClientSocket.settimeout(unixClientSocketConnectTimeout)
  unixClientSocket.connect(unixSocketPath)
  unixClientSocket.settimeout(None)
  unixClientSocketFile = unixClientSocket.makefile()

  unixClientSocketFile.write(json.dumps(vars(parsedArgs), separators=(',',':')) + '\n')
  unixClientSocketFile.flush()

  if not parsedArgs.stop:
    result = returnCode, errorMessage = json.loads(unixClientSocketFile.read())

    print formatResult(result)

    unixClientSocketFile.close()
    unixClientSocket.close()

    sys.exit(returnCode)

