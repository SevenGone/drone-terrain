# -*- coding: utf-8 -*-
"""地理计算：haversine 距离、最近点匹配、把坐标源对齐到视频时间轴。"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .route import parse_route
from .srt import parse_srt

R_EARTH = 6371008.8  # 米


@dataclass
class TrackPoint:
    video_ts: float  # 相对视频起点的秒数
    lat: float
    lon: float
    alt: float | None = None


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def nearest_index(lats, lons, lat, lon):
    """返回 (最小距离索引, 最小距离米)。"""
    best_i, best_d = 0, float("inf")
    for i, (la, lo) in enumerate(zip(lats, lons)):
        d = haversine_m(lat, lon, la, lo)
        if d < best_d:
            best_d, best_i = d, i
    return best_i, best_d


def build_track(srt_path, route_path, video_duration, start_offset=0.0):
    """把坐标源（优先 SRT，其次航线文件）归一化为 TrackPoint 列表并返回 (track, aligned_by)。"""
    if srt_path:
        pts = parse_srt(srt_path)
        if len(pts) < 2:
            raise ValueError(f"SRT 文件 {srt_path} 中有效 GPS 点不足 2 个")
        track = [TrackPoint(p.video_ts, p.lat, p.lon, p.alt) for p in pts]
        return track, "srt"

    if route_path:
        rpts = parse_route(route_path)
        # 有时间戳：以首点为视频 0 点对齐
        if all(p.time is not None for p in rpts):
            base = rpts[0].time
            track = [TrackPoint((p.time - base) - start_offset, p.lat, p.lon, p.alt) for p in rpts]
            return track, "timestamp"
        # 无时间戳：按累计距离匀速假设；start_offset = 视频开始后多少秒到达航线起点
        cum = [0.0]
        for i in range(1, len(rpts)):
            cum.append(cum[-1] + haversine_m(rpts[i - 1].lat, rpts[i - 1].lon, rpts[i].lat, rpts[i].lon))
        total = cum[-1]
        denom = max(video_duration - start_offset, 1e-6)
        track = []
        for i, p in enumerate(rpts):
            frac = (cum[i] / total) if total > 0 else (i / max(len(rpts) - 1, 1))
            track.append(TrackPoint(start_offset + frac * denom, p.lat, p.lon, p.alt))
        return track, "uniform_speed"

    raise ValueError("缺少坐标源：请提供 --srt（大疆字幕）或 --route（GPX/CSV/KML 航线文件）")


def match_coord(track, lat, lon, max_dist_meters=200.0):
    """在轨迹中找到离 (lat, lon) 最近的点，返回 (TrackPoint, 距离米, 是否偏离航线)。"""
    lats = [p.lat for p in track]
    lons = [p.lon for p in track]
    i, d = nearest_index(lats, lons, lat, lon)
    return track[i], d, d > max_dist_meters


def track_extent(track):
    """返回轨迹的 (min_lat, max_lat, min_lon, max_lon)。"""
    lats = [p.lat for p in track]
    lons = [p.lon for p in track]
    return min(lats), max(lats), min(lons), max(lons)
