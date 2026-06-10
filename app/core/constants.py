"""尺寸、阈值与场景预设等静态配置。"""

# 导出尺寸（像素），label -> (width, height)
SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "1:1": (1000, 1000),
    "3:4": (900, 1200),
    "4:5": (1080, 1350),
}
DEFAULT_SIZES: list[str] = ["1:1", "3:4", "4:5"]
# 场景图总张数：轮流分配到所选尺寸，每张配一条不同的创意提示词
DEFAULT_SCENE_COUNT: int = 5

MIN_SOURCE_SIZE: int = 300   # 源图最短边下限
MAX_SIDE: int = 2000         # 预处理时的最长边上限

# 场景图渐变背景预设（顶部色 -> 底部色）
SCENE_PRESETS: list[dict] = [
    {"name": "奶油风", "top": (250, 244, 233), "bottom": (234, 223, 205)},
    {"name": "北欧灰", "top": (234, 236, 238), "bottom": (206, 210, 214)},
    {"name": "清新绿", "top": (233, 240, 233), "bottom": (205, 221, 205)},
    {"name": "暖阳米", "top": (248, 242, 232), "bottom": (226, 212, 190)},
    {"name": "冷调蓝", "top": (232, 238, 243), "bottom": (202, 214, 226)},
]
