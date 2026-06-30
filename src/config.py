"""
配置管理模块

集中化加载和管理所有配置，支持类型检查。
"""
import os
from dataclasses import dataclass, field
from typing import Dict, Optional
from pathlib import Path
import yaml
from dotenv import load_dotenv


@dataclass
class SystemConfig:
    """系统配置"""
    currency: str
    bean_file: str
    append_file: str


@dataclass
class AppConfig:
    """应用配置"""
    telegram_token: str
    allowed_user_id: int
    gemini_api_key: str
    aliases: Dict[str, str]
    system: SystemConfig
    
    @property
    def bean_file_path(self) -> str:
        """获取 Beancount 主文件路径"""
        return self.system.bean_file
    
    @property
    def append_file_path(self) -> str:
        """获取追加文件路径"""
        return self.system.append_file
    
    @property
    def default_currency(self) -> str:
        """获取默认货币"""
        return self.system.currency


def load_config(config_dir: str = "config") -> AppConfig:
    """
    加载所有配置
    
    Args:
        config_dir: 配置目录路径，默认为 "config"
    
    Returns:
        AppConfig 实例
    
    Raises:
        ValueError: 配置文件缺失或格式错误
    """
    # 加载环境变量
    env_path = Path(config_dir) / ".env"
    load_dotenv(env_path)
    
    # 加载 YAML 配置
    settings_path = Path(config_dir) / "settings.yaml"
    if not settings_path.exists():
        raise ValueError(f"配置文件不存在: {settings_path}")
    
    with open(settings_path, 'r', encoding='utf-8') as f:
        settings = yaml.safe_load(f)
    
    # 验证必要的环境变量
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not telegram_token:
        raise ValueError("缺少环境变量: TELEGRAM_BOT_TOKEN")
    
    allowed_user_id = os.getenv('ALLOWED_USER_ID')
    if not allowed_user_id:
        raise ValueError("缺少环境变量: ALLOWED_USER_ID")
    
    gemini_api_key = os.getenv('GEMINI_API_KEY', '')
    
    # 验证 YAML 配置
    if 'system' not in settings:
        raise ValueError("配置文件缺少 'system' 部分")
    
    system_cfg = settings['system']
    
    return AppConfig(
        telegram_token=telegram_token,
        allowed_user_id=int(allowed_user_id),
        gemini_api_key=gemini_api_key,
        aliases=settings.get('aliases', {}),
        system=SystemConfig(
            currency=system_cfg.get('currency', 'CNY'),
            bean_file=system_cfg.get('bean_file', 'data/main.bean'),
            append_file=system_cfg.get('append_file', system_cfg.get('bean_file', 'data/main.bean'))
        )
    )


# 全局配置实例（可选使用）
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """获取全局配置实例"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> AppConfig:
    """重新加载配置"""
    global _config
    _config = load_config()
    return _config
