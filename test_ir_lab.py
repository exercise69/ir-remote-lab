# Tests fuer ir_lab.py, laufen auf dem Mac: python3 test_ir_lab.py
# (kommt nicht aufs Board)

import unittest

from ir_lab import (best_frame, carrier_khz, code_pulses, compare_echo, majority,
                       nearest_std, parse_khz, parse_pulses, pick_networks,
                       same_frame, split_frames, strip_idle)


def tsmp_bursts(khz, bursts, cycles=20, gap=600, low=9):
    """Simuliert TSMP-Ausgabe: pro Traegerperiode ein LOW-Puls, dazwischen HIGH."""
    period = 1000 / khz
    out = []
    t = 0.0
    edges = []
    for b in range(bursts):
        for c in range(cycles):
            edges.append(t)
            t += period
        t += gap
    # LOW-Beginn-Zeitpunkte auf ganze us runden wie PulseIn
    for i, e in enumerate(edges):
        out.append(low)
        if i + 1 < len(edges):
            out.append(round(edges[i + 1]) - round(e) - low)
    return out


class CarrierTest(unittest.TestCase):
    def test_36_khz(self):
        f, bursts = carrier_khz(tsmp_bursts(36, 5))
        self.assertEqual(len(bursts), 5)
        self.assertAlmostEqual(f, 36.0, delta=0.3)

    def test_38_khz(self):
        f, _ = carrier_khz(tsmp_bursts(38, 3))
        self.assertAlmostEqual(f, 38.0, delta=0.3)
        self.assertEqual(nearest_std(f), 38)

    def test_ends_with_high(self):
        p = tsmp_bursts(36, 2)
        p.append(5)  # kurzes HIGH am Ende
        f, bursts = carrier_khz(p)
        self.assertEqual(len(bursts), 2)

    def test_empty_and_noise(self):
        self.assertEqual(carrier_khz([]), (None, []))
        self.assertEqual(carrier_khz([5, 3000, 5]), (None, []))


class EchoTest(unittest.TestCase):
    SENT = [3000, 1500, 500, 500, 500, 1500, 500]

    def test_ok(self):
        got = [3080, 1420, 560, 440, 570, 1430, 560]
        r = compare_echo(self.SENT, got, 36.0, 36.05)
        self.assertTrue(r["ok"], r["text"])
        self.assertEqual(r["max_dev"], 80)

    def test_nothing(self):
        r = compare_echo(self.SENT, [], 36.0, None)
        self.assertFalse(r["ok"])
        self.assertIn("nichts", r["text"])

    def test_wrong_count(self):
        r = compare_echo(self.SENT, [3000, 1500, 500], 36.0, 36.0)
        self.assertFalse(r["ok"])
        self.assertIn("3 statt 7", r["text"])

    def test_wrong_freq(self):
        r = compare_echo(self.SENT, list(self.SENT), 36.0, 38.0)
        self.assertFalse(r["ok"])

    def test_esp32_end_marker(self):
        # echte Aufnahme vom Board: PulseIn haengt 65535 an
        got = strip_idle([3010, 1488, 512, 488, 514, 1488, 520, 65535])
        self.assertEqual(len(got), 7)
        r = compare_echo(self.SENT, got, 36.0, 35.96)
        self.assertTrue(r["ok"], r["text"])
        self.assertEqual(strip_idle([]), [])


class ParseTest(unittest.TestCase):
    def test_console_format(self):
        self.assertEqual(parse_pulses("[9000, 4500, 560]"), [9000, 4500, 560])

    def test_lines(self):
        self.assertEqual(parse_pulses("9000 4500\n560"), [9000, 4500, 560])

    def test_errors(self):
        for bad in ("", "abc", "0", "70000"):
            with self.assertRaises(ValueError):
                parse_pulses(bad)

    def test_khz(self):
        self.assertEqual(parse_khz("", 36), 36)
        self.assertEqual(parse_khz("38", 36), 38.0)
        with self.assertRaises(ValueError):
            parse_khz("100", 36)



