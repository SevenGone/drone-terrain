# -*- coding: utf-8 -*-
"""允许 python -m dterrain 运行。"""
import sys

from dterrain.cli import main

if __name__ == "__main__":
    sys.exit(main())
