#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成一套合成演示数据：航线 CSV + 大疆风格 SRT + 坐标清单 + 合成视频。

用于在没有真实无人机数据时联调/演示 dterrain。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def fmt_ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def generate(out_dir: str, seconds: int = 30,
             lat0: float = 40.000000, lon0: float = 116.000000,
             lat_step: float = 0.000010, lon_step: float = 0.000004,
             alt: float = 120.0):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1) 航线 CSV（含时间戳）
    csv_path = out / "demo_route.csv"
    with csv_path.open("w", encoding="utf-8") as f:
        f.write("time,lat,lon,alt\n")
        for i in range(seconds + 1):
            f.write(f"{i},{lat0 + lat_step * i:.6f},{lon0 + lon_step * i:.6f},{alt:.1f}\n")

    # 2) 大疆风格 SRT（方括号键值式）
    srt_path = out / "demo.srt"
    with srt_path.open("w", encoding="utf-8") as f:
        for i in range(seconds):
            f.write(f"{i + 1}\n{fmt_ts(i)} --> {fmt_ts(i + 1)}\n")
            f.write(f"[iso: 100] [shutter: 1/800] [latitude: {lat0 + lat_step * i:.6f}] "
                    f"[longitude: {lon0 + lon_step * i:.6f}] [rel_alt: {alt:.1f}]\n\n")

    # 3) 坐标清单（落在航线上）
    pts_path = out / "demo_points.csv"
    with pts_path.open("w", encoding="utf-8") as f:
        f.write("id,lon,lat\n")
        for i in (0, seconds // 3, 2 * seconds // 3, seconds):
            f.write(f"点{i},{lon0 + lon_step * i:.6f},{lat0 + lat_step * i:.6f}\n")

    # 4) 无时间戳航线航点（lat,lon，演示无 GPS/时间戳时的匀速匹配）
    wp_path = out / "demo_waypoints.csv"
    with wp_path.open("w", encoding="utf-8") as f:
        f.write("lat,lon\n")
        for i in range(0, seconds + 1, 2):
            f.write(f"{lat0 + lat_step * i:.6f},{lon0 + lon_step * i:.6f}\n")

    print(f"已生成: {csv_path}")
    print(f"已生成: {srt_path}")
    print(f"已生成: {pts_path}")
    print(f"已生成: {wp_path}")

    # 4) 合成视频（若 ffmpeg 可用）
    if shutil.which("ffmpeg"):
        video = out / "demo_video.mp4"
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i",
               f"testsrc2=size=1280x720:rate=30", "-t", str(seconds),
               "-pix_fmt", "yuv420p", str(video)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            print(f"已生成: {video}")
        else:
            print(f"合成视频失败: {r.stderr.strip()[:300]}")
    else:
        print("未找到 ffmpeg，跳过合成视频（可用任意真实航拍视频替代 demo_video.mp4）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="生成 dterrain 演示数据")
    ap.add_argument("--out", default="demo", help="输出目录")
    ap.add_argument("--seconds", type=int, default=30, help="时长（秒）")
    a = ap.parse_args()
    generate(a.out, a.seconds)
