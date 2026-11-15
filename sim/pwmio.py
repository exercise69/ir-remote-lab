"""Attrappe fuer pwmio: die LED tut nichts."""


class PWMOut:
    def __init__(self, pin, frequency=500, duty_cycle=0):
        self.duty_cycle = duty_cycle
