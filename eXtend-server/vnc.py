from cvt import cvt
from parse_xrandr import parse_xrandr
from runAndWait import runAndWait

import time
import subprocess
import traceback
import os

passwordFile = None

class VirtualOutput(object):
  def __init__(self,
               virtualOutputNum,
               resolution = (0, 0),
               offset = (0, 0),
               vncSubprocess = None,
               vncPort = None):
    self.resolution = resolution
    self.virtualOutputNum = virtualOutputNum
    self.offset = offset
    self.vncSubprocess = vncSubprocess
    self.vncPort = vncPort

def initVirtualOutput(resolution, position, outputs):
  modename, modeline = cvt(resolution[0], resolution[1])

  outputNum = 1
  while outputs['VIRTUAL%d' % outputNum]['coords'] != None:
    outputNum += 1

  xrandr = lambda cmd = '': runAndWait('xrandr ' + cmd)
  xrandr('--newmode %s' % modeline)
  xrandr('--addmode VIRTUAL%d %s' % (outputNum, modename))
  time.sleep(1) #TODO investigate
  xrandr('--output VIRTUAL%d --mode %s --pos %dx%d' % (outputNum, modename, position[0], position[1]))
  time.sleep(1) #TODO investigate

  return outputNum

def initVNC(resolution, screensize, position):
  args = [
    'x11vnc',
    '-clip', '%dx%d+%d+%d' % (resolution[0], resolution[1], position[0], position[1]),
    '-viewonly', '-q'
  ]

  global passwordFile
  if passwordFile:
    args += [ '-passwdfile', passwordFile ]

  print(args)

  sp = subprocess.Popen(args, stdout = subprocess.PIPE)
  time.sleep(5) #TODO

  vncPort = ''
  while vncPort[:5] != 'PORT=':
    vncPort = sp.stdout.readline()

  print vncPort
  vncPort = int(vncPort[5:-1])

  return sp, vncPort

def initVirtualOutputAndVNC(resolution, position):
  screensize, outputs = parse_xrandr()

  if position == None:
    position = (screensize[0], 0)

  outputNum = initVirtualOutput(resolution, position, outputs)
  try:
    vncSubprocess, vncPort = initVNC(resolution, screensize, position)
  except:
    print('cannot initialize VNC, cleaning up output %d' % outputNum)
    cleanup(VirtualOutput(virtualOutputNum=outputNum))
    raise

  return VirtualOutput(resolution=resolution,
                       virtualOutputNum=outputNum,
                       offset=(screensize[0], 0),
                       vncSubprocess=vncSubprocess,
                       vncPort=vncPort)

def cleanup(virtualOutput):
  if virtualOutput.vncSubprocess:
    if virtualOutput.vncSubprocess.poll() is None:
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

