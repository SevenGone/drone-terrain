# -*- coding: utf-8 -*-
import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from dterrain.categories import DEFAULT_CATEGORIES
from dterrain.cli import main


def _have_ffmpeg():
    return shutil.which("ffmpeg") is not None


@unittest.skipUnless(_have_ffmpeg(), "需要 ffmpeg 才能生成测试视频")
class TestCliE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.video = str(d / "v.mp4")
        # 3 秒合成视频
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10",
             "-t", "3", "-pix_fmt", "yuv420p", self.video],
            capture_output=True, text=True)
        # 3 条大疆风格 SRT
        srt = d / "v.srt"
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\n[latitude: 40.000000] [longitude: 116.000000] [rel_alt: 100]\n\n"
            "2\n00:00:01,000 --> 00:00:02,000\n[latitude: 40.000010] [longitude: 116.000004] [rel_alt: 100]\n\n"
            "3\n00:00:02,000 --> 00:00:03,000\n[latitude: 40.000020] [longitude: 116.000008] [rel_alt: 100]\n\n",
            encoding="utf-8")
        self.srt = str(srt)
        self.out = str(d / "out")

    def _run(self, argv):
        buf = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, buf.getvalue(), err.getvalue()

    def test_single_mock(self):
        code, out, err = self._run([
            "single", "--video", self.video, "--srt", self.srt,
            "--coord", "116.000000,40.000000", "--backend", "mock", "--out", self.out])
        self.assertEqual(code, 0, f"stderr: {err}")
        data = json.loads(Path(self.out, "results.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data), 1)
        self.assertIn(data[0]["category"], DEFAULT_CATEGORIES)
        self.assertTrue(Path(data[0]["frame_path"]).exists())
        self.assertIn("地貌", out)

    def test_info(self):
        code, out, err = self._run([
            "info", "--video", self.video, "--srt", self.srt])
        self.assertEqual(code, 0, f"stderr: {err}")
        self.assertIn("srt", out)
        self.assertIn("轨迹点数", out)


if __name__ == "__main__":
    unittest.main()
