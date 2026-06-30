import math
from dataclasses import dataclass
from datetime import date
import re
from typing import List, Optional


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


BANK_ACCOUNT_MAP = {
    '工商银行储蓄卡(3355)': 'Assets:CN:DebitCard:ICBC:3355',
    '浦发银行储蓄卡(1691)': 'Assets:CN:DebitCard:SPDB:1691',
    '光大银行储蓄卡(6340)': 'Assets:CN:DebitCard:CEB:6340',
    '中信银行储蓄卡(1709)': 'Assets:CN:DebitCard:CITIC:1709',
    '四川天府银行储蓄卡(5866)': 'Assets:CN:DebitCard:CGNB:5866',
    '华夏银行储蓄卡(2593)': 'Assets:CN:DebitCard:HXB:2593',
    '浙商银行储蓄卡(0907)': 'Assets:CN:DebitCard:CZBANK:0907',
    '招商银行储蓄卡(5666)': 'Assets:CN:DebitCard:CMB:5666',
    '中国银行储蓄卡(2174)': 'Assets:CN:DebitCard:BOC:2174',
    '平安银行储蓄卡(6197)': 'Assets:CN:DebitCard:PAB:6197',
    '建设银行储蓄卡(7610)': 'Assets:CN:DebitCard:CCB:7610',
    '农业银行储蓄卡(8979)': 'Assets:CN:DebitCard:ABC:8979',
    '网商银行储蓄卡(5518)': 'Assets:CN:DebitCard:ANTBANK:5518',
    '中信银行信用卡(9369)': 'Liabilities:CreditCard:UnionPay:CITIC',
    '工商银行信用卡(3965)': 'Liabilities:CreditCard:UnionPay:ICBC:3965',
    '建设银行信用卡(8686)': 'Liabilities:CreditCard:UnionPay:CCB',
    '邮储银行信用卡(1824)': 'Liabilities:CreditCard:AMEX:PSBC:1824',
}

BANK_SHORT_NAME_MAP = {
    '工商银行': '工行',
    '浦发银行': '浦发',
    '光大银行': '光大',
    '中信银行': '中信',
    '四川天府银行': '天府',
    '华夏银行': '华夏',
    '浙商银行': '浙商',
    '招商银行': '招商',
    '中国银行': '中行',
    '平安银行': '平安',
    '建设银行': '建行',
    '农业银行': '农行',
    '宁波银行': '宁波',
    '盛京银行': '盛京',
    '邮储银行': '邮储',
    '民生银行': '民生',
    '交通银行': '交行',
}


def apply_image_rules(tx: ExtractedImageTransaction) -> ResolvedImageTransaction:
    if _is_wechat_transaction(tx):
        return _apply_wechat_rules(tx)
    return _apply_alipay_rules(tx)


def _apply_alipay_rules(tx: ExtractedImageTransaction) -> ResolvedImageTransaction:
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

    if _is_parent_support(payee, narration, receiver):
        bank_short = _resolve_bank_short(method)
        payee = f'支付宝{bank_short}立减' if bank_short else '支付宝立减'
        narration = ''

    funding_account = _resolve_alipay_asset_account(method)
    counterparty_account = _resolve_alipay_counterparty_account(payee, narration, category, tx.amount)
    payee = meal_payee_for_food(counterparty_account, tx.transaction_time) or payee
    is_outflow = _is_outflow(tx)
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


def _resolve_bank_short(method: str) -> str:
    for full_name, short_name in BANK_SHORT_NAME_MAP.items():
        if full_name in method:
            return short_name
    if '花呗' in method:
        return '花呗'
    if '亲情卡' in method:
        return '亲情卡'
    return ''


def _resolve_alipay_asset_account(method: str) -> str:
    if '余额宝' in method:
        return 'Assets:CN:FinTech:YEB:Huiyou'
    if '花呗' in method:
        return 'Liabilities:Alipay:HB'
    if '亲情卡(常桂英' in method:
        return 'Liabilities:Payable:Parents'

    for key, account in BANK_ACCOUNT_MAP.items():
        if key in method:
            return account

    return 'Assets:CN:Alipay:Huiyou'


