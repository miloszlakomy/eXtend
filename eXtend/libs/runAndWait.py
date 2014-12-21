
import subprocess

def runAndWait(cmd, silent = False):
  process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)

  ret = process.stdout.read(), process.wait()

  if not silent:
    print '%s : %d' % (cmd, ret[1])

  return ret

