# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from dterrain.route import parse_route


def _write(tmp, name, content):
    p = Path(tmp) / name
    p.write_text(content, encoding="utf-8")
    return str(p)


class TestRoute(unittest.TestCase):
    def test_parse_gpx(self):
        gpx = (
            '<?xml version="1.0"?>\n'
            '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">\n'
            ' <trk><trkseg>\n'
            '  <trkpt lat="40.0" lon="116.0"><ele>100</ele><time>2024-01-01T00:00:00Z</time></trkpt>\n'
            '  <trkpt lat="40.001" lon="116.001"><ele>101</ele><time>2024-01-01T00:00:01Z</time></trkpt>\n'
            ' </trkseg></trk>\n'
            '</gpx>'
        )
        with tempfile.TemporaryDirectory() as d:
            pts = parse_route(_write(d, "a.gpx", gpx))
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0].lat, 40.0)
        self.assertAlmostEqual(pts[0].lon, 116.0)
        self.assertAlmostEqual(pts[0].alt, 100)
        self.assertIsNotNone(pts[0].time)

    def test_parse_csv_with_time(self):
        csv = "time,lat,lon,alt\n0,40.0,116.0,100\n1,40.001,116.001,101\n"
        with tempfile.TemporaryDirectory() as d:
            pts = parse_route(_write(d, "a.csv", csv))
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[1].lat, 40.001)
        self.assertAlmostEqual(pts[0].time, 0.0)

    def test_parse_csv_header_aliases(self):
        csv = "timestamp,latitude,longitude\n0,30.0,120.0\n1,30.1,120.1\n"
        with tempfile.TemporaryDirectory() as d:
            pts = parse_route(_write(d, "a.csv", csv))
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0].lat, 30.0)
        self.assertAlmostEqual(pts[0].lon, 120.0)

    def test_parse_kml(self):
        kml = (
            '<?xml version="1.0"?>\n'
            '<kml xmlns="http://www.opengis.net/kml/2.2">\n'
            ' <Placemark><LineString><coordinates>\n'
            ' 116.0,40.0,100 116.001,40.001,101\n'
            ' </coordinates></LineString></Placemark>\n'
            '</kml>'
        )
        with tempfile.TemporaryDirectory() as d:
            pts = parse_route(_write(d, "a.kml", kml))
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0].lat, 40.0)
        self.assertAlmostEqual(pts[0].lon, 116.0)
        self.assertAlmostEqual(pts[0].alt, 100)

    def test_reject_too_few_points(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "a.csv", "lat,lon\n40.0,116.0\n")
            with self.assertRaises(ValueError):
                parse_route(p)


if __name__ == "__main__":
    unittest.main()
