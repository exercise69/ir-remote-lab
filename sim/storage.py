"""Attrappe fuer storage."""


def mount(*a, **k):
    raise OSError("keine SD-Karte im Simulator")


def VfsFat(*a, **k):
    raise OSError("keine SD-Karte im Simulator")
