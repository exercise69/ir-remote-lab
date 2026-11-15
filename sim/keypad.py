"""Attrappe fuer keypad: der Taster wird nie gedrueckt."""


class Event:
    pressed = False
    released = False


class _Queue:
    def get_into(self, event):
        return False


class Keys:
    def __init__(self, pins, value_when_pressed=False, pull=True):
        self.events = _Queue()
