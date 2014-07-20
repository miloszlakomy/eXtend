#!/usr/bin/env python

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


daemonProcessName = 'eXtend-server'

unixSocketPath = os.path.expanduser('~/.' + daemonProcessName + '.socket')
unixSocketBacklog = 128
unixClientSocketConnectTimeout = 5

inetSocketPort = 0X7E5D #xtend
inetSocketAddress = ('', inetSocketPort)
inetSocketBacklog = 128


def runAndWait(cmd):
  process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
  return process.stdout.read(), process.wait()

def processRunning(name):
  ps = runAndWait('pgrep -u `whoami` ' + name)

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
    print 'new inet socket connection accepted from ' + str(inetClientAddress)

#    if inetClientAddress not in whitelist: return

    inetClientHandler = threading.Thread(target = handleInetClient, args = (inetServerSocket, ))
#    inetClientHandler.daemon = True
    inetClientHandler.start()

def spawnDaemon(func):
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

  func()

  os._exit(os.EX_OK)

def daemon():
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
  print 'inet socket bound to ' + str(inetSocketAddress)

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

  if not processRunning(daemonProcessName):
    spawnDaemon(daemon)


  while not os.path.exists(unixSocketPath):
    time.sleep(1)

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

