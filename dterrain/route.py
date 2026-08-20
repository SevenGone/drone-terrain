# -*- coding: utf-8 -*-
"""解析外部航线/航迹文件（GPX / CSV / KML），作为 SRT 之外的备用坐标源。"""
from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RoutePoint:
    lat: float
    lon: float
    alt: float | None = None
    time: float | None = None  # epoch 秒；无时间戳时为 None


# CSV 表头别名 -> 规范字段
_HEADER_ALIASES = {
    "time": {"time", "timestamp", "datetime", "date_time", "utc", "time_s", "时间"},
    "lat": {"lat", "latitude", "y", "纬度", "lat_deg"},
    "lon": {"lon", "lng", "long", "longitude", "x", "经度", "lon_deg"},
    "alt": {"alt", "altitude", "elevation", "height", "高度", "alt_abs", "rel_alt"},
}


def _norm_header(name: str) -> str:
    n = (name or "").strip().lower().lstrip("\ufeff")
    for field, aliases in _HEADER_ALIASES.items():
        if n in aliases:
            return field
    return n


def _parse_time_token(value: str):
    """解析时间：优先当作 Unix 秒（数字），否则按 ISO8601。失败返回 None。"""
    if value is None:
        return None
    v = str(value).strip()
    if not v:
        return None
    try:
        f = float(v)
        return f
    except ValueError:
        pass
    # ISO8601，兼容末尾 Z
    iso = v.replace("Z", "+00:00").replace("z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(iso, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return None


def _parse_gpx(text: str) -> list:
    root = ET.fromstring(text)
    ns = {"g": "http://www.topografix.com/GPX/1/1",
          "g0": "http://www.topografix.com/GPX/1/0"}
    points = []
    for tag in ("trkpt", "rtept", "wpt"):
        for el in root.iter():
            if el.tag.split("}")[-1] != tag:
                continue
            lat = el.get("lat")
            lon = el.get("lon")
            if lat is None or lon is None:
                continue
            ele = el.find(".//{http://www.topografix.com/GPX/1/1}ele")
            if ele is None:
                ele = el.find(".//{http://www.topografix.com/GPX/1/0}ele")
            tm = el.find(".//{http://www.topografix.com/GPX/1/1}time")
            if tm is None:
                tm = el.find(".//{http://www.topografix.com/GPX/1/0}time")
            try:
                points.append(RoutePoint(
                    lat=float(lat), lon=float(lon),
                    alt=float(ele.text) if ele is not None and ele.text else None,
                    time=_parse_time_token(tm.text) if tm is not None and tm.text else None,
                ))
            except ValueError:
                continue
    return points


def _parse_csv(text: str) -> list:
    sample = text[:4096]
    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    reader = csv.reader(text.splitlines(), dialect)
    rows = [r for r in reader if r]
    if not rows:
        return []

    header = [_norm_header(c) for c in rows[0]]
    # 定位各列
    idx = {f: header.index(f) for f in ("time", "lat", "lon") if f in header}
    if "lat" not in idx or "lon" not in idx:
        # 找不到表头时，尝试按列名模糊：若首行是数据，则报错提示
        raise ValueError("CSV 缺少 lat/lon 列（可识别表头：time/lat/lon/alt 及常见别名）")

    def cell(row, key):
        i = idx.get(key)
        if i is None or i >= len(row):
            return None
        return row[i]

    points = []
    for row in rows[1:]:
        if not row or all((c or "").strip() == "" for c in row):
            continue
        try:
            lat = float(str(cell(row, "lat")).strip())
            lon = float(str(cell(row, "lon")).strip())
        except (ValueError, TypeError):
            continue
        alt = None
        if "alt" in idx:
            try:
                alt = float(str(cell(row, "alt")).strip())
            except (ValueError, TypeError):
                alt = None
        t = _parse_time_token(cell(row, "time")) if "time" in idx else None
        points.append(RoutePoint(lat=lat, lon=lon, alt=alt, time=t))
    return points


def _parse_kml(text: str) -> list:
    root = ET.fromstring(text)
    points = []
    for coords in root.iter():
        if coords.tag.split("}")[-1] != "coordinates":
            continue
        if not coords.text:
            continue
        for chunk in coords.text.strip().split():
            parts = [p for p in chunk.split(",") if p != ""]
            if len(parts) < 2:
                continue
            try:
                lon = float(parts[0])
                lat = float(parts[1])
                alt = float(parts[2]) if len(parts) >= 3 else None
            except ValueError:
                continue
            points.append(RoutePoint(lat=lat, lon=lon, alt=alt, time=None))
    return points


def parse_route(path) -> list:
    """按扩展名分发解析，返回 RoutePoint 列表。"""
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    ext = p.suffix.lower()
    if ext == ".gpx":
        points = _parse_gpx(text)
    elif ext == ".csv":
        points = _parse_csv(text)
    elif ext == ".kml" or ext == ".kmz":
        if ext == ".kmz":
            raise ValueError("KMZ 是压缩包，请先用解压工具取出其中的 .kml 后再导入")
        points = _parse_kml(text)
    else:
        raise ValueError(f"不支持的航线文件格式: {ext}（支持 .gpx/.csv/.kml）")

    if len(points) < 2:
        raise ValueError(f"航线文件 {path} 中有效坐标点不足 2 个，无法匹配")
    return points