def _resolve_alipay_counterparty_account(payee: str, narration: str, category: str, amount: float) -> str:
    if '收益发放' in narration:
        return 'Income:PassiveIncome:Interest:YEB'
    if payee == '网商银行' and '余利宝' in narration:
        return 'Assets:CN:DebitCard:ANTBANK:5518'
    if payee == '杭州阿里妈妈淘联信息技术有限公司' or '碰一下支付现金奖励' in narration:
        return 'Income:CN:RedEnvelope'
    if '批量付款' in narration or '批量付款' in payee:
        return 'Assets:CN:ZeroSum'
    if payee == '华夏银行' and '提现' in narration:
        return 'Assets:CN:DebitCard:HXB:2593'
    if payee == '深圳市惠得宝科技有限公司' and '提款' in narration:
        return 'Assets:CN:ZeroSum'
    if payee == '蜜蜂提现':
        return 'Assets:CN:ZeroSum'
    if payee in ['鹏林(高鹏林)', 'seiten(*滨)']:
        return 'Expenses:Unknown'
    if payee in ['**君', '**伟', '*腾']:
        return 'Income:Unknown'
    if payee == '顺丰速运':
        return 'Expenses:Package-Delivery'
    if payee == '厦门地铁':
        return 'Expenses:Transport'
    if payee == '支付宝红包' and '口令红包' in narration:
        return 'Income:CN:RedEnvelope'
    if payee == '见福便利店' or payee == '碰一碰收款' or (payee.startswith('支付宝') and payee.endswith('立减')):
        return 'Liabilities:Payable:Parents'
    if any(text in payee for text in ['美团', '套餐店', '小吃店', '炖品', '不想走']) or '肯德基' in narration:
        return 'Expenses:Food'
    if '便利店' in payee or '便民服务' in payee:
        return 'Expenses:Groceries'
    if category == '日用百货':
        return 'Expenses:Groceries'
    if category == '餐饮美食':
        return 'Expenses:Food'
    if category == '交通出行':
        return 'Expenses:Transport'
    if category == '转账红包':
        return 'Income:CN:RedEnvelope' if amount > 0 else 'Assets:CN:ZeroSum'
    return 'Expenses:Unknown'


def _apply_wechat_rules(tx: ExtractedImageTransaction) -> ResolvedImageTransaction:
    payee = _normalize_wechat_payee(tx.payee.strip(), tx.receiver_name.strip(), tx.narration.strip())
    narration = _normalize_wechat_narration(tx.narration.strip(), tx.category.strip())
    method = tx.payment_method.strip()
    category = tx.category.strip()
    is_outflow = _is_outflow(tx)

    funding_account = _resolve_wechat_asset_account(method, category, narration, tx.notes, is_outflow)
    counterparty_account = _resolve_wechat_counterparty_account(
        payee=payee,
        narration=narration,
        category=category,
        method=method,
        notes=tx.notes,
        amount=tx.amount,
        is_outflow=is_outflow,
    )
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
) -> str:
    text = ' '.join([method, category, narration, notes])
    if '零钱通' in text:
        return 'Assets:CN:FinTech:LQT:Mathlife'
    if '立减金' in text and not is_outflow and any(keyword in text for keyword in ['获得', '入账', '奖励', '到账']):
        return 'Assets:CN:WXLJJ'
    return 'Assets:CN:Wechat:Mathlife'


def _resolve_wechat_counterparty_account(
    payee: str,
    narration: str,
    category: str,
    method: str,
    notes: str,
    amount: float,
    is_outflow: bool,
) -> str:
    text = ' '.join([payee, narration, category, method, notes])

    if '零钱通收益' in text or '收益入账' in text:
        return 'Income:PassiveIncome:Interest:LQT'
    if any(keyword in text for keyword in ['提现', '回款', '提款', '零钱充值']):
        return 'Assets:CN:ZeroSum'
    if '批量付款' in text or '经营码交易' in text:
        return 'Assets:CN:ZeroSum'
    if payee == '米夏' and '转账' in narration:
        return 'Assets:CN:ZeroSum'
    if payee == '卖存款':
        return 'Income:SideProject'
    if '外卖女王🌹🌹🌹🌹🌹🌹' in payee or '外卖回款' in narration:
        return 'Assets:CN:ZeroSum'
    if '红包' in text or '奖励' in text:
        return 'Income:CN:RedEnvelope' if not is_outflow else 'Expenses:Unknown'
    if '退款' in text:
        return 'Income:CN:Rebate'
    if any(keyword in text for keyword in ['小村口', '秋佳', '卤味', '快餐', '佳乐多', '餐饮', '美食', '外卖']):
        return 'Expenses:Food'
    if any(keyword in narration for keyword in ['微信转账', '转账']):
        return 'Expenses:Unknown' if is_outflow else 'Income:Unknown'
    if '扫码支付' in narration or '扫码支付' in category:
        return 'Expenses:Unknown' if is_outflow else 'Income:Unknown'
    if '立减金' in text and not is_outflow:
        return 'Income:CN:WXLJJ'
    return 'Expenses:Unknown' if is_outflow else 'Income:Unknown'
