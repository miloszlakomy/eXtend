
from runAndWait import runAndWait

def cvt(x, y):
  output, _, returnCode = runAndWait('cvt %d %d' % (x, y))

  modeline = output.split('\n')[-2]
  modeline = modeline[modeline.find(' ')+1:]

  modename = modeline[:modeline.find(' ')]

  return modename, modeline

