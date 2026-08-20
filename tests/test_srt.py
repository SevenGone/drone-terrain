# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from dterrain.srt import extract_gps, find_srt, parse_srt


class TestSrt(unittest.TestCase):
    def test_extract_bracket_format(self):
        text = "[iso: 100] [shutter: 1/800] [latitude: 34.123456] [longitude: 108.123456] [rel_alt: 100.5]"
        lat, lon, alt = extract_gps(text)
        self.assertAlmostEqual(lat, 34.123456)
        self.assertAlmostEqual(lon, 108.123456)
        self.assertAlmostEqual(alt, 100.5)

    def test_extract_gps_tuple_format(self):
        text = "F/2.8, SS 1/640, ISO 100, GPS(40.0755000, 116.3281000, 128), D 5.2m"
        lat, lon, alt = extract_gps(text)
        self.assertAlmostEqual(lat, 40.0755)
        self.assertAlmostEqual(lon, 116.3281)
        self.assertAlmostEqual(alt, 128)

    def test_extract_gps_colon_format(self):
        text = "GPS: (34.5, 108.5)"
        lat, lon, alt = extract_gps(text)
        self.assertAlmostEqual(lat, 34.5)
        self.assertAlmostEqual(lon, 108.5)
        self.assertIsNone(alt)

    def test_extract_none(self):
        self.assertIsNone(extract_gps("no gps here"))
        self.assertIsNone(extract_gps(""))

    def test_parse_srt(self):
        content = (
            "1\n00:00:00,000 --> 00:00:01,000\n"
            "[latitude: 40.000000] [longitude: 116.000000] [rel_alt: 100.0]\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n"
            "[latitude: 40.000010] [longitude: 116.000004] [rel_alt: 100.0]\n\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.srt"
            p.write_text(content, encoding="utf-8")
            pts = parse_srt(str(p))
        self.assertEqual(len(pts), 2)
        self.assertAlmostEqual(pts[0].video_ts, 0.0)
        self.assertAlmostEqual(pts[1].video_ts, 1.0)
        self.assertAlmostEqual(pts[1].lat, 40.00001)

    def test_find_srt_case_insensitive(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "DJI_0001.MP4").write_text("x")
            Path(d, "DJI_0001.SRT").write_text("srt")
            self.assertEqual(find_srt(str(Path(d, "DJI_0001.MP4"))), str(Path(d, "DJI_0001.SRT")))


if __name__ == "__main__":
    unittest.main()
