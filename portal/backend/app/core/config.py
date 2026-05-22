from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "mysql+pymysql://root:changeme@localhost:3306/portal_db"
    SECRET_KEY: str = "changeme-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480  # 8 hours
    COOKIE_SECURE: bool = False  # 生产环境通过 env 设为 True(HTTPS 时)
    DS_API_URL: str = "http://dolphinscheduler:12345/dolphinscheduler"
    DS_ADMIN_USER: str = "admin"
    DS_ADMIN_PASSWORD: str = "changeme"
    OM_API_URL: str = "http://localhost:8585"
    # 内部存为逗号分隔字符串,通过 CORS_ORIGINS property 暴露 List[str]
    # 默认仅放本机开发,生产通过 env CORS_ORIGINS=https://a.com,https://b.com 注入
    CORS_ORIGINS_RAW: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="CORS_ORIGINS",
    )
    REDIS_URL: str = "redis://localhost:6379/0"
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 300
    ADMIN_INIT_PASSWORD: str = "admin123"
    SQL_QUERY_TIMEOUT_SEC: int = 30

    @property
    def CORS_ORIGINS(self) -> List[str]:
        return [item.strip() for item in self.CORS_ORIGINS_RAW.split(",") if item.strip()]


settings = Settings()
