# -*- coding: utf-8 -*-
"""命令行入口：single / batch / sample / info 子命令。"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from .classify import classify_frame
from .config import load_config
from .geo import build_track, match_coord, track_extent
from .report import print_result, save_results
from .srt import find_srt
from .video import extract_frame, probe


def _parse_coord(s: str):
    parts = [p.strip() for p in str(s).split(",")]
    if len(parts) != 2:
        raise ValueError('--coord 格式应为 "lon,lat"，例如 "116.3281,40.0755"')
    try:
        lon = float(parts[0])
        lat = float(parts[1])
    except ValueError:
        raise ValueError("--coord 解析失败：应为两个数字（lon,lat）")
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError(f"坐标越界：经度 {lon}（应 -180~180）、纬度 {lat}（应 -90~90）；注意顺序为 lon,lat")
    return lat, lon


def _col(header, *names):
    for n in names:
        if n in header:
            return header.index(n)
    return None


def _read_coords_csv(path: str):
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


def _sample_points(track, duration, every, count):
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


def _run_points(video, duration, track, config, out_dir, points, aligned_by):
    out = Path(out_dir)
    thumbs = out / "thumbnails"
    thumbs.mkdir(parents=True, exist_ok=True)

    results = []
    for pid, lat, lon in points:
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
    return results


def _cmd_info(args, config, track, duration, aligned_by, info):
    mnlat, mxlat, mnlon, mxlon = track_extent(track)
    print(f"视频: {args.video}")
    print(f"时长: {duration:.2f} s  分辨率: {info.get('width')}x{info.get('height')}")
    print(f"创建时间: {info.get('creation_time')}")
    print(f"轨迹点数: {len(track)}  对齐方式: {aligned_by}")
    print(f"轨迹范围: 纬度 {mnlat:.6f} ~ {mxlat:.6f}，经度 {mnlon:.6f} ~ {mxlon:.6f}")
    print(f"地貌分类({len(config.categories)}): {', '.join(config.categories)}")
    return 0


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--video", required=True, help="无人机航拍视频文件")
    common.add_argument("--srt", help="大疆 .SRT 字幕（缺省按视频同名自动发现）")
    common.add_argument("--route", help="备用航线/航迹文件 .gpx/.csv/.kml")
    common.add_argument("--model", help="云端视觉模型名")
    common.add_argument("--api-base", help="OpenAI 兼容 API 地址，如 https://dashscope.aliyuncs.com/compatible-mode/v1")
    common.add_argument("--api-key", help="API Key")
    common.add_argument("--categories", type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                        help="地貌分类，逗号分隔；最后一项为兜底")
    common.add_argument("--max-dist-meters", type=float, help="判定偏离航线的距离阈值（默认 200）")
    common.add_argument("--timeout", type=float, help="单次请求超时秒数（默认 60）")
    common.add_argument("--retries", type=int, help="失败重试次数（默认 3）")
    common.add_argument("--start-offset", type=float, default=0.0,
                        help="视频开始后多少秒无人机到达航线起点（默认 0；用于无 SRT 时对齐）")
    common.add_argument("--max-side", type=int, help="发送给模型前图片长边像素（默认 1024）")
    common.add_argument("--backend", choices=["features", "vision", "mock"], default=None,
                        help="识别后端：features=本地特征+DeepSeek文本(默认) / vision=视觉大模型 / mock=假结果")
    common.add_argument("--verbose", action="store_true", help="输出更多诊断信息")
    common.add_argument("--out", default=".", help="结果输出目录（默认当前目录）")

    parser = argparse.ArgumentParser(
        prog="dterrain",
        description="无人机航拍视频 -> 坐标点位地形地貌识别（针对大疆 DJI，SRT 字幕为主坐标源）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("single", parents=[common], help="识别单个坐标点位")
    p.add_argument("--coord", required=True, help='目标坐标 "lon,lat"，需落在航线上')

    p = sub.add_parser("batch", parents=[common], help="批量识别坐标清单")
    p.add_argument("--coords", required=True, help="坐标清单 CSV，列 lon,lat[,id]")

    p = sub.add_parser("sample", parents=[common], help="沿航线等间隔采样识别")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--every", type=float, help="按时间间隔采样（秒）")
    g.add_argument("--count", type=int, help="按点数均匀采样")

    sub.add_parser("info", parents=[common], help="查看视频与轨迹信息")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    config = load_config(args)
    try:
        srt = args.srt or find_srt(args.video)
        if args.verbose and srt:
            print(f"[info] 使用 SRT: {srt}")

        info = probe(args.video)
        duration = float(info.get("duration") or 0)
        if duration <= 0:
            raise RuntimeError("视频时长读取为 0，无法处理")

        track, aligned_by = build_track(srt, args.route, duration, args.start_offset)
        if args.verbose:
            print(f"[info] 轨迹点数 {len(track)}，对齐方式 {aligned_by}，视频时长 {duration:.1f}s")

        if args.command == "info":
            return _cmd_info(args, config, track, duration, aligned_by, info)

        if args.command == "single":
            lat, lon = _parse_coord(args.coord)
            points = [("single", lat, lon)]
        elif args.command == "batch":
            points = _read_coords_csv(args.coords)
        elif args.command == "sample":
            points = _sample_points(track, duration, args.every, args.count)
        else:
            raise RuntimeError(f"未知子命令 {args.command}")

        results = _run_points(args.video, duration, track, config, args.out, points, aligned_by)
        for r in results:
            print_result(r)
        jp, cp = save_results(results, args.out)
        print(f"\n完成 {len(results)} 个点位。汇总: {jp} / {cp}")
        return 0
    except Exception as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
