"""
交易相关数据模型

使用 dataclass 定义核心数据类型，替代字典传递，提高代码可维护性。
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, List, Union


@dataclass
class DiscountInfo:
    """优惠/折扣信息"""
    account: str
    amount: float
    
    def to_tuple(self) -> tuple:
        """转换为元组格式，兼容旧代码"""
        return (self.account, self.amount)
    
    @classmethod
    def from_tuple(cls, data: tuple) -> 'DiscountInfo':
        """从元组创建实例"""
        return cls(account=data[0], amount=data[1])


@dataclass
class AmountBlock:
    """金额解析块"""
    amount: float
    currency: Optional[str] = None
    converted_amount: Optional[float] = None
    converted_currency: Optional[str] = None
    token_count: int = 1  # 占用的 token 数量
    
    @property
    def has_conversion(self) -> bool:
        """是否包含货币转换"""
        return self.converted_amount is not None and self.converted_currency is not None


@dataclass
class ParseResult:
    """位置解析结果"""
    payee: str
    narration: str
    amount: float
    asset: str
    currency: Optional[str] = None
    converted_amount: Optional[float] = None
    converted_currency: Optional[str] = None
    discount_info: Optional[DiscountInfo] = None
    raw_asset_token: str = ""
    
    def to_dict(self) -> dict:
        """转换为字典格式，兼容旧代码"""
        result = {
            "payee": self.payee,
            "narration": self.narration,
            "amount": self.amount,
            "currency": self.currency,
            "converted_amount": self.converted_amount,
            "converted_currency": self.converted_currency,
            "asset": self.asset,
            "raw_asset_token": self.raw_asset_token,
            "discount_info": None
        }
        if self.discount_info:
            # 兼容旧格式 (account, amount) 或 ([accounts], amount)
            result["discount_info"] = self.discount_info.to_tuple()
        return result


@dataclass
class PendingTransaction:
    """待确认交易"""
    date: date
    payee: str
    narration: str
    amount: float
    currency: str
    asset: str
    expense: str
    converted_amount: Optional[float] = None
    converted_currency: Optional[str] = None
    discount_info: Optional[DiscountInfo] = None
    
    def to_dict(self) -> dict:
        """转换为字典格式，兼容 context.user_data 存储"""
        return {
            'date': self.date,
            'payee': self.payee,
            'narration': self.narration,
            'amount': self.amount,
            'currency': self.currency,
            'converted_amount': self.converted_amount,
            'converted_currency': self.converted_currency,
            'asset': self.asset,
            'expense': self.expense,
            'discount_info': self.discount_info.to_tuple() if self.discount_info else None
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PendingTransaction':
        """从字典创建实例"""
        discount_info = None
        if data.get('discount_info'):
            discount_info = DiscountInfo.from_tuple(data['discount_info'])
        
        return cls(
            date=data['date'],
            payee=data.get('payee', ''),
            narration=data['narration'],
            amount=data['amount'],
            currency=data['currency'],
            asset=data['asset'],
            expense=data['expense'],
            converted_amount=data.get('converted_amount'),
            converted_currency=data.get('converted_currency'),
            discount_info=discount_info
        )


@dataclass
class AmbiguousDiscount:
    """歧义优惠数据"""
    candidates: List[str]
    amount: float
    description: str
    original_data: Optional[dict] = None
    asset_candidates: Optional[List[str]] = None


@dataclass
class AmbiguousAsset:
    """歧义资产数据"""
    candidates: List[str]
    description: str
    amount: float
    discount_info: Optional[DiscountInfo] = None
