"""
自定义异常类型

定义项目中使用的异常类，便于统一错误处理。
"""


class TGBotError(Exception):
    """TG_bot 基础异常类"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
    
    def __str__(self):
        if self.details:
            return f"{self.message} - {self.details}"
        return self.message


class ParseError(TGBotError):
    """解析失败异常"""
    
    def __init__(self, message: str, input_text: str = "", details: dict = None):
        super().__init__(message, details)
        self.input_text = input_text


class LedgerWriteError(TGBotError):
    """写入账本失败异常"""
    
    def __init__(self, message: str, file_path: str = "", details: dict = None):
        super().__init__(message, details)
        self.file_path = file_path


class LedgerValidationError(TGBotError):
    """账本验证失败异常"""
    pass


class ConfigError(TGBotError):
    """配置错误异常"""
    
    def __init__(self, message: str, config_key: str = "", details: dict = None):
        super().__init__(message, details)
        self.config_key = config_key


class AIServiceError(TGBotError):
    """AI 服务异常"""
    
    def __init__(self, message: str, service_name: str = "Gemini", details: dict = None):
        super().__init__(message, details)
        self.service_name = service_name


class RateLimitError(AIServiceError):
    """API 限流异常"""
    
    def __init__(self, message: str = "API rate limit exceeded", retry_after: int = 0):
        super().__init__(message)
        self.retry_after = retry_after


class SessionExpiredError(TGBotError):
    """会话过期异常"""
    pass


class AmbiguousAliasError(TGBotError):
    """别名歧义异常"""
    
    def __init__(self, message: str, alias: str, candidates: list):
        super().__init__(message)
        self.alias = alias
        self.candidates = candidates
