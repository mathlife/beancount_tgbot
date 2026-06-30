"""
TG_bot - Telegram Beancount 记账机器人

主模块入口。
"""
from src.config import load_config, get_config, AppConfig

__version__ = "1.0.0"

__all__ = [
    'load_config',
    'get_config',
    'AppConfig',
]
