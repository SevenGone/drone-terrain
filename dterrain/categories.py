# -*- coding: utf-8 -*-
"""地形地貌分类表与模糊归一化。"""
from __future__ import annotations

# 默认 9 类地貌（可通过配置增删改）
DEFAULT_CATEGORIES = [
    "水域",
    "农田",
    "森林",
    "草地",
    "裸地/荒漠",
    "建筑",
    "道路",
    "山地",
    "其他",
]

# 每一类的同义/近义词，用于把大模型的自由文本归一化到固定类别（尽量用 >=2 字，避免误匹配）
CATEGORY_ALIASES = {
    "水域": ["水域", "水面", "河流", "湖泊", "水库", "池塘", "海洋", "湿地", "河道", "湖水", "江", "溪流"],
    "农田": ["农田", "耕地", "田地", "稻田", "麦田", "庄稼", "梯田", "田块", "农地", "菜地"],
    "森林": ["森林", "树林", "林地", "林木", "丛林", "密林"],
    "草地": ["草地", "草原", "草坪", "草甸", "牧场"],
    "裸地/荒漠": ["裸地", "荒漠", "沙漠", "戈壁", "荒地", "沙地", "盐碱地", "滩涂", "秃地"],
    "建筑": ["建筑", "房屋", "楼房", "城区", "城镇", "村庄", "居民", "厂房", "工地", "建筑物", "聚居"],
    "道路": ["道路", "公路", "马路", "街道", "高速", "铁路", "桥梁", "路面", "省道", "国道"],
    "山地": ["山地", "丘陵", "山坡", "山峰", "山脉", "峡谷", "山谷", "山体", "岩壁", "山脊"],
    "其他": ["其他", "其它", "未知", "无法判断", "无法确定", "云层", "不确定"],
}


def _clean(text: str) -> str:
    if not text:
        return ""
    return text.strip().strip("。.！!？?；;，,：: ").strip()


def normalize_category(text: str, categories=None) -> str:
    """把模型返回的任意文本归一化到 categories 中的一个类别；匹配不到则返回最后一个（默认「其他」）。

    注意：以 categories 列表顺序为优先级；若自定义分类表，则无法匹配时回落到列表最后一项。
    """
    cats = list(categories) if categories else list(DEFAULT_CATEGORIES)
    if not cats:
        return "其他"

    cleaned = _clean(text).lower()

    # 1) 精确匹配类别名 / 别名
    for cat in cats:
        if cleaned == cat.lower():
            return cat
        for alias in CATEGORY_ALIASES.get(cat, []):
            if cleaned == alias.lower():
                return cat

    # 2) 子串匹配（按类别顺序，别名需 >= 2 字）
    for cat in cats:
        for alias in CATEGORY_ALIASES.get(cat, []):
            if len(alias) >= 2 and alias.lower() in cleaned:
                return cat

    # 3) 兜底：返回最后一项（约定为「其他」）
    return cats[-1]
