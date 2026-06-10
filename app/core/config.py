from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    # 真实地址在 .env；此处仅为通用默认
    database_url: str = "mysql+pymysql://shotsmith:shotsmith@localhost:3306/shotsmith?charset=utf8mb4"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: str = "./data"

    # 模型 Provider 选择（见 app/providers/registry.py）
    # matting: rembg(质量优,需 .[matting]) / simple(纯 Pillow,离线可跑)
    matting_provider: str = "rembg"
    # rembg 模型：birefnet-general 当前质量最佳；备选 isnet-general-use / u2net
    matting_model: str = "birefnet-general"
    # imagegen: local(Pillow 合成,离线可跑) / openrouter_image(OpenRouter·Gemini 生图)
    #           / vendor_a(其它商用 API)
    imagegen_provider: str = "local"
    # fidelity: simple(Pillow 比对) / dinov2(向量相似,需 torch)
    fidelity_provider: str = "simple"

    # 商用图像 API（vendor_a 时使用）
    imagegen_api_key: str = ""
    imagegen_api_base: str = ""

    # 看图写提示词：生成场景图前先让多模态大模型结合去背景图生成场景提示词
    prompt_vlm_enabled: bool = True
    vlm_timeout: float = 60.0             # VLM 单次请求超时（秒）

    # OpenRouter：统一网关对接多家模型（VLM 看图写提示词 + Gemini 生图）
    openrouter_api_key: str = ""
    openrouter_api_base: str = "https://openrouter.ai/api/v1"
    # 视觉识别模型：必须选 input_modalities 含 image 的模型，否则带图请求会 404
    openrouter_vlm_model: str = "google/gemini-3.1-flash-lite"
    # 创意模型：为每张场景图生成不同的创意提示词。支持图片输入的模型（如
    # openai/gpt-5.5）单段看图直出；纯文本模型（如 deepseek）自动回落两段式
    openrouter_text_model: str = "openai/gpt-5.5"
    openrouter_image_model: str = "google/gemini-3.1-flash-image-preview"
    openrouter_image_size: str = "1K"     # image_config.image_size：0.5K/1K/2K/4K
    openrouter_image_timeout: float = 300.0  # 出图单次请求超时（秒）

    # 还原度阈值 τ：低于此值的素材转人工复核
    fidelity_threshold: float = 0.85

    # 访问鉴权：前端输入密码 → /auth/login 换取签名令牌 → 后续请求带 Bearer
    auth_enabled: bool = True
    access_password: str = "frankz61_shotsmith"
    # 令牌 HMAC 签名密钥（生产务必在 .env 覆盖为随机值）
    auth_secret: str = "shotsmith-dev-secret-change-me"
    auth_token_ttl: int = 7 * 24 * 3600   # 令牌有效期（秒），默认 7 天


settings = Settings()
