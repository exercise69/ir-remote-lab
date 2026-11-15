"""Attrappe fuer wifi: immer verbunden, Adresse localhost."""


class _AP:
    ssid = "Simulation"


class _Radio:
    connected = True
    ipv4_address = "127.0.0.1"
    ap_info = _AP()


radio = _Radio()
