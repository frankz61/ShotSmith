"""建表脚本：创建 task / asset 表（首次运行或表结构变更后执行）。"""
import sys
from pathlib import Path

# 保证从任意 cwd 都能 import app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.models.task  # noqa: E402,F401  注册模型到 Base.metadata
from app.models.db import Base, engine  # noqa: E402


def main() -> None:
    Base.metadata.create_all(engine)
    print("OK: 建表完成 -> task, asset")


if __name__ == "__main__":
    main()
