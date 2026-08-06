import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import List, Optional
from sqlalchemy.engine.url import URL

class Settings(BaseSettings):
    API_SERVICE_ENV: str = "dev"
    API_SERVICE_PORT: int = 8001
    LOG_LEVEL: str = "INFO"
    # Empty means same-origin only. Cross-origin deployments must enumerate origins.
    ALLOWED_ORIGINS: List[str] = []
    APP_PUBLIC_URL: Optional[str] = None
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    LOGIN_RATE_LIMIT: int = 10
    CHAT_RATE_LIMIT: int = 60
    CODE_EXECUTION_RATE_LIMIT: int = 10
    BROWSER_SESSION_TTL_SECONDS: int = 3600

    # Main database type: mysql (default) / postgresql
    DATABASE_TYPE: str = "mysql"

    # MySQL
    MYSQL_HOST: Optional[str] = None
    MYSQL_PORT: int = 3306
    MYSQL_DB: Optional[str] = None
    MYSQL_USER: Optional[str] = None
    MYSQL_PASSWORD: Optional[str] = None
    MYSQL_POOL_SIZE: int = 20
    MYSQL_MAX_OVERFLOW: int = 50
    MYSQL_POOL_RECYCLE: int = 3600

    # PostgreSQL (used when DATABASE_TYPE=postgresql)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None  # 改为 Optional 且默认为 None
    REDIS_ENABLE: bool = True

    # Security - API Key Encryption
    # Fernet Key (32 url-safe base64-encoded bytes)
    ENCRYPTION_KEY: str

    # LLM Gateway
    LLM_BASE_URL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL_NAME: Optional[str] = None
    LLM_TEMPERATURE: Optional[float] = None

    # External SQL API
    EXTERNAL_SQL_API_URL: Optional[str] = None
    EXTERNAL_SQL_API_KEY: Optional[str] = None

    # Metadata & RAG
    METADATA_PROVIDER: str = "local" # local / ragflow
    RAGFLOW_API_URL: Optional[str] = None
    RAGFLOW_API_KEY: Optional[str] = None

    # Ebbinghaus Memory Configs
    MEMORY_BASE_HALF_LIFE: float = 7.0
    MEMORY_CONSOLIDATION_THRESHOLD: float = 0.82

    # SSO Configuration
    SSO_API_URL: str = "https://yovole.net/api/v1/user/check/login"
    # Never ship a usable SSO credential in source. Deployments must inject it.
    SSO_ACCESS_TOKEN: str = "CHANGE_ME_SSO_ACCESS_TOKEN"
    SSO_REQUEST_SYSTEM: str = "NANZI_AI_AGENT_PLATFORM"
    SSO_REQUEST_BUSINESS: str = "USER-LOGIN"
    SSO_TIMEOUT: int = 30

    def validate_runtime_configuration(self) -> None:
        """Reject unusable placeholder secrets before a production process serves traffic."""
        if self.API_SERVICE_ENV.strip().lower() not in {"prod", "production"}:
            return

        required_values = {
            "ENCRYPTION_KEY": self.ENCRYPTION_KEY,
            "SSO_ACCESS_TOKEN": self.SSO_ACCESS_TOKEN,
        }
        errors = [
            f"{name} 未配置"
            for name, value in required_values.items()
            if not str(value or "").strip()
            or str(value).strip().startswith(("CHANGE_ME_", "GENERATE_A_"))
        ]
        if not self.SSO_API_URL.strip().lower().startswith("https://"):
            errors.append("SSO_API_URL 必须使用 HTTPS")
        if "*" in self.ALLOWED_ORIGINS:
            errors.append("ALLOWED_ORIGINS 禁止使用通配符")
        if errors:
            raise ValueError("生产环境禁止使用占位安全配置: " + ", ".join(errors))

    @property
    def SKILLS_DIR(self) -> str:
        container_path = "/app/data/skills"
        if os.path.exists(container_path):
            return container_path
        host_path = os.path.expanduser("~/.agents/skills")
        os.makedirs(host_path, exist_ok=True)
        return host_path

    def build_mysql_url(self, driver: str = "mysql+aiomysql") -> URL:
        """构建 SQLAlchemy MySQL URL（自动对 user/password 中的 @:#/ 等特殊字符做编码）。"""
        missing = [
            name for name, value in (
                ("MYSQL_HOST", self.MYSQL_HOST),
                ("MYSQL_DB", self.MYSQL_DB),
                ("MYSQL_USER", self.MYSQL_USER),
                ("MYSQL_PASSWORD", self.MYSQL_PASSWORD),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "MySQL database configuration is incomplete; "
                f"missing: {', '.join(missing)}"
            )
        return URL.create(
            drivername=driver,
            username=self.MYSQL_USER,
            password=self.MYSQL_PASSWORD,
            host=self.MYSQL_HOST,
            port=self.MYSQL_PORT,
            database=self.MYSQL_DB,
        )

    def build_postgresql_url(self, driver: str = "postgresql+psycopg") -> URL:
        """构建 SQLAlchemy PostgreSQL URL，并对凭据中的特殊字符做编码。"""
        missing = [
            name for name, value in (
                ("POSTGRES_DB", self.POSTGRES_DB),
                ("POSTGRES_USER", self.POSTGRES_USER),
                ("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "PostgreSQL database configuration is incomplete; "
                f"missing: {', '.join(missing)}"
            )
        return URL.create(
            drivername=driver,
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    @property
    def normalized_database_type(self) -> str:
        database_type = self.DATABASE_TYPE.strip().lower()
        if database_type == "mysql":
            return "mysql"
        if database_type in {"postgres", "postgresql", "pg"}:
            return "postgresql"
        raise ValueError(f"Unsupported DATABASE_TYPE: {self.DATABASE_TYPE}")

    @property
    def DATABASE_ASYNC_URL(self) -> URL:
        if self.normalized_database_type == "postgresql":
            return self.build_postgresql_url("postgresql+psycopg")
        return self.MYSQL_ASYNC_URL

    @property
    def DATABASE_SYNC_URL(self) -> str:
        if self.normalized_database_type == "postgresql":
            return self.build_postgresql_url("postgresql+psycopg").render_as_string(hide_password=False)
        return self.MYSQL_SYNC_URL

    @property
    def MYSQL_ASYNC_URL(self) -> URL:
        return self.build_mysql_url("mysql+aiomysql")

    @property
    def MYSQL_SYNC_URL(self) -> str:
        # APScheduler 等同步组件需要字符串 URL；render 时保留已编码的密码
        return self.build_mysql_url("mysql+pymysql").render_as_string(hide_password=False)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
