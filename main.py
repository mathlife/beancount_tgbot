#!/usr/bin/env python3
"""
TG_bot - Telegram Beancount 记账机器人

简化的入口脚本，主要逻辑已拆分到 src 模块。
"""
from src.config import load_config
from src.bot.app import create_application
from src.utils.logger import setup_logger


def main():
    """主入口函数"""
    # 初始化日志
    setup_logger()
    
    # 加载配置
    config = load_config()
    
    # 创建并运行 Bot
    app = create_application(config)
    print("Bot is running...")
    app.run_polling()


if __name__ == '__main__':
    main()
