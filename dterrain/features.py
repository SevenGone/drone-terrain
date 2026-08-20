# -*- coding: utf-8 -*-
"""本地图像特征提取：从抽出的帧中计算地形相关统计特征，供 DeepSeek 文本模型判断。

无需视觉 API；只用 numpy + Pillow 做颜色/纹理统计，把「图」变成「数」再交给 DeepSeek 语义判断。
"""
from __future__ import annotations


def extract_features(jpg_path: str, max_side: int = 256) -> dict:
    import numpy as np
    from PIL import Image

    img = Image.open(jpg_path).convert("RGB")
    img.thumbnail((max_side, max_side))
    arr = np.asarray(img, dtype=np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

    # 植被：绿色明显高于红、蓝（NDVI 近似）
    veg = float(np.mean((g > r * 1.08) & (g > b * 1.08)))
    # 水域：蓝色明显高于红、绿
    water = float(np.mean((b > r * 1.08) & (b > g * 1.08)))
    # 暖色裸地/沙土：红、绿偏暖且蓝偏低
    warm = float(np.mean((r > b * 1.2) & (g > b * 1.15)))
    # 亮度 / 饱和度
    brightness = float(arr.mean())
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    saturation = float(np.mean((mx - mn) / (mx + 1e-6)))
    # 边缘密度（建筑/道路多边缘，森林/草地/水面较少）
    gray = 0.299 * r + 0.587 * g + 0.114 * b
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    edge = float((gx.mean() + gy.mean()) / 2.0)

    means = {"r": float(r.mean()), "g": float(g.mean()), "b": float(b.mean())}
    dominant = max(means, key=means.get)

    return {
        "vegetation_ratio": round(veg, 4),
        "water_ratio": round(water, 4),
        "warm_soil_ratio": round(warm, 4),
        "brightness": round(brightness, 1),
        "saturation": round(saturation, 4),
        "edge_density": round(edge, 2),
        "mean_r": round(means["r"], 1),
        "mean_g": round(means["g"], 1),
        "mean_b": round(means["b"], 1),
        "dominant_channel": dominant,
    }


def features_to_text(f: dict) -> str:
    return (
        f"- 绿色植被像素占比(vegetation): {f['vegetation_ratio']}\n"
        f"- 蓝色水域像素占比(water): {f['water_ratio']}\n"
        f"- 暖色裸地/沙土占比(warm_soil): {f['warm_soil_ratio']}\n"
        f"- 平均亮度(brightness): {f['brightness']}\n"
        f"- 平均饱和度(saturation): {f['saturation']}\n"
        f"- 边缘密度(edge_density): {f['edge_density']}\n"
        f"- RGB 均值: R={f['mean_r']} G={f['mean_g']} B={f['mean_b']}"
    )
