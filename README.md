# ShotSmith

AI 电商商品素材图生成工具：**一张商品图 + 可选描述 → 一套可上架素材图**（白底主图 + 多场景图 + 多尺寸），并对每张做**商品还原度校验**。

第一约束：**AI 只换背景，绝不篡改商品本体**（款式 / 颜色 / 材质 / Logo）。整条链路围绕"抠图 + 商品保持"设计。

设计文档见 [`docs/`](docs/)：需求 / 技术架构选型 / 概要设计 / 数据库设计。

## 技术栈

- **后端**：FastAPI（API:28000）+ Celery（Redis broker）+ SQLAlchemy（MySQL）
- **前端**：React + Vite + TypeScript（25173）
- **抠图**：rembg / BiRefNet（SOTA，可选 simple 纯 Pillow 兜底）
- **场景生成**：Pillow 纯色合成（离线）/ OpenRouter·Gemini 生图（在线 AI），**按任务可选**
- **还原度校验**：Pillow 比对（可选 DINOv2 向量相似）

> Redis 与 MySQL 为外部服务，连接串在 `.env`（已 gitignore，勿提交）。

## 整体流程

任务由前端创建后入 Redis 队列，Celery worker 跑六阶段流水线，逐阶段写回状态 / 进度，产物落库为 asset：

```
上传图/URL ─▶ POST /api/v1/tasks ─▶ Redis 队列 ─▶ Celery: orchestrator.run()
                                                        │
  ┌─────────────────────────────────────────────────────┘
  ▼
① ingest      取源图（上传落盘 / URL 下载）            00_source.*
② preprocess  尺寸校验(≥300) + 限制最长边(≤2000)      02_input.png
③ matting     抠图 → RGBA 透明主体 + mask             03_cutout/product.png
④ generate    [在线引擎] 两段式提示词：VLM 识图 + 文本模型出 5 条创意提示词
              白底主图(Pillow合成) + 场景图 5 张(尺寸轮流分配,每张一条提示词)
                                                      04_white_bg/  05_scene/
⑤ quality     比对商品区域算还原度，打 qc_status        （写回 asset）
⑥ package     生成 metadata.json，可打包 zip 下载       metadata.json
```

- 进度：`pending → processing(ingest…package) → success / partial / failed`；任一张需复核则整体 `partial`。
- 前端轮询 `GET /tasks/{id}` 刷新状态与素材网格。
- 产物目录：`data/tasks/{task_id}/`（`00_source` / `02_input` / `03_cutout/` / `04_white_bg/` / `05_scene/` / `metadata.json`）。

## Provider 架构（换实现 = 改配置 / 选项）

业务层只依赖抽象协议（[`app/providers/base.py`](app/providers/base.py)），由 [`registry.py`](app/providers/registry.py) 按配置或**按任务**选择具体实现：

| 类型 | 协议 | 可选实现 | 选择方式 |
|---|---|---|---|
| 抠图 `matting` | `MattingProvider.cutout` | `rembg`(BiRefNet，质量优) / `simple`(Pillow 离线) | `MATTING_PROVIDER` |
| 场景生成 `imagegen` | `ImageGenProvider.generate` | `local`(纯色合成) / `openrouter_image`(OpenRouter·Gemini 生图) / `vendor_a`(预留) | **页面按任务选** → `options.scene_engine`，缺省回落 `IMAGEGEN_PROVIDER` |
| 还原度 `fidelity` | `FidelityProvider.score` | `simple`(Pillow) / `dinov2`(向量，需 torch) | `FIDELITY_PROVIDER` |

白底主图始终走 Pillow 合成（商品像素原样粘贴，还原度天然≈1）；**场景图引擎**才是页面那个下拉切换的对象。

## 场景图引擎：纯色 vs OpenRouter·Gemini 生图

页面表单「场景图引擎」每次任务可选，随 `options={scene_engine}` 提交：

- **`local`（纯色背景 · 离线免费）**：把抠图贴到预设渐变背景并加投影，商品像素保持。
- **`openrouter_image`（Gemini 生图 · 经 OpenRouter）**：商品主体放到透明画布做 base，
  经 OpenRouter 调 `google/gemini-3.1-flash-image-preview`（Nano Banana 2）补全背景、保留前景商品。

`openrouter_image` 流程（[`app/providers/imagegen/openrouter_image.py`](app/providers/imagegen/openrouter_image.py)）：每尺寸建透明底主体图 → 以 base64 data URI 随 `chat/completions` 请求提交（`modalities=["image","text"]`，`image_config` 控制比例与分辨率档位）→ 从 `message.images` 解码 base64 结果 → 缩放到精确导出尺寸。商品位置 `bbox` 随结果回传，使还原度校验只比对商品区域；网络瞬断有传输层重试。

