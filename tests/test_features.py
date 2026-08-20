# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from dterrain.features import extract_features, features_to_text


def _img(color):
    d = tempfile.mkdtemp()
    p = Path(d) / "a.jpg"
    Image.new("RGB", (64, 64), color).save(p)
    return str(p)


class TestFeatures(unittest.TestCase):
    def test_green_vegetation(self):
        f = extract_features(_img((0, 180, 0)))
        self.assertGreater(f["vegetation_ratio"], 0.9)

    def test_blue_water(self):
        f = extract_features(_img((0, 0, 200)))
        self.assertGreater(f["water_ratio"], 0.9)

    def test_keys_and_text(self):
        f = extract_features(_img((128, 128, 128)))
        for k in ("vegetation_ratio", "water_ratio", "warm_soil_ratio",
                  "brightness", "saturation", "edge_density"):
            self.assertIn(k, f)
        t = features_to_text(f)
        self.assertIn("植被", t)


if __name__ == "__main__":
    unittest.main()
