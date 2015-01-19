
import subprocess

def runAndWait(cmd, silent = False, stdin = None):
  process = subprocess.Popen(cmd, shell=True,
                             stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE)

  if stdin:
    process.stdin.write(stdin)
  process.stdin.close()

  ret = process.stdout.read(), process.stderr.read(), process.wait()

  if not silent:
    print '%s : %d' % (cmd, ret[2])

  return ret

