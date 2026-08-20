# -*- coding: utf-8 -*-
"""地形地貌识别：本地特征 + DeepSeek 文本模型（默认），或视觉大模型（vision），或 mock。"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

import requests

from .categories import normalize_category
from .features import extract_features, features_to_text
from .video import frame_to_base64


def _require_config(config):
    if not config.api_base or not config.model or not config.api_key:
        raise RuntimeError(
            "缺少云端模型配置。请通过以下任一方式提供：\n"
            "  --api-base https://api.deepseek.com --model deepseek-v4-flash --api-key <key>\n"
            "  或在 ~/.dterrain/config.json 中配置 api_base / model / api_key\n"
            "  或设置环境变量 DTERRAIN_API_KEY\n"
            "（本地联调可用 --backend mock 跳过云端调用）"
        )


def _post_chat(messages, config) -> str:
    _require_config(config)
    url = config.api_base.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
    payload = {"model": config.model, "messages": messages, "temperature": 0.2}

    last_err = ""
    for attempt in range(config.retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=config.timeout)
            if r.status_code == 200:
                data = r.json()
                return data["choices"][0]["message"]["content"]
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.exceptions.RequestException as e:
            last_err = str(e)
        except (KeyError, IndexError, ValueError) as e:
            last_err = f"响应解析失败: {e}"
        if attempt < config.retries:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"云端调用失败: {last_err}")


def build_vision_prompt(categories) -> str:
    cats = "、".join(categories)
    return (
        "你是一名无人机航拍影像分析助手。下面这张图片是无人机在某坐标点位上拍摄的航拍画面。\n"
        f"请判断该点位的地形地貌类别，只能从以下类别中选择最匹配的一个：{cats}。\n"
        "请严格只输出一个 JSON 对象，不要输出任何其他文字或代码块，格式为：\n"
        '{"category": "类别名", "confidence": 0到1之间的小数, "reason": "一句话判断依据"}'
    )


def build_features_prompt(features, categories) -> str:
    cats = "、".join(categories)
    return (
        "你是一名地形地貌分析助手。下面是无人机航拍画面经过本地图像分析得到的统计特征：\n"
        f"{features_to_text(features)}\n"
        f"请据此判断该点位的地形地貌类别，只能从以下类别中选择最匹配的一个：{cats}。\n"
        "请严格只输出一个 JSON 对象，不要输出任何其他文字，格式为：\n"
        '{"category": "类别名", "confidence": 0到1之间的小数, "reason": "一句话判断依据"}'
    )


def _extract_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def parse_response(text, categories):
    """把模型返回文本解析为 (category, confidence, reason)。"""
    obj = _extract_json(text)
    category = None
    confidence = None
    reason = text
    if isinstance(obj, dict):
        category = obj.get("category") or obj.get("类别") or obj.get("label") or obj.get("type")
        conf = obj.get("confidence") or obj.get("置信度") or obj.get("score")
        if conf is not None:
            try:
                confidence = float(conf)
            except (TypeError, ValueError):
                confidence = None
        reason = obj.get("reason") or obj.get("依据") or obj.get("说明") or text
    normalized = normalize_category(str(category if category else text), categories)
    return normalized, confidence, reason


def mock_classify(jpg_path, categories):
    """mock 模式：按文件字节做确定性哈希选类别（仅用于无 Key 联调/演示）。"""
    h = hashlib.md5(Path(jpg_path).read_bytes()).hexdigest()
    cat = categories[int(h, 16) % len(categories)]
    return cat, 0.5, "mock 模式（未调用云端模型）"


def classify_frame(jpg_path, categories, config):
    if config.backend == "mock":
        return mock_classify(jpg_path, categories)
    if config.backend == "vision":
        b64 = frame_to_base64(jpg_path, config.max_side)
        raw = _post_chat([{
            "role": "user",
            "content": [
                {"type": "text", "text": build_vision_prompt(categories)},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }], config)
    else:  # features（默认：本地特征 + DeepSeek 文本模型）
        feat = extract_features(jpg_path)
        raw = _post_chat([{"role": "user", "content": build_features_prompt(feat, categories)}], config)
    return parse_response(raw, categories)
