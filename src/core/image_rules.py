import math
import os
from dataclasses import dataclass
from datetime import date
import re
from typing import List, Optional

from src.core.rules_engine import RulesEngine


@dataclass
class ExtractedImageTransaction:
    date: date
    payee: str
    receiver_name: str
    narration: str
    amount: float
    order_amount: Optional[float]
    discount_amount: Optional[float]
    currency: str
    payment_method: str
    category: str
    tx_id: str
    direction: str = ""
    transaction_time: str = ""
    notes: str = ""
    confidence: Optional[float] = None
    needs_review: bool = False


@dataclass
class PostingSpec:
    account: str
    amount: float


@dataclass
class ResolvedImageTransaction:
    date: date
    payee: str
    narration: str
    currency: str
    postings: List[PostingSpec]
    funding_account: str = ""
    counterparty_account: str = ""
    funding_index: int = 0
    counterparty_index: int = 0
    tx_id: str = ""
    category: str = ""
    method: str = ""
    transaction_time: str = ""
    notes: str = ""
    confidence: Optional[float] = None
    needs_review: bool = False


# ---------------------------------------------------------------------------
# 规则引擎加载（默认从 config/rules.yaml 读取可编辑种子；缺失时退化为空引擎）
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_RULES_PATH = os.path.join(_PROJECT_ROOT, "config", "rules.yaml")
_rules_cache: Optional[RulesEngine] = None


def load_rules(path: Optional[str] = None) -> RulesEngine:
    """加载账户映射规则；path 为空时读取默认 config/rules.yaml。"""
    global _rules_cache
    target = path or _DEFAULT_RULES_PATH
    if target == _DEFAULT_RULES_PATH and _rules_cache is not None:
        return _rules_cache
    engine = RulesEngine.from_file(target) if os.path.exists(target) else RulesEngine({})
    if target == _DEFAULT_RULES_PATH:
        _rules_cache = engine
    return engine


def apply_image_rules(tx: ExtractedImageTransaction, rules: Optional[RulesEngine] = None) -> ResolvedImageTransaction:
    if rules is None:
        rules = load_rules()
    if _is_wechat_transaction(tx):
        return _apply_wechat_rules(tx, rules)
    return _apply_alipay_rules(tx, rules)


# ---------------------------------------------------------------------------
# 支付宝
# ---------------------------------------------------------------------------
def _apply_alipay_rules(tx: ExtractedImageTransaction, rules: RulesEngine) -> ResolvedImageTransaction:
    payee = tx.payee.strip()
    narration = tx.narration.strip()
    method = tx.payment_method.strip()
    category = tx.category.strip()
    receiver = tx.receiver_name.strip()

    if payee in ['**英', '**明', '**杰'] and narration == '经营码交易':
        payee = '碰一碰收款'
        narration = ''

    if payee == '深圳蜜蜂收卡科技有限公司' and narration == '转账':
        payee = '蜜蜂提现'
        narration = ''

    is_outflow = _is_outflow(tx)
    if _is_parent_support(payee, narration, receiver):
        bank_short = rules.resolve_bank_short(method)
        payee = f'支付宝{bank_short}立减' if bank_short else '支付宝立减'
        narration = ''

    funding_account = rules.resolve_payment_account(method, provider='alipay', is_outflow=is_outflow) \
        or 'Assets:CN:Alipay:Huiyou'
    search_text = ' '.join([payee, narration, category, tx.notes])
    # 长辈/亲情支持：payee 形如「支付宝{银行}立减」，对手方固定为亲情应付款（优先于分类规则）
    if payee.startswith('支付宝') and payee.endswith('立减'):
        counterparty_account = 'Liabilities:Payable:Parents'
    else:
        counterparty_account = rules.resolve_counterparty_account(search_text, provider='alipay', is_outflow=is_outflow)
        if not counterparty_account:
            counterparty_account = _alipay_counterparty_fallback(payee, is_outflow)

    payee = meal_payee_for_food(counterparty_account, tx.transaction_time) or payee
    base_offset, discount = _resolve_discount_amount(tx.amount, tx.order_amount, tx.discount_amount, method, is_outflow)

    postings_with_role = [
        ('funding', PostingSpec(funding_account, _funding_amount(tx.amount, is_outflow))),
    ]
    if discount > 0:
        discount_account = _resolve_discount_account(
            provider='alipay',
            counterparty_account=counterparty_account,
            method=method,
            category=category,
            narration=narration,
            notes=tx.notes,
            is_outflow=is_outflow,
        )
        postings_with_role.append(('discount', PostingSpec(discount_account, -discount)))
    postings_with_role.append(('counterparty', PostingSpec(counterparty_account, _counterparty_amount(base_offset, is_outflow))))
    postings = [item[1] for item in postings_with_role]
    funding_index = next(i for i, item in enumerate(postings_with_role) if item[0] == 'funding')
    counterparty_index = next(i for i, item in enumerate(postings_with_role) if item[0] == 'counterparty')

    return ResolvedImageTransaction(
        date=tx.date,
        payee=payee,
        narration=narration,
        currency=tx.currency,
        postings=postings,
        funding_account=funding_account,
        counterparty_account=counterparty_account,
        funding_index=funding_index,
        counterparty_index=counterparty_index,
        tx_id=tx.tx_id,
        category=category,
        method=method,
        transaction_time=tx.transaction_time,
        notes=tx.notes,
        confidence=tx.confidence,
        needs_review=tx.needs_review,
    )


