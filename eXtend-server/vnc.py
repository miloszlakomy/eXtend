from cvt import cvt
from parse_xrandr import parse_xrandr
from runAndWait import runAndWait

import time
import subprocess
import traceback
import os

passwordFile = None

class VirtualOutput(object):
  def __init__(self, resolution, vncSubprocess, vncPort, virtualOutputNum):
    self.resolution = resolution
    self.vncSubprocess = vncSubprocess
    self.vncPort = vncPort
    self.virtualOutputNum = virtualOutputNum

def initVirtualOutput(resolution):
  modename, modeline = cvt(resolution[0], resolution[1])
  screensize, outputs = parse_xrandr()

  outputNum = 1
  while outputs['VIRTUAL%d' % outputNum]['coords'] != None:
    outputNum += 1

  xrandr = lambda cmd = '': runAndWait('xrandr ' + cmd)
  xrandr('--newmode %s' % modeline)
  xrandr('--addmode VIRTUAL%d %s' % (outputNum, modename))
  time.sleep(1) #TODO investigate
  xrandr('--output VIRTUAL%d --mode %s --pos %dx0' % (outputNum, modename, screensize[0]))
  time.sleep(1) #TODO investigate

  return outputNum, screensize

def initVNC(resolution, screensize):
  args = [ 
    'x11vnc'
    '-clip', '%dx%d+%d+0' % (resolution[0], resolution[1], screensize[0]),
    '-viewonly', '-q'
  ]

  global passwordFile
  if passwordFile:
    args += [ '--passwdfile', vncPasswordFile ]

  sp = subprocess.Popen(args, stdout = subprocess.PIPE)
  time.sleep(5) #TODO

  vncPort = ''
  while vncPort[:5] != 'PORT=':
    vncPort = sp.stdout.readline()

  print vncPort
  vncPort = int(vncPort[5:-1])

  return sp, vncPort

def initVirtualOutputAndVNC(resolution):
  outputNum, screenSize = initVirtualOutput(resolution)
  try:
    vncSubprocess, vncPort = initVNC(resolution, screenSize)
  except:
    print('cannot initialize VNC, cleaning up output %d' % outputNum)
    cleanup(VirtualOutput(resolution, None, None, outputNum))
    raise

  return VirtualOutput(resolution, vncSubprocess, vncPort, outputNum)

def cleanup(virtualOutput):
  if virtualOutput.vncSubprocess:
    if not virtualOutput.vncSubprocess.poll():
      virtualOutput.vncSubprocess.terminate()

    virtualOutput.vncSubprocess.wait()

  if virtualOutput.virtualOutputNum is not None:
    runAndWait('xrandr --output VIRTUAL%d --off' % virtualOutput.virtualOutputNum)

def initPasswordFile(newFile):
  global passwordFile

  if newFile:
    passwordFile = newFile
  else:
    passwordFile = os.path.expanduser('~/.eXtend_vncPwd')
    if not os.path.exists(passwordFile):
      fd = os.open(passwordFile, os.O_WRONLY | os.O_CREAT, 0600)
      os.write(fd, 'lubieplacki')
      os.close(fd)

