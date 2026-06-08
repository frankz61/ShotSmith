class DinoV2Provider:
    """DINOv2 嵌入余弦相似度做还原度校验（需 torch，质量更高）。"""

    def score(self, original: str, generated: str, bbox: tuple | None = None) -> float:
        raise NotImplementedError("TODO: 加载 DINOv2，提取商品区域嵌入并计算余弦相似度")
