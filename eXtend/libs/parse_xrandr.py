
from runAndWait import runAndWait

import re

def parse_xrandr():
    rawOut, _, returnCode = runAndWait('xrandr')
    rawOutputs = re.findall('\n([A-Z]+\d+.*)', rawOut)

    outputs = {}
    for rawOutput in rawOutputs:
      splittedRawOutput = rawOutput.split()

      name = splittedRawOutput[0]

      coords = re.findall('(\d+)x(\d+)\+(\d+)\+(\d+)', rawOutput)
      coords = None if coords == [] else tuple(map(int, coords[0]))

      outputs[name] = {
        'name' : name,
        'connected' : splittedRawOutput[1] == 'connected',
        'coords' : coords
      }

    screenSize = tuple(map(int, re.findall('current (\d+) x (\d+)', rawOut)[0]))

    return screenSize, outputs

