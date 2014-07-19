#!/usr/bin/env python

import json
import os
import re
import socket
import stat
import subprocess
import sys
import threading

import setproctitle

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


daemonProcessName = 'eXtend-server'

unixSocketPath = os.path.expanduser('~/.' + daemonProcessName + '.socket')
unixSocketBacklog = 128
unixClientSocketConnectTimeout = 5


if __name__ == '__main__':

  if not processRunning(daemonProcessName):
    setproctitle.setproctitle(daemonProcessName)
    print 'becoming eXtend-server daemon'

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
#    initialCommandExecutor.daemon = True
    initialCommandExecutor.start()

    unixAcceptorHandler = threading.Thread(target = handleUnixAcceptor, args = (unixAcceptorSocket, ))
#    unixAcceptorHandler.daemon = True
    unixAcceptorHandler.start()

    for t in [initialCommandExecutor,
              unixAcceptorHandler]:
      t.join()


  else:
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

