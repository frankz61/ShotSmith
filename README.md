# ShotSmith

AI 电商商品素材图生成工具：一张商品图 + 可选描述 → 一套可上架的素材图（白底主图 + 多场景图 + 多尺寸）。

设计文档见 [`docs/`](docs/)：需求 / 技术架构选型 / 概要设计 / 数据库设计。

## 技术栈
- 后端：FastAPI + Celery + SQLAlchemy（MySQL）+ Redis（端口 28000）
- 流水线：ingest → preprocess → 抠图 → 生成（白底/场景）→ 还原度校验 → 打包
- 抠图：rembg / BiRefNet（可选 simple 离线兜底）；场景：Pillow 合成（商品像素保持，可替换为商用 API）
- 前端：React + Vite + TypeScript（端口 25173）

> Redis 与 MySQL 使用外部服务，连接配置在 `.env`（已 gitignore，不要提交）。

## 启动

VS Code 调试面板：`1) Init DB` 建表一次 → `全部启动 (API + Worker + 前端)` 一键起三件套。
或命令行：

```bash
pip install -e ".[dev,matting]"          # matting 装 rembg/BiRefNet；纯试可只 .[dev]

# 建表（首次）
python scripts/init_db.py

# 后端 28000
uvicorn app.main:app --host 127.0.0.1 --port 28000
# Windows 下 Celery 需要 solo 池：
celery -A app.tasks.celery_app.celery_app worker --loglevel=info --pool=solo

# 前端 25173
cd web && pnpm install && pnpm dev
```

访问：前端 http://localhost:25173 ，后端文档 http://localhost:28000/docs 。

> 开箱即跑可把 `.env` 的 `MATTING_PROVIDER=simple`（纯 Pillow，仅适合纯色背景图）；最高质量用 `rembg` + `birefnet-general`（需 `.[matting]`，首次下模型权重）。

## 测试

```bash
pytest tests/test_composition.py         # 合成与还原度逻辑（无需 DB）
```
