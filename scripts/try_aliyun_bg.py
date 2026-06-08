"""通义万相·背景生成试跑：用一张商品抠图生成 5 种不同风格的场景图。

用法（key 经环境变量传入，勿写进文件）：
    DASHSCOPE_API_KEY=sk-xxx python scripts/try_aliyun_bg.py [可选:抠图路径]

输出落到 data/aliyun_demo/NN_风格.png，并打印每张的 task_id 与耗时。
"""
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.providers.imagegen.aliyun_bg import AliyunBackgroundProvider  # noqa: E402

# 默认用仓库里已有的连帽夹克抠图（RGBA 透明 PNG）
DEFAULT_CUTOUT = (
    "data/tasks/322c6180-0815-4e57-9a27-046e6353f55f/03_cutout/product.png"
)
OUT_DIR = Path("data/aliyun_demo")
SIZE = [("3:4", 900, 1200)]  # 服装常用竖图；每个任务 n=1，5 个风格=5 张

# 5 种风格的背景引导词（描述场景/背景，主体夹克由 API 原样保留；中文≤120字）
STYLES: list[tuple[str, str]] = [
    ("纯色影棚", "简约影棚浅灰渐变背景，柔和均匀布光，干净通透，高级电商服装主图风格"),
    ("都市街拍", "城市街头水泥墙与玻璃幕墙背景，午后斜射阳光，光影层次分明，时尚街拍氛围"),
    ("户外山野", "户外山野自然风光，远处山峦与松林绿植，清新晨雾微光，徒步户外运动氛围"),
    ("暖调家居", "原木质感桌面搭配暖色家居背景，自然柔光，温馨松弛的生活方式场景"),
    ("高级质感", "深色高级质感背景，戏剧化侧逆聚光，冷调光影对比，高端品牌大片质感"),
]


def main() -> None:
    if not os.environ.get("DASHSCOPE_API_KEY"):
        sys.exit("请用 DASHSCOPE_API_KEY=sk-xxx 环境变量传入 key")
    cutout = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CUTOUT
    if not Path(cutout).exists():
        sys.exit(f"抠图不存在：{cutout}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prov = AliyunBackgroundProvider()
    ok = 0
    for i, (name, prompt) in enumerate(STYLES, 1):
        t0 = time.monotonic()
        tmp = OUT_DIR / f"_tmp_{i}"
        try:
            gens = prov.generate(cutout, prompt, {"out_dir": str(tmp), "sizes": SIZE, "variants": 1})
            dst = OUT_DIR / f"{i:02d}_{name}.png"
            shutil.copy(gens[0].path, dst)
            shutil.rmtree(tmp, ignore_errors=True)
            ok += 1
            print(f"[{i}/5] {name:6s} OK  {time.monotonic() - t0:5.1f}s  "
                  f"task={gens[0].meta.get('task_id')}  -> {dst}")
        except Exception as e:  # 单个风格失败不影响其余
            print(f"[{i}/5] {name:6s} 失败  {time.monotonic() - t0:5.1f}s  {e}")
    print(f"\n完成 {ok}/5，输出目录：{OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
