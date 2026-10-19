#!/usr/bin/env python3
"""NeoPilot 可执行入口：python3 neopilot.py <命令>"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from neopilot.cli import main

if __name__ == "__main__":
    sys.exit(main())
