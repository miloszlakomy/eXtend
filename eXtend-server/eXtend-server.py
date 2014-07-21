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

import setproctitle


inetSocketPort = 0X7E5D #xtend
inetSocketAddress = ('', inetSocketPort)
inetSocketBacklog = 128

daemonProcessName = 'eXtend-server_0X%X' % inetSocketPort

daemonSpawnLockFile = os.path.expanduser('~/.' + daemonProcessName + '.lock')

unixSocketPath = os.path.expanduser('~/.' + daemonProcessName + '.socket')
unixSocketBacklog = 128
unixClientSocketConnectTimeout = 5


def runAndWait(cmd):
  process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
  return process.stdout.read(), process.wait()

def processRunning(name):
  command = 'ps -u `whoami` -o command | grep \'^ *%s *$\'' % name
  ps = runAndWait(command)

  return ps[1] == 0

def formatResult(result):
  return reduce(lambda x, y: str(x) + ' : ' + str(y), result)

def initialCommandHandler(args):
  result = returnCode, errorMessage = executeCommand(args)
  print formatResult(result)

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

  f.close()
  inetServerSocket.close()

def handleInetAcceptor(inetAcceptorSocket):
  while True:
    inetServerSocket, inetClientAddress = inetAcceptorSocket.accept()
    print 'new inet socket connection accepted from %s:0X%X' % (str(inetClientAddress[0]), inetClientAddress[1])

#    if inetClientAddress not in whitelist: return

    inetClientHandler = threading.Thread(target = handleInetClient, args = (inetServerSocket, ))
#    inetClientHandler.daemon = True
    inetClientHandler.start()

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

  initialCommandExecutor = threading.Thread(target = initialCommandHandler, args = (sys.argv[1:], ))
#  initialCommandExecutor.daemon = True
  initialCommandExecutor.start()

  unixAcceptorHandler = threading.Thread(target = handleUnixAcceptor, args = (unixAcceptorSocket, ))
#  unixAcceptorHandler.daemon = True
  unixAcceptorHandler.start()

  inetAcceptorSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  inetAcceptorSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  inetAcceptorSocket.bind(inetSocketAddress)
  print 'inet socket bound to %s:0X%X' % (
    'INADDR_ANY' if inetSocketAddress[0] == '' else str(inetSocketAddress[0]), inetSocketAddress[1])

  inetAcceptorSocket.listen(inetSocketBacklog)
  print 'inet socket started listening'

  inetAcceptorHandler = threading.Thread(target = handleInetAcceptor, args = (inetAcceptorSocket, ))
#  inetAcceptorHandler.daemon = True
  inetAcceptorHandler.start()

  for t in [initialCommandExecutor,
            unixAcceptorHandler,
            inetAcceptorHandler]:
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

