
import subprocess

def runAndWait(cmd):
  process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)

  ret = process.stdout.read(), process.wait()
  print '%s : %d' % (cmd, ret[1])


  return ret

