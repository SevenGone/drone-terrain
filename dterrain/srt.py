# -*- coding: utf-8 -*-
"""解析大疆 DJI 无人机视频配套的 .SRT 字幕，提取「视频时间戳 -> GPS 坐标」映射。

大疆无人机在录制视频时会同步生成一个同名 .SRT 字幕文件（需在 App 里开启「视频字幕」）。
字幕里逐条（约每秒一条）记录 GPS 经纬度，常见格式举例如下：

  1
  00:00:00,000 --> 00:00:01,000
  [iso: 100] [shutter: 1/800] [latitude: 34.123456] [longitude: 108.123456] [rel_alt: 100.5]

  或

  00:00:01,000 --> 00:00:02,000
  F/2.8, SS 1/640, ISO 100, EV 0, GPS(40.0755000, 116.3281000, 128), D 5.2m, H 100.5m

本模块用多套正则兼容不同固件版本，尽量稳健地抽出 lat / lon（alt 可选）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SrtPoint:
    video_ts: float  # 相对视频起点的秒数
    lat: float
    lon: float
    alt: float | None = None


# SRT 时间戳：00:00:00,000 或 00:00:00.000
_TS_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.]\d{1,3}")

# 方括号/键值式：latitude / longitude
_RE_LAT = re.compile(r"(?<![\w])latitude\s*[:：]\s*(-?\d+\.?\d*)", re.I)
_RE_LON = re.compile(r"(?<![\w])longitude\s*[:：]\s*(-?\d+\.?\d*)", re.I)
# GPS(...) 或 GPS: (...) 形式：GPS(40.0, 116.0) / GPS(40.0, 116.0, 128)
_RE_GPS = re.compile(r"(?<![\w])GPS\s*[:：]?\s*[(（]?\s*(-?\d+\.?\d*)\s*[,，]\s*(-?\d+\.?\d*)(?:\s*[,，]\s*(-?\d+\.?\d*))?\s*[)）]?", re.I)
# 高度：rel_alt / altitude / alt
_RE_ALT = re.compile(r"(?:rel_alt|relalt|altitude)\s*[:：]\s*(-?\d+\.?\d*)", re.I)


def _parse_ts(s: str):
    m = re.match(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})", s)
    if not m:
        return None
    h, mi, sec, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(sec) + int(ms.ljust(3, "0")) / 1000.0


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def extract_gps(text: str):
    """从一段字幕文本中抽取 (lat, lon, alt|None)；失败返回 None。"""
    if not text:
        return None

    m = _RE_GPS.search(text)
    if m:
        lat = _num(m.group(1))
        lon = _num(m.group(2))
        alt = _num(m.group(3)) if m.group(3) else None
        return lat, lon, alt

    lm = _RE_LAT.search(text)
    gm = _RE_LON.search(text)
    if lm and gm:
        lat = _num(lm.group(1))
        lon = _num(gm.group(1))
        am = _RE_ALT.search(text)
        alt = _num(am.group(1)) if am else None
        return lat, lon, alt

    return None


def parse_srt(path) -> list:
    """解析 SRT 文件，返回 SrtPoint 列表（按时间升序）。"""
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    points = []

    for block in re.split(r"\n\s*\n", raw):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        start = None
        for ln in lines:
            m = re.search(r"(\d{2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->", ln)
            if m:
                start = _parse_ts(m.group(1))
                break
        if start is None:
            continue

        body = " ".join(lines)
        gps = extract_gps(body)
        if gps is None:
            continue
        lat, lon, alt = gps
        points.append(SrtPoint(start, lat, lon, alt))

    points.sort(key=lambda p: p.video_ts)
    return points


def find_srt(video_path: str):
    """按同名文件自动发现视频配套的 .SRT（大小写不敏感）。"""
    p = Path(video_path)
    for cand in (p.with_suffix(".SRT"), p.with_suffix(".srt")):
        if cand.exists():
            return str(cand)
    return None
