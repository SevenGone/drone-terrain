# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from dterrain.geo import TrackPoint, build_track, haversine_m, match_coord


class TestGeo(unittest.TestCase):
    def test_haversine_latitude_degree(self):
        d = haversine_m(0, 0, 1, 0)
        self.assertTrue(110000 < d < 112000, f"got {d}")

    def test_haversine_symmetry(self):
        self.assertAlmostEqual(haversine_m(10, 20, 30, 40), haversine_m(30, 40, 10, 20))

    def test_build_track_uniform_speed(self):
        csv = "lat,lon\n0,0\n0,1\n0,2\n"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.csv"
            p.write_text(csv, encoding="utf-8")
            track, aligned = build_track(None, str(p), video_duration=10.0)
        self.assertEqual(aligned, "uniform_speed")
        self.assertEqual(len(track), 3)
        self.assertAlmostEqual(track[0].video_ts, 0.0)
        self.assertAlmostEqual(track[-1].video_ts, 10.0)
        self.assertAlmostEqual(track[1].video_ts, 5.0)

    def test_build_track_timestamp(self):
        csv = "time,lat,lon\n100.0,0,0\n101.0,0,1\n102.0,0,2\n"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.csv"
            p.write_text(csv, encoding="utf-8")
            track, aligned = build_track(None, str(p), video_duration=10.0, start_offset=0.5)
        self.assertEqual(aligned, "timestamp")
        self.assertAlmostEqual(track[0].video_ts, -0.5)
        self.assertAlmostEqual(track[-1].video_ts, 1.5)

    def test_match_coord(self):
        track = [TrackPoint(0.0, 40.0, 116.0), TrackPoint(1.0, 40.001, 116.001)]
        tp, d, off = match_coord(track, 40.00005, 116.00005)
        self.assertEqual(tp, track[0])
        self.assertTrue(d < 20)
        self.assertFalse(off)

    def test_match_coord_off_route(self):
        track = [TrackPoint(0.0, 40.0, 116.0)]
        tp, d, off = match_coord(track, 39.0, 115.0, max_dist_meters=100)
        self.assertTrue(off)


if __name__ == "__main__":
    unittest.main()
