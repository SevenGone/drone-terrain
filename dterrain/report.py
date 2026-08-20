# -*- coding: utf-8 -*-
"""结果输出：打印、写 JSON / CSV 汇总。"""
from __future__ import annotations

import csv
import json
from pathlib import Path

_FIELDS = [
    "id", "lat", "lon", "video_ts", "category", "confidence",
    "nearest_lat", "nearest_lon", "distance_m", "off_route",
    "aligned_by", "frame_path", "reason",
]


def _row(result: dict) -> dict:
    return {k: result.get(k, "") for k in _FIELDS}


def print_result(result: dict):
    print(f"[{result.get('id')}] 坐标({result.get('lat'):.6f}, {result.get('lon'):.6f}) "
          f"-> 地貌: {result.get('category')}  "
          f"(置信度 {result.get('confidence') if result.get('confidence') is not None else '-'})")
    if result.get("off_route"):
        print(f"    ⚠ 偏离航线最近点 {result.get('distance_m', 0):.1f} m（>阈值），已按最近点返回")
    if result.get("frame_path"):
        print(f"    帧截图: {result.get('frame_path')}")
    if result.get("reason"):
        print(f"    依据: {result.get('reason')}")


def save_results(results, out_dir: str):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "results.json"
    json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = out / "results.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDS)
        writer.writeheader()
        for r in results:
            writer.writerow(_row(r))

    return str(json_path), str(csv_path)
