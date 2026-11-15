"""Attrappe fuer supervisor: Konsolenbefehle nur, wenn stdin ein Terminal ist."""
import select
import sys


class _Runtime:
    @property
    def serial_bytes_available(self):
        if not sys.stdin.isatty():
            return 0
        return 1 if select.select([sys.stdin], [], [], 0)[0] else 0


runtime = _Runtime()
