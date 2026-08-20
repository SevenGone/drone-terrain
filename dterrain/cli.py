# -*- coding: utf-8 -*-
"""命令行入口：single / batch / sample / info 子命令。"""
from __future__ import annotations

import argparse
import sys

from .config import load_config
from .geo import build_track, track_extent
from .pipeline import parse_coord, read_coords_csv, run_points, sample_points
from .report import print_result, save_results
from .srt import find_srt
from .video import probe


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
    common.add_argument("--model", help="云端模型名")
    common.add_argument("--api-base", help="OpenAI 兼容 API 地址，默认 https://api.deepseek.com")
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
        description="无人机航拍视频 -> 坐标点位地形地貌识别（DeepSeek 云端，支持大疆 SRT 或无 GPS 航线）",
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
            lat, lon = parse_coord(args.coord)
            points = [("single", lat, lon)]
        elif args.command == "batch":
            points = read_coords_csv(args.coords)
        elif args.command == "sample":
            points = sample_points(track, duration, args.every, args.count)
        else:
            raise RuntimeError(f"未知子命令 {args.command}")

        results = run_points(args.video, duration, track, config, args.out, points, aligned_by)
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
