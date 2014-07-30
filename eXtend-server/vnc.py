
class VirtualOutput(object):
  def __init__(self, resolution, vnsSubprocess, vncPort, virtualOutputNum):
    self.resolution = resolution
    self.vnsSubprocess = vnsSubprocess
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

  return outputNum

def initVNC(resolution):
  sp = subprocess.Popen([
    vncCmd,
    '-clip', '%dx%d+%d+0' % (resolution[0], resolution[1], screensize[0]),
    '--passwdfile', vncPasswordFile,
    '-viewonly', '-q'],
    stdout = subprocess.PIPE)

  time.sleep(5) #TODO

  vncPort = ''
  while vncPort[:5] != 'PORT=':
    vncPort = sp.stdout.readline()

  print vncPort
  vncPort = int(vncPort[5:-1])

  return sp, vncPort

def initVirtualOutputAndVNC(resolution):
  outputNum = initVirtualOutput(resolution)
  vncSubprocess, vncPort = initVNC(resolution)

  return VirtualOutput(resolution, vncSubprocess, vncPort, outputNum)

def cleanup(virtualOutput):
  if not virtualOutput.vncSubprocess.poll():
    virtualOutput.vncSubprocess.terminate()

  virtualOutput.vncSubprocess.wait()
  xrandr('--output VIRTUAL%d --off' % virtualOutput.virtualOutputNum)

