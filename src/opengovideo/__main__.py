"""讓 `python -m opengovideo` 等同 `opengovideo` CLI。"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