def _is_parent_support(payee: str, narration: str, receiver: str) -> bool:
    return (
        (payee in ['便民服务', '见福便利店'] and narration == '收钱码收款')
        or payee == '碰一碰收款'
        or '榆社县建明商店' in payee
        or '榆社县建明商店' in receiver
    )


def _alipay_counterparty_fallback(payee: str, is_outflow: bool) -> str:
    """引擎未命中时的兜底：按收支方向归类到 Unknown。"""
    return 'Expenses:Unknown' if is_outflow else 'Income:Unknown'


# ---------------------------------------------------------------------------
# 微信
# ---------------------------------------------------------------------------
def _apply_wechat_rules(tx: ExtractedImageTransaction, rules: RulesEngine) -> ResolvedImageTransaction:
    payee = _normalize_wechat_payee(tx.payee.strip(), tx.receiver_name.strip(), tx.narration.strip())
    narration = _normalize_wechat_narration(tx.narration.strip(), tx.category.strip())
    method = tx.payment_method.strip()
    category = tx.category.strip()
    is_outflow = _is_outflow(tx)

    funding_account = _resolve_wechat_asset_account(method, category, narration, tx.notes, is_outflow, rules)
    search_text = ' '.join([payee, narration, category, method, tx.notes])
    counterparty_account = rules.resolve_counterparty_account(search_text, provider='wechat', is_outflow=is_outflow)
    if not counterparty_account:
        counterparty_account = _wechat_counterparty_fallback(is_outflow)

    payee = meal_payee_for_food(counterparty_account, tx.transaction_time) or payee
    base_offset, discount = _resolve_discount_amount(tx.amount, tx.order_amount, tx.discount_amount, method, is_outflow)

    postings_with_role = [
        ('funding', PostingSpec(funding_account, _funding_amount(tx.amount, is_outflow))),
    ]
    if discount > 0:
        discount_account = _resolve_discount_account(
            provider='wechat',
            counterparty_account=counterparty_account,
            method=method,
            category=category,
            narration=narration,
            notes=tx.notes,
            is_outflow=is_outflow,
        )
        postings_with_role.append(('discount', PostingSpec(discount_account, -discount)))
    postings_with_role.append(('counterparty', PostingSpec(counterparty_account, _counterparty_amount(base_offset, is_outflow))))
    postings = [item[1] for item in postings_with_role]
    funding_index = next(i for i, item in enumerate(postings_with_role) if item[0] == 'funding')
    counterparty_index = next(i for i, item in enumerate(postings_with_role) if item[0] == 'counterparty')

    return ResolvedImageTransaction(
        date=tx.date,
        payee=payee,
        narration=narration,
        currency=tx.currency,
        postings=postings,
        funding_account=funding_account,
        counterparty_account=counterparty_account,
        funding_index=funding_index,
        counterparty_index=counterparty_index,
        tx_id=tx.tx_id,
        category=category,
        method=method,
        transaction_time=tx.transaction_time,
        notes=tx.notes,
        confidence=tx.confidence,
        needs_review=tx.needs_review,
    )


def _wechat_counterparty_fallback(is_outflow: bool) -> str:
    return 'Expenses:Unknown' if is_outflow else 'Income:Unknown'


