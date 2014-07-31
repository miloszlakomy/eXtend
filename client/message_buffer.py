
class MessageBuffer(object):
    def __init__(self):
        self.messages = []
        self.data = ''

    def update(self, data):
        self.data += data

        lines = self.data.split('\n')
        self.data = lines[-1]
        self.messages += [ line for line in lines[:-1] ]

    def __iter__(self):
        return self

    def next(self):
        if not self.messages:
            raise StopIteration

        ret = self.messages[0]
        self.messages.pop(0)
        return ret

