#!/usr/bin/env python

from cvt import cvt
from runAndWait import runAndWait
from parse_xrandr import parse_xrandr

import argparse
import fcntl
import json
import os
import re
import socket
import stat
import struct
import subprocess
import sys
import time
import threading

import pymouse
import setproctitle


parser = argparse.ArgumentParser()

parser.add_argument('-p', '--port', type = lambda x: int(x, 0))
parser.add_argument('-s', '--start', action = 'store_true')
parser.add_argument('-S', '--stop', action = 'store_true')
parser.add_argument('-P', '--password-file')

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

inetSocketsStarted = False

vncCmd = 'x11vnc -q'

vncPasswordFile = parsedArgs.password_file if parsedArgs.password_file else os.path.expanduser('~/.eXtend_vncPwd')
if not os.path.exists(vncPasswordFile):
  fd = os.open(vncPasswordFile, os.O_WRONLY | os.O_CREAT, 0600)
  os.write(fd, 'lubieplacki')
  os.close(fd)


def processRunning(name):
  command = 'ps -u `whoami` -o command'
  ps = runAndWait(command)

  return re.findall('\n *' + name + ' *\n', '\n' + ps[0] + '\n') != []

def formatResult(result):
  return reduce(lambda x, y: str(x) + ' : ' + str(y), result)

def suicide():
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

def executeCommand(parsedArgs):
  print parsedArgs

  returnCode = 0
  errorMessage = 'success'

  result = None
  if parsedArgs['stop']: suicide()
  if parsedArgs['start']: result = startInetSockets()

  if result != None:
    returnCode, errorMessage = result

  return returnCode, errorMessage

def handleUnixClient(unixServerSocket):
  f = unixServerSocket.makefile()

  parsedArgs = json.loads(f.readline())

  returnCode, errorMessage = executeCommand(parsedArgs)

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

  resolution = f.readline().split()

  print resolution

  assert resolution[0] == 'resolution'
  resolution = map(int, resolution[1:])

  modename, modeline = cvt(resolution[0], resolution[1])

  screensize, outputs = parse_xrandr()

  outputNum = 1
  while outputs['VIRTUAL%d' % outputNum]['coords'] != None: outputNum += 1

  xrandr = lambda cmd = '': runAndWait('xrandr ' + cmd)
  xrandr('--newmode %s' % modeline)
  xrandr('--addmode VIRTUAL%d %s' % (outputNum, modename))
  xrandr('--output VIRTUAL%d --mode %s --pos %dx0' % (outputNum, modename, screensize[0]))

  sp = subprocess.Popen('%s -clip %dx%d+%d+0' % (vncCmd, resolution[0], resolution[1], screensize[0]), shell=True)

#  sp = subprocess.Popen('../eXtend_alpha_server %s %s $DISPLAY' % (resolution.split()[1], resolution.split()[2]), shell=True) #TODO
  time.sleep(5) #TODO
  f.write('vnc %s 5900 %d 0\n' % (inetServerSocket.getsockname()[0], screensize[0])) #TODO

  f.close()

  sp.wait()

  xrandr('--output VIRTUAL%d --off' % outputNum)

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

