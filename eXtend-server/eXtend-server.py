#!/usr/bin/env python

import json
import os
import re
import socket
import stat
import subprocess
import sys

import setproctitle

def runAndWait(cmd):
  process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
  process.wait()
  return process.stdout.read()

def processRunning(name):
  ps = runAndWait('ps -u `whoami` o command')
  found = re.findall('\n\s*' + name + '\s*\n', ps)

  return found != []

def handleClient(unixServerSocket):
  print json.loads(unixServerSocket.makefile().read())

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

    while True:
      unixServerSocket = unixAcceptorSocket.accept()[0]
      print 'new unix socket connection accepted'
      handleClient(unixServerSocket)


  else:
    unixClientSocket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    unixClientSocket.settimeout(unixClientSocketConnectTimeout)
    unixClientSocket.connect(unixSocketPath)
    unixClientSocket.settimeout(None)
    unixClientSocketFile = unixClientSocket.makefile()

    unixClientSocketFile.write(json.dumps(sys.argv[1:], separators=(',',':')))