def _resolve_discount_amount(
    actual_amount: float,
    order_amount: Optional[float],
    extracted_discount: Optional[float],
    method: str,
    is_outflow: bool,
) -> tuple[float, float]:
    offset_amount = abs(actual_amount)
    base_offset = float(offset_amount)
    discount = round(abs(extracted_discount or 0.0), 2)

    if not is_outflow:
        return base_offset, 0.0

    if order_amount is not None and order_amount >= offset_amount:
        base_offset = float(order_amount)
        discount = round(max(base_offset - offset_amount, discount), 2)
        return base_offset, discount

    has_discount = any(keyword in method for keyword in ['立减', '天天减', '折扣券', '红包', '优惠'])
    if offset_amount > 0 and has_discount and not float(offset_amount).is_integer():
        ceil_amount = math.ceil(offset_amount)
        if ceil_amount % 10 in [7, 8, 9, 0] and ceil_amount > 50:
            base_offset = float(math.ceil(offset_amount / 10.0) * 10)
        else:
            base_offset = float(ceil_amount)
        discount = round(max(base_offset - offset_amount, discount), 2)

    return base_offset, discount


def meal_payee_for_food(counterparty_account: str, transaction_time: str) -> str:
    if counterparty_account != 'Expenses:Food':
        return ''

    hour = _extract_hour(transaction_time)
    if hour is None:
        return ''
    if hour < 11:
        return '早餐'
    if hour < 17:
        return '午饭'
    if hour < 22:
        return '晚饭'
    return '夜宵'


def _extract_hour(value: str) -> Optional[int]:
    if not value:
        return None

    text = str(value)
    match = re.search(r'(?:\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}[日号]?\s*)?([01]?\d|2[0-3])[:：时点]', text)
    if not match:
        return None
    return int(match.group(1))


def amount_is_expense(amount: float, expense_account: str) -> bool:
    return amount > 0 or expense_account.startswith('Expenses:')


def _is_wechat_transaction(tx: ExtractedImageTransaction) -> bool:
    text = ' '.join([
        tx.payee,
        tx.receiver_name,
        tx.narration,
        tx.payment_method,
        tx.category,
        tx.notes,
    ])
    return any(keyword in text for keyword in [
        '微信', '零钱', '零钱通', '微信转账', '扫码支付', '二维码收款',
        '财付通', '外卖回款', '已存入零钱', '已收钱', '立减金',
    ])


def _is_outflow(tx: ExtractedImageTransaction) -> bool:
    direction = tx.direction.strip()
    if direction:
        if any(keyword in direction for keyword in ['支出', '付款', '消费', '支付']):
            return True
        if any(keyword in direction for keyword in ['收入', '收款', '到账', '退款']):
            return False
    text = ' '.join([
        tx.payee,
        tx.receiver_name,
        tx.narration,
        tx.payment_method,
        tx.category,
        tx.notes,
    ])
    if any(keyword in text for keyword in ['回款', '收益入账', '退款', '已存入零钱', '已收钱', '到账', '红包']):
        return False
    if any(keyword in text for keyword in ['扫码支付', '付款', '消费', '收钱码收款', '商品说明']):
        return True
    if tx.amount < 0:
        return True
    if tx.amount > 0:
        return False
    return True


def _funding_amount(amount: float, is_outflow: bool) -> float:
    return -abs(amount) if is_outflow else abs(amount)


def _counterparty_amount(amount: float, is_outflow: bool) -> float:
    return abs(amount) if is_outflow else -abs(amount)


def _resolve_discount_account(
    provider: str,
    counterparty_account: str,
    method: str,
    category: str,
    narration: str,
    notes: str,
    is_outflow: bool,
) -> str:
    text = ' '.join([method, category, narration, notes])
    if provider == 'wechat' and '立减金' in text:
        return 'Assets:CN:WXLJJ'
    if is_outflow:
        if counterparty_account.startswith('Income:'):
            return 'Income:CN:Discount'
        return 'Expenses:CN:Discount'
    return 'Income:CN:Discount'


def _normalize_wechat_payee(payee: str, receiver_name: str, narration: str) -> str:
    result = payee or receiver_name
    if result.startswith('高物') and '转账' in narration:
        return '卖存款'
    return result


def _normalize_wechat_narration(narration: str, category: str) -> str:
    result = narration.replace('转账备注:', '').strip()
    if result in ['', '/']:
        return category if category not in ['', '/'] else ''
    return result.replace('转账备注:微信转账', '微信转账')


def _resolve_wechat_asset_account(
    method: str,
    category: str,
    narration: str,
    notes: str,
    is_outflow: bool,
    rules: RulesEngine,
) -> str:
    text = ' '.join([method, category, narration, notes])
    # 微信立减金（收到）单独计入资产
    if '立减金' in text and not is_outflow and any(keyword in text for keyword in ['获得', '入账', '奖励', '到账']):
        return 'Assets:CN:WXLJJ'
    return rules.resolve_payment_account(method, provider='wechat', is_outflow=is_outflow) \
        or 'Assets:CN:Wechat:Mathlife'
