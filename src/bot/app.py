"""
Telegram Bot 应用构建器

创建和配置 Telegram Bot Application。
"""
from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters
)

from src.config import AppConfig
from src.core.loader import BeanLoader
from src.core.matcher import HybridMatcher
from src.core.ledger import LedgerAppender
from src.core.transaction_log import TransactionLog
from src.utils.ai_client import GeminiClient
from src.utils.logger import setup_logger, get_bot_logger
from .handlers import MessageHandlers
from .callbacks import CallbackHandlers

logger = get_bot_logger()


class BotContext:
    """Bot 上下文，存储共享组件"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.loader = BeanLoader(config.bean_file_path)
        self.ai_client = GeminiClient(api_key=config.gemini_api_key)
        self.matcher = HybridMatcher(self.loader, self.ai_client, config.aliases)
        self.ledger = LedgerAppender(config.append_file_path)
        self.tx_log = TransactionLog()
        
        # 初始加载
        self.loader.load()
        logger.info(f"已加载 {len(self.loader.all_accounts)} 个账户")
    
    def reload_bean(self):
        """重新加载 Beancount 文件"""
        self.loader.load()
        return len(self.loader.all_accounts)
    
    def reload_config(self):
        """重新加载配置"""
        from src.config import load_config
        new_config = load_config()
        self.config = new_config
        self.matcher.local_expenses_map = new_config.aliases
        return True


def create_application(config: AppConfig):
    """
    创建并配置 Telegram Bot Application
    
    Args:
        config: AppConfig 实例
    
    Returns:
        配置好的 Application 实例
    """
    # 初始化日志
    setup_logger()
    
    # 创建上下文
    ctx = BotContext(config)
    
    # 创建处理器
    msg_handlers = MessageHandlers(ctx.matcher, ctx.ledger, config, ctx.tx_log)
    cb_handlers = CallbackHandlers(ctx.matcher, ctx.ledger, config, ctx.tx_log)
    
    # 注册启动通知
    async def post_init(application):
        await application.bot.set_my_commands([
            BotCommand("start", "查看使用说明"),
            BotCommand("today", "查看今日交易汇总"),
            BotCommand("recent", "查看最近已存交易"),
            BotCommand("undo", "撤销最后一笔交易"),
            BotCommand("reload", "重新加载配置和账本"),
        ])
        await application.bot.send_message(
            chat_id=config.allowed_user_id,
            text="🚀 Beancount Bot 已启动！"
        )
    
    # 构建 Application
    application = (
        ApplicationBuilder()
        .token(config.telegram_token)
        .post_init(post_init)
        .build()
    )
    
    # 存储上下文到 bot_data
    application.bot_data['ctx'] = ctx
    
    # 注册处理器
    application.add_handler(CommandHandler('start', msg_handlers.start))
    application.add_handler(CommandHandler('reload', msg_handlers.reload_data))
    application.add_handler(CommandHandler('undo', msg_handlers.undo_last))
    application.add_handler(CommandHandler('today', msg_handlers.today_summary))
    application.add_handler(CommandHandler('recent', msg_handlers.recent_transactions))
    application.add_handler(CallbackQueryHandler(cb_handlers.button_handler))
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.IMAGE,
        msg_handlers.image_handler
    ))
    application.add_handler(MessageHandler(
        filters.TEXT & (~filters.COMMAND), 
        msg_handlers.text_handler_wrapper
    ))
    
    return application

