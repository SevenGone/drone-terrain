# -*- coding: utf-8 -*-
import unittest

from dterrain.categories import DEFAULT_CATEGORIES, normalize_category
from dterrain.classify import parse_response


class TestClassify(unittest.TestCase):
    def test_parse_json(self):
        cat, conf, reason = parse_response(
            '{"category": "森林", "confidence": 0.9, "reason": "大面积树木"}', DEFAULT_CATEGORIES)
        self.assertEqual(cat, "森林")
        self.assertAlmostEqual(conf, 0.9)
        self.assertEqual(reason, "大面积树木")

    def test_parse_json_with_surrounding_text(self):
        cat, _, _ = parse_response(
            '判断结果为：{"category": "水域", "confidence": 0.8}', DEFAULT_CATEGORIES)
        self.assertEqual(cat, "水域")

    def test_parse_plain_text_alias(self):
        cat, _, _ = parse_response("这是一片稻田", DEFAULT_CATEGORIES)
        self.assertEqual(cat, "农田")

    def test_parse_garbage_falls_back_to_other(self):
        cat, _, _ = parse_response("asdfgh123", DEFAULT_CATEGORIES)
        self.assertEqual(cat, "其他")

    def test_normalize_alias_exact(self):
        self.assertEqual(normalize_category("沙漠", DEFAULT_CATEGORIES), "裸地/荒漠")
        self.assertEqual(normalize_category("公路", DEFAULT_CATEGORIES), "道路")


if __name__ == "__main__":
    unittest.main()
