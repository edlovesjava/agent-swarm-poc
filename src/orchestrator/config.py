"""Configuration management."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment."""
    
    # GitHub App
    github_app_id: str
    github_app_private_key: str
    github_webhook_secret: str
    
    # Anthropic
    anthropic_api_key: str
    
    # Redis
    redis_url: str = "redis://localhost:6379"
    
    # Logging
    log_level: str = "INFO"
    
    # Coordination
    file_lock_ttl_seconds: int = 1800  # 30 minutes
    max_concurrent_agents: int = 3
    
    # Cost tracking
    cost_alert_threshold_usd: float = 10.0
    
    # Models
    model_haiku: str = "claude-haiku-4-5-20251001"
    model_sonnet: str = "claude-sonnet-4-5-20250929"
    model_opus: str = "claude-opus-4-5-20251101"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
