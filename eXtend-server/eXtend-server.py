#!/usr/bin/env python

import fcntl
import json
import os
import re
import socket
import stat
import subprocess
import sys
import time
import threading
import pymouse

import setproctitle


inetSocketPort = 0X7E5D #xtend
inetSocketAddress = ('', inetSocketPort)
inetSocketBacklog = 128
mcastGroup = '224.0.126.93'
mcastPort = inetSocketPort

daemonProcessName = 'eXtend-server_0X%X' % inetSocketPort

daemonSpawnLockFile = os.path.expanduser('~/.' + daemonProcessName + '.lock')

unixSocketPath = os.path.expanduser('~/.' + daemonProcessName + '.socket')
unixSocketBacklog = 128
unixClientSocketConnectTimeout = 5

vncServerCommand = 'x11vnc'


def runAndWait(cmd):
  process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
  return process.stdout.read(), process.wait()

def processRunning(name):
  command = 'ps -u `whoami` -o command'
  ps = runAndWait(command)

  return re.findall('\n *' + name + ' *\n', '\n' + ps[0] + '\n') != []

def formatResult(result):
  return reduce(lambda x, y: str(x) + ' : ' + str(y), result)

def executeCommand(args):
  print args

  returnCode = 0
  errorMessage = 'success'
  return returnCode, errorMessage

def handleUnixClient(unixServerSocket):
  f = unixServerSocket.makefile()

  args = json.loads(f.readline())

  returnCode, errorMessage = executeCommand(args)

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

def handleInetClient(inetServerSocket):
  f = inetServerSocket.makefile()

  resolution = f.readline()

  print resolution

#  f.write(adres? i port vnc)

  print resolution.split()
  sp = subprocess.Popen('../eXtend_alpha_server %s %s $DISPLAY' % (resolution.split()[1], resolution.split()[2]), shell=True) #TODO
  time.sleep(5) #TODO
  f.write('vnc %s 5900 0 0\n' % inetServerSocket.getsockname()[0])
  f.flush()
  f.close()

  sp.wait()

  inetServerSocket.close()

def handleInetAcceptor(inetAcceptorSocket):
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
  return sock

class MouseThread(pymouse.PyMouseEvent):
  def __init__(self):
    pymouse.PyMouseEvent.__init__(self)

    global mcastGroup, mcastPort
    self.sock = setupMulticastSocket(mcastGroup, mcastPort)
    self.lastEventTime = time.time()

  def move(self, x, y):
    global mcastGroup, mcastPort
    currEventTime = time.time()
    if currEventTime - self.lastEventTime > 0.03:
      self.lastEventTime = currEventTime
      self.sock.sendto('cursor %d %d\n' % (x, y), (mcastGroup, mcastPort))

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

  inetAcceptorSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  inetAcceptorSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  inetAcceptorSocket.bind(inetSocketAddress)
  print 'tcp socket bound to %s:0X%X' % (
    'INADDR_ANY' if inetSocketAddress[0] == '' else str(inetSocketAddress[0]), inetSocketAddress[1])

  inetAcceptorSocket.listen(inetSocketBacklog)
  print 'tcp socket started listening'

  inetAcceptorHandler = threading.Thread(target = handleInetAcceptor, args = (inetAcceptorSocket, ))
#  inetAcceptorHandler.daemon = True
  inetAcceptorHandler.start()

  jsAcceptorSocket

  inetMulticastHandler = MouseThread()
  #threading.Thread(target = handleInetBroadcast,
                                          #args = (multicastGroup, multicastPort))
#  inetMulticastHandler.daemon = True
  inetMulticastHandler.start()

  for t in [unixAcceptorHandler,
            inetAcceptorHandler,
            inetMulticastHandler]:
    t.join()


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

  unixClientSocketFile.write(json.dumps(sys.argv[1:], separators=(',',':')) + '\n')
  unixClientSocketFile.flush()

  result = returnCode, errorMessage = json.loads(unixClientSocketFile.read())

  print formatResult(result)

  unixClientSocketFile.close()
  unixClientSocket.close()

  sys.exit(returnCode)

