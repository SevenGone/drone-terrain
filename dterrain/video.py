# -*- coding: utf-8 -*-
"""视频处理：ffprobe 读元信息、ffmpeg 抽帧、帧缩放转 base64。"""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import sys
from pathlib import Path


def _find_tool(env_name: str, exe_name: str) -> str:
    env = os.environ.get(env_name)
    if env and Path(env).exists():
        return env
    # PyInstaller 打包时捆绑的二进制（_MEIPASS 临时解包目录）
    base_dir = getattr(sys, "_MEIPASS", None)
    if base_dir:
        cand = Path(base_dir) / "bin" / (exe_name + (".exe" if os.name == "nt" else ""))
        if cand.exists():
            return str(cand)
    # 项目根 bin/ 目录
    cand = Path(__file__).resolve().parents[1] / "bin" / (exe_name + (".exe" if os.name == "nt" else ""))
    if cand.exists():
        return str(cand)
    return exe_name  # 依赖系统 PATH


def ffmpeg() -> str:
    return _find_tool("DTERRAIN_FFMPEG", "ffmpeg")


def ffprobe() -> str:
    return _find_tool("DTERRAIN_FFPROBE", "ffprobe")


def probe(video_path: str) -> dict:
    cmd = [ffprobe(), "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(video_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe 读取视频失败: {(r.stderr or '').strip()}")
    data = json.loads(r.stdout)
    duration = float(data.get("format", {}).get("duration", 0) or 0)
    width = height = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            width = s.get("width")
            height = s.get("height")
            break
    creation = (data.get("format", {}).get("tags", {}) or {}).get("creation_time")
    return {"duration": duration, "width": width, "height": height, "creation_time": creation}


def extract_frame(video_path: str, ts: float, out_jpg: str):
    """在时间戳 ts 处抽一帧。先快速 seek 到 ts-3 再精确 seek，兼顾速度与精度。"""
    ts = max(0.0, float(ts))
    pre = max(0.0, ts - 3.0)
    delta = ts - pre
    cmd = [ffmpeg(), "-ss", f"{pre:.3f}", "-i", str(video_path),
           "-ss", f"{delta:.3f}", "-frames:v", "1", "-q:v", "3", "-y", str(out_jpg)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not Path(out_jpg).exists():
        raise RuntimeError(f"ffmpeg 抽帧失败(ts={ts:.1f}s): {(r.stderr or '').strip()[:400]}")


def frame_to_base64(jpg_path: str, max_side: int = 1024) -> str:
    from PIL import Image
    img = Image.open(jpg_path).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")
