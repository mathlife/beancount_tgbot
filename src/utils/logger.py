"""
日志配置模块

提供统一的日志配置和获取方式。
"""
import logging
import sys
from typing import Optional


# 日志格式
DEFAULT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
SIMPLE_FORMAT = '%(levelname)s - %(message)s'


def setup_logger(
    name: str = "TG_bot",
    level: int = logging.INFO,
    format_string: str = DEFAULT_FORMAT,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    配置并返回 logger
    
    Args:
        name: 日志名称
        level: 日志级别
        format_string: 日志格式
        log_file: 可选的日志文件路径
    
    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    logger.setLevel(level)
    
    # 控制台输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(format_string))
    logger.addHandler(console_handler)
    
    # 文件输出（可选）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(format_string))
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "TG_bot") -> logging.Logger:
    """获取已配置的 logger"""
    return logging.getLogger(name)


# 预配置的模块日志器
def get_bot_logger() -> logging.Logger:
    """获取 Bot 模块日志器"""
    return get_logger("TG_bot.bot")


def get_core_logger() -> logging.Logger:
    """获取核心模块日志器"""
    return get_logger("TG_bot.core")


def get_ai_logger() -> logging.Logger:
    """获取 AI 模块日志器"""
    return get_logger("TG_bot.ai")
