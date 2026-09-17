"""全局配置：所有配置项均可用 AGENTFLOW_ 前缀的环境变量覆盖。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENTFLOW_",
        env_file=(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AgentFlow"
    version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    data_dir: Path = PROJECT_ROOT / "data"
    frontend_dir: Path = PROJECT_ROOT / "frontend"

    # ----- LLM -----
    llm_provider: str = "mock"  # mock | openai_compatible
    llm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    llm_api_key: str = ""
    llm_model: str = "glm-4-flash"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    llm_timeout: float = 120.0

    # ----- Embedding -----
    embedding_provider: str = "local"  # local | openai_compatible
    embedding_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    embedding_api_key: str = ""
    embedding_model: str = "embedding-3"
    embedding_dim: int = 512

    # ----- 网关 -----
    auth_enabled: bool = False
    api_key: str = "agentflow-dev-key"
    rate_limit_per_minute: int = 60
    cors_origins: list[str] = ["*"]

    # ----- Agent 运行时 -----
    max_iterations: int = 6
    memory_window: int = 10
    rag_top_k: int = 4
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 80
    tool_timeout: float = 30.0

    # 离线开关：关闭后 web_search / web_read 直接返回模拟数据
    net_tools_enabled: bool = True

    # ----- 派生路径 -----
    @property
    def db_path(self) -> Path:
        return self.data_dir / "agentflow.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def charts_dir(self) -> Path:
        return self.data_dir / "charts"

    @property
    def sandbox_dir(self) -> Path:
        return self.data_dir / "sandbox"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.uploads_dir, self.charts_dir, self.sandbox_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
