# -*- coding: utf-8 -*-
"""共享处理流程：坐标解析、清单读取、采样、批量跑点（CLI 与 GUI 共用）。"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from .classify import classify_frame
from .geo import match_coord
from .video import extract_frame


def parse_coord(s: str):
    parts = [p.strip() for p in str(s).split(",")]
    if len(parts) != 2:
        raise ValueError('坐标格式应为 "lon,lat"，例如 "116.3281,40.0755"')
    try:
        lon = float(parts[0])
        lat = float(parts[1])
    except ValueError:
        raise ValueError("坐标解析失败：应为两个数字（lon,lat）")
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError(f"坐标越界：经度 {lon}（应 -180~180）、纬度 {lat}（应 -90~90）；注意顺序为 lon,lat")
    return lat, lon


def _col(header, *names):
    for n in names:
        if n in header:
            return header.index(n)
    return None


def read_coords_csv(path: str):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    if not rows:
        raise ValueError(f"坐标清单 {path} 为空")
    h = [c.strip().lower().lstrip("\ufeff") for c in rows[0]]
    lon_i = _col(h, "lon", "lng", "long", "longitude", "x", "经度")
    lat_i = _col(h, "lat", "latitude", "y", "纬度")
    id_i = _col(h, "id", "name", "编号", "名称")
    if lon_i is None or lat_i is None:
        raise ValueError("坐标清单 CSV 需要 lon/lat 列（可识别表头：lon/lat/id/name）")

    points = []
    for i, row in enumerate(rows[1:], 1):
        if not row or all(not (c or "").strip() for c in row):
            continue
        try:
            lon = float(row[lon_i].strip())
            lat = float(row[lat_i].strip())
        except (ValueError, IndexError):
            continue
        pid = row[id_i].strip() if id_i is not None and id_i < len(row) and row[id_i].strip() else str(i)
        points.append((pid, lat, lon))
    if not points:
        raise ValueError(f"坐标清单 {path} 中没有有效坐标行")
    return points


def sample_points(track, duration, every, count):
    if count:
        n = max(2, int(count))
        idxs = []
        for i in range(n):
            j = round(i * (len(track) - 1) / (n - 1))
            if not idxs or idxs[-1] != j:
                idxs.append(j)
        return [(f"p{j:03d}", track[j].lat, track[j].lon) for j in idxs]
    step = max(0.1, float(every))
    ts, points = 0.0, []
    while ts <= duration + 1e-9:
        i = min(range(len(track)), key=lambda k: abs(track[k].video_ts - ts))
        points.append((f"t={ts:.0f}s", track[i].lat, track[i].lon))
        ts += step
        if len(points) > 100000:
            break
    return points


def run_points(video, duration, track, config, out_dir, points, aligned_by, progress=None):
    """progress(done:int, total:int, pid:str) 可选回调，用于 GUI 进度。"""
    out = Path(out_dir)
    thumbs = out / "thumbnails"
    thumbs.mkdir(parents=True, exist_ok=True)

    results = []
    total = len(points)
    for idx, (pid, lat, lon) in enumerate(points):
        tp, dist, off = match_coord(track, lat, lon, config.max_dist_meters)
        ts = max(0.0, min(tp.video_ts, duration - 0.001))
        safe = re.sub(r"[^0-9A-Za-z_.\-]+", "_", str(pid))
        frame = thumbs / f"{safe}.jpg"
        extract_frame(video, ts, str(frame))
        category, confidence, reason = classify_frame(str(frame), config.categories, config)
        results.append({
            "id": str(pid),
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "video_ts": round(ts, 2),
            "category": category,
            "confidence": confidence,
            "nearest_lat": round(tp.lat, 7),
            "nearest_lon": round(tp.lon, 7),
            "distance_m": round(dist, 1),
            "off_route": bool(off),
            "aligned_by": aligned_by,
            "frame_path": str(frame),
            "reason": reason,
        })
        if progress:
            progress(idx + 1, total, str(pid))
    return results
