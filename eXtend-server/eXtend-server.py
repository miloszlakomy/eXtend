#!/usr/bin/env python

import errno
import os
import re
import setproctitle
import stat
import subprocess
import sys

def fifoExists(path):
  if not os.path.exists(path):
    return False

  return stat.S_ISFIFO(os.stat(path).st_mode)

def runAndWait(cmd):
  process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
  process.wait()
  return process.stdout.read()

def processRunning(name):
  ps = runAndWait('ps -u `whoami` o command')
  found = re.findall('\n\s*' + name + '\s*\n', ps)

  return found != []

class FifoReader:
  def __init__(self, fifoPath):
    self.fifo = None
    self.fifoPath = fifoPath
    self.open()

  def __del__(self):
    self.close()

  def mkfifo(self):
    os.mkfifo(self.fifoPath)

  def open(self):
    try:
      self.fifo = open(self.fifoPath)
    except IOError as e:
      if e.errno == errno.ENOENT:
        self.mkfifo()
        self.open()
      else:
        raise

  def close(self):
    if self.fifo != None:
      self.fifo.close()

  def readline(self):
    line = self.fifo.readline()

    while line == '':
      self.close()
      self.open()
      line = self.fifo.readline()

    return line

daemonProcessName = 'eXtend-server'
fifoPath = os.path.expanduser('~/.' + daemonProcessName + '.pipe')

if __name__ == '__main__':

  if not processRunning(daemonProcessName):
    setproctitle.setproctitle(daemonProcessName)
    print 'eXtend-server daemon started'

    fr = FifoReader(fifoPath)

    while True:
      print fr.readline()


  else:
    if fifoExists(fifoPath):
      fifoHandle = open(fifoPath, 'w')
      fifoHandle.write(str(sys.argv[1:]))

