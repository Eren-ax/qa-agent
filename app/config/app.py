from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.app",
    )
    stage: Literal["development", "exp", "production"] = "development"

    docs_url: Optional[str] = "/docs"
    redoc_url: Optional[str] = "/redoc"

    def model_post_init(self, _):
        if self.stage == "production":
            self.docs_url = None
            self.redoc_url = None


config = Config()
