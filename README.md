# ShotSmith

AI 电商商品素材图生成工具：**一张商品图 + 可选描述 → 一套可上架素材图**（白底主图 + 多场景图 + 多尺寸），并对每张做**商品还原度校验**。

第一约束：**AI 只换背景，绝不篡改商品本体**（款式 / 颜色 / 材质 / Logo）。整条链路围绕"抠图 + 商品保持"设计。

设计文档见 [`docs/`](docs/)：需求 / 技术架构选型 / 概要设计 / 数据库设计。

## 技术栈

- **后端**：FastAPI（API:28000）+ Celery（Redis broker）+ SQLAlchemy（MySQL）
- **前端**：React + Vite + TypeScript（25173）
- **抠图**：rembg / BiRefNet（SOTA，可选 simple 纯 Pillow 兜底）
- **场景生成**：Pillow 纯色合成（离线）/ 阿里通义万相·背景生成（在线 AI），**按任务可选**
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
④ generate    [在线引擎] Qwen-VL 看抠图写场景提示词
              白底主图(Pillow合成) + 场景图(引擎可选)  04_white_bg/  05_scene/
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
| 场景生成 `imagegen` | `ImageGenProvider.generate` | `local`(纯色合成) / `aliyun_bg`(通义万相·背景生成) / `vendor_a`(预留) | **页面按任务选** → `options.scene_engine`，缺省回落 `IMAGEGEN_PROVIDER` |
| 还原度 `fidelity` | `FidelityProvider.score` | `simple`(Pillow) / `dinov2`(向量，需 torch) | `FIDELITY_PROVIDER` |

白底主图始终走 Pillow 合成（商品像素原样粘贴，还原度天然≈1）；**场景图引擎**才是页面那个下拉切换的对象。

## 场景图引擎：纯色 vs 在线万相

页面表单下拉「场景图引擎」每次任务可选，随 `options={scene_engine}` 提交：

- **`local`（纯色背景 · 离线免费）**：把抠图贴到预设渐变背景并加投影，商品像素保持。
- **`aliyun_bg`（在线万相 AI · 调用阿里）**：商品主体放到透明画布做 base，调阿里**图像背景生成**只生成背景、保留前景商品。

`aliyun_bg` 流程（[`app/providers/imagegen/aliyun_bg.py`](app/providers/imagegen/aliyun_bg.py)）：每尺寸建透明底主体图 → `OssUtils` 上传得 `oss://` URL → 提交异步任务（`X-DashScope-Async`，`n` 一次多张候选）→ 轮询 `tasks/{id}` 至 `SUCCEEDED` → 下载结果。商品位置 `bbox` 随结果回传，使还原度校验只比对商品区域；网络瞬断有传输层重试。

启用在线万相：

```bash
pip install -e ".[aliyun]"        # 仅用 dashscope 的 OssUtils 上传本地图
# .env 填 百炼统一 API-KEY（通义/千问/万相共用）
DASHSCOPE_API_KEY=sk-xxxx
```

未配 key 而选了在线引擎，任务会失败并在 UI 显示明确错误（不静默）。

## Qwen-VL 看图写提示词（调用万相前的一步）

在线引擎（`aliyun_bg` / `vendor_a`）生成场景图前，先让多模态大模型 **Qwen-VL 结合「去背景后的商品图」理解分析**，产出一段只描述背景场景的中文提示词，作为万相背景生成的 `ref_prompt`——比固定模板更贴合商品品类/材质/调性。实现见 [`app/services/prompt_vlm.py`](app/services/prompt_vlm.py)，编排与回落见 [`app/services/prompt.py`](app/services/prompt.py)`resolve_scene_prompt`。

- 走 DashScope **OpenAI 兼容端点**，抠图以 base64 内联（喂模型前缩到长边≤1024 省 token），只依赖 `httpx`，**无需** `dashscope` SDK。
- 提示词只描述背景（光线/氛围/道具/构图），**绝不描述或改动商品本身**，契合「AI 不得篡改商品本体」第一约束。
- **失败即回落**：VLM 未开通 / 报错 / 返回空时，自动回落到模板提示词，不阻断出图。`local` 引擎用纯渐变背景、不消费 prompt，故跳过 VLM。
- 用到的提示词与来源（`vlm`/`user`/`template`）记入 scene 资产的 `gen_params`。

```bash
# .env（与万相共用百炼 API-KEY）
PROMPT_VLM_ENABLED=true
VLM_MODEL=qwen-vl-max     # 按百炼已开通模型填写；qwen-vl-max-latest 需额外权限
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
pip install -e ".[dev,matting]"          # 纯试可只 .[dev]；在线万相再加 .[aliyun]
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

# 实跑阿里背景生成：一张抠图出 5 种风格（key 经环境变量传入）
DASHSCOPE_API_KEY=sk-xxx python scripts/try_aliyun_bg.py [可选:抠图路径]
```