启用 OpenRouter 生图（无需额外依赖，只用 `httpx`）：

```bash
# .env 填 OpenRouter API-KEY（https://openrouter.ai/keys）
OPENROUTER_API_KEY=sk-or-v1-xxxx
```

未配 key 而选了在线引擎，任务会失败并在 UI 显示明确错误（不静默）。

## 两段式提示词：VLM 识图 + 文本模型创意（在线生图前的一步）

在线引擎（`openrouter_image` / `vendor_a`）生成场景图前，为**每张图各产出一条不同的创意提示词**（默认 5 张 → 5 条），经 OpenRouter 两段完成：

1. **视觉识别**（`OPENROUTER_VLM_MODEL`，默认 `gemini-3.1-flash-lite`）：看「去背景后的商品图」输出一句客观商品描述；
2. **创意生成**（`OPENROUTER_TEXT_MODEL`，默认 `deepseek/deepseek-v4-pro`）：结合商品描述 + 平台/品类/链接约束，一次产出 N 条场景方向各异（家居/户外/节日/棚拍/质感特写…）的中文提示词（JSON 数组）。

实现见 [`app/services/prompt_vlm.py`](app/services/prompt_vlm.py)，编排与回落见 [`app/services/prompt.py`](app/services/prompt.py)`resolve_scene_prompts`。

- 走 OpenRouter **OpenAI 兼容端点**，抠图以 base64 内联（喂模型前缩到长边≤1024 省 token），只依赖 `httpx`。
- 为何拆两段：deepseek 系列为纯文本模型（带图请求 OpenRouter 返回 404），视觉小模型负责"看"、创意模型负责"想"，各取所长。
- 提示词只描述背景（光线/氛围/道具/构图），**绝不描述或改动商品本身**，契合「AI 不得篡改商品本体」第一约束。
- 支持跨境卖家约束：货源参考链接（自动抓取标题/描述）+ 目标平台（亚马逊/Walmart/通用）注入提示词，避免场景跑偏。
- **失败即回落**：任一段报错/返回空时，自动回落到「模板 + 5 种风格变化」，不阻断出图。`local` 引擎用纯渐变背景、不消费 prompt，故跳过。
- 每张 scene 资产的 `gen_params` 记录自己用的那条提示词与来源（`vlm`/`user`/`template`）。

```bash
# .env（与生图共用 OpenRouter API-KEY）
PROMPT_VLM_ENABLED=true
OPENROUTER_VLM_MODEL=google/gemini-3.1-flash-lite
OPENROUTER_TEXT_MODEL=deepseek/deepseek-v4-pro
```

## 数据模型

- **task**：`status / current_stage / progress / source_type / source_ref / description / options(JSON) / error_message / 时间戳`
- **asset**：`task_id / type(cutout|white_bg|scene) / size_label / path / fidelity_score / qc_status(passed|needs_review|pending) / selected / gen_params(JSON: provider,prompt,bbox…)`

## API（前缀 `/api/v1`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/tasks` | 创建任务（multipart：`file`/`url` + `description` + `options`），入队 |
| GET | `/tasks` | 历史列表（轻量摘要） |
| GET | `/tasks/{id}` | 任务详情 + 素材 |
| GET | `/tasks/{id}/assets` | 素材列表 |
| POST | `/tasks/{id}/regenerate` | 复用 `options` 重跑 |
| POST | `/assets/{id}/select` | 勾选/取消选用 |
| GET | `/tasks/{id}/package` | 打包下载 zip |

静态产物经 `/files/{path}` 访问；健康检查 `/health`。

## 启动

VS Code 调试面板：`1) Init DB` 建表一次 → `全部启动 (API + Worker + 前端)`。或命令行：

```bash
pip install -e ".[dev,matting]"          # 纯试可只 .[dev]
python scripts/init_db.py                # 建表（首次）

uvicorn app.main:app --host 127.0.0.1 --port 28000
# Windows 下 Celery 需 solo 池：
celery -A app.tasks.celery_app.celery_app worker --loglevel=info --pool=solo

cd web && npm install && npm run dev      # 前端 25173
```

访问：前端 http://localhost:25173 ，后端文档 http://localhost:28000/docs 。

> 开箱即跑可把 `MATTING_PROVIDER=simple`（纯 Pillow，仅适合纯色背景图）；最高质量用 `rembg` + `birefnet-general`（需 `.[matting]`，首次下模型权重）。

## 测试与试跑

```bash
pytest tests/test_composition.py          # 合成与还原度逻辑（无需 DB）
```
