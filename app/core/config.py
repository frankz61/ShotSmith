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
    # imagegen: local(Pillow 合成,离线可跑) / aliyun_bg(阿里通义万相·背景生成) / vendor_a(其它商用 API)
    imagegen_provider: str = "local"
    # fidelity: simple(Pillow 比对) / dinov2(向量相似,需 torch)
    fidelity_provider: str = "simple"

    # 商用图像 API（vendor_a 时使用）
    imagegen_api_key: str = ""
    imagegen_api_base: str = ""

    # Qwen-VL 看图写提示词：调用万相前先让多模态大模型结合去背景图生成场景提示词
    # 复用 dashscope_api_key 鉴权；走 DashScope OpenAI 兼容端点（仅需 httpx）
    prompt_vlm_enabled: bool = True
    # 多模态模型 ID：qwen3.7-plus 支持多模态看图（按百炼已开通模型填写）
    vlm_model: str = "qwen3.7-plus"
    vlm_timeout: float = 60.0             # VLM 单次请求超时（秒）

    # 阿里通义万相·背景生成（imagegen_provider=aliyun_bg 时使用，需 .[aliyun]）
    # 在百炼控制台开通后获取 API-KEY；SDK/HTTP 均用此鉴权
    dashscope_api_key: str = ""
    aliyun_bg_model: str = "wanx-background-generation-v2"
    aliyun_bg_model_version: str = "v2"   # v2 / v3（v3 需配套权限）
    aliyun_bg_noise_level: int = 300      # 0~999，越大背景与主体差异越大
    aliyun_bg_ref_prompt_weight: float = 0.5  # 0~1，文本引导权重
    aliyun_poll_interval: float = 3.0     # 轮询任务结果的间隔（秒）
    aliyun_poll_timeout: float = 180.0    # 单个任务等待上限（秒）

    # 还原度阈值 τ：低于此值的素材转人工复核
    fidelity_threshold: float = 0.85

    # 访问鉴权：前端输入密码 → /auth/login 换取签名令牌 → 后续请求带 Bearer
    auth_enabled: bool = True
    access_password: str = "frankz61_shotsmith"
    # 令牌 HMAC 签名密钥（生产务必在 .env 覆盖为随机值）
    auth_secret: str = "shotsmith-dev-secret-change-me"
    auth_token_ttl: int = 7 * 24 * 3600   # 令牌有效期（秒），默认 7 天


settings = Settings()
