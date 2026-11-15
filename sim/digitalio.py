"""Attrappe fuer digitalio."""


class DigitalInOut:
    def __init__(self, pin):
        self.pin, self.value = pin, False

    def deinit(self):
        pass