class PickNetworksTest(unittest.TestCase):
    KNOWN = [("Buero", "pw1"), ("Zuhause", "pw2"), ("Handy", "pw3")]

    def test_nur_sichtbare_bekannte(self):
        seen = [("Nachbar", -40), ("Zuhause", -60)]
        self.assertEqual(pick_networks(self.KNOWN, seen), [("Zuhause", "pw2")])

    def test_staerkstes_zuerst(self):
        seen = [("Buero", -80), ("Handy", -50), ("Zuhause", -65)]
        self.assertEqual([s for s, _ in pick_networks(self.KNOWN, seen)],
                         ["Handy", "Zuhause", "Buero"])

    def test_mehrere_access_points_bester_zaehlt(self):
        seen = [("Buero", -85), ("Zuhause", -70), ("Buero", -55)]
        self.assertEqual(pick_networks(self.KNOWN, seen)[0][0], "Buero")

    def test_gleich_stark_prioritaet_entscheidet(self):
        seen = [("Handy", -60), ("Buero", -60)]
        self.assertEqual(pick_networks(self.KNOWN, seen)[0][0], "Buero")

    def test_nichts_bekanntes(self):
        self.assertEqual(pick_networks(self.KNOWN, [("Fremd", -30)]), [])


# echte Aufnahme An/Aus vom 2026-11-14 (3 Pakete)
ANAUS = [310, 286, 336, 286, 338, 622, 618, 286, 338, 620, 620, 622, 620, 624, 310, 286, 336, 284,
         646, 620, 622, 622, 618, 65535, 312, 284, 334, 290, 334, 622, 618, 288, 336, 622, 618, 624,
         618, 624, 310, 286, 336, 284, 646, 622, 620, 622, 618, 65535, 312, 284, 334, 286, 336, 622,
         620, 286, 336, 622, 620, 622, 618, 626, 308, 286, 338, 284, 646, 622, 618, 622, 620]
# Licht unten, erstes Paket mit verkuerztem Anfang (234 statt ~310)
LICHT = [234, 284, 338, 284, 334, 624, 618, 286, 336, 622, 620, 624, 618, 624, 310, 284, 646, 624,
         310, 284, 646, 284, 338, 622, 312, 65535, 310, 286, 336, 284, 340, 620, 620, 284, 334, 624,
         622, 620, 622, 622, 312, 284, 646, 622, 312, 282, 648, 284, 334, 624, 310]


class LearnTest(unittest.TestCase):
    def test_split(self):
        f = split_frames(ANAUS)
        self.assertEqual([len(x) for x in f], [23, 23, 23])

    def test_best_frame_nimmt_zweites(self):
        self.assertEqual(best_frame(LICHT)[0], 310)
        self.assertEqual(len(best_frame(LICHT)), 25)

    def test_best_frame_einzeln_und_leer(self):
        self.assertEqual(best_frame([300, 300, 600]), [300, 300, 600])
        self.assertEqual(best_frame([]), [])

    def test_same_frame(self):
        a, b, c = split_frames(ANAUS)
        self.assertTrue(same_frame(a, b) and same_frame(b, c))
        self.assertFalse(same_frame(best_frame(ANAUS), best_frame(LICHT)))
        self.assertFalse(same_frame([], []))

    def test_majority(self):
        an, li = best_frame(ANAUS), best_frame(LICHT)
        self.assertEqual(majority([li, an, an]), (1, 2))
        self.assertEqual(majority([]), (-1, 0))

    def test_code_pulses(self):
        f = best_frame(ANAUS)
        out = code_pulses(f)
        self.assertEqual(len(out), 3 * 23 + 2)
        self.assertEqual(split_frames(out), [f, f, f])
        self.assertEqual(len(out) % 2, 1)     # endet mit "an"

if __name__ == "__main__":
    unittest.main()
