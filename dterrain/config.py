# -*- coding: utf-8 -*-
"""配置加载与合并：默认值 <- 配置文件 <- 命令行参数 <- 环境变量。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .categories import DEFAULT_CATEGORIES

CONFIG_PATH = Path.home() / ".dterrain" / "config.json"

# 默认采用 DeepSeek 云端文本模型（本地特征 -> DeepSeek 判断）
_DEFAULTS = {
    "model": "deepseek-v4-flash",
    "api_base": "https://api.deepseek.com",
    "api_key": "",
    "backend": "features",
    "max_dist_meters": 200.0,
    "timeout": 60.0,
    "retries": 3,
    "max_side": 1024,
    "categories": list(DEFAULT_CATEGORIES),
}


@dataclass
class Config:
    model: str = "deepseek-v4-flash"
    api_base: str = "https://api.deepseek.com"
    api_key: str = ""
    backend: str = "features"
    categories: list = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    max_dist_meters: float = 200.0
    timeout: float = 60.0
    retries: int = 3
    max_side: int = 1024
    verbose: bool = False


def _read_file_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def load_config(args) -> Config:
    """args 为 argparse 解析后的 Namespace。命令行未显式提供的项，依次回落到配置文件、默认值、环境变量。"""
    file_cfg = _read_file_config()

    def pick(name: str):
        cli_val = getattr(args, name, None)
        if cli_val is not None:
            return cli_val
        return file_cfg.get(name, _DEFAULTS.get(name))

    cfg = Config(
        model=pick("model") or "deepseek-v4-flash",
        api_base=pick("api_base") or "https://api.deepseek.com",
        api_key=pick("api_key") or "",
        backend=pick("backend") or "features",
        categories=pick("categories") or list(DEFAULT_CATEGORIES),
        max_dist_meters=float(pick("max_dist_meters")),
        timeout=float(pick("timeout")),
        retries=int(pick("retries")),
        max_side=int(pick("max_side")),
        verbose=bool(getattr(args, "verbose", False)),
    )

    if not cfg.api_key:
        cfg.api_key = os.environ.get("DTERRAIN_API_KEY", "")

    if not cfg.categories or len(cfg.categories) < 2:
        cfg.categories = list(DEFAULT_CATEGORIES)

    if cfg.backend not in ("features", "vision", "mock"):
        cfg.backend = "features"

    return cfg
