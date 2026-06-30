import os
import re
import tempfile
from typing import Iterable, Optional


TITLE_WORDS = {
    '账单详情', '支付详情', '微信支付', '支付宝', '微信', '账单明细',
    '交易成功', '支付成功', '收款成功', '已收钱', '已存入零钱', '退款成功',
}

AMOUNT_PATTERN = re.compile(r'(?P<sign>[+-])?\s*[¥￥]?\s*(?P<amount>\d+(?:\.\d{1,2})?)')
DATE_PATTERN = re.compile(r'(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})')


class OCRImageExtractor:
    def __init__(self):
        self._engine = None

    def extract_transaction(self, image_bytes: bytes, mime_type: str, default_currency: str, caption: str = "") -> dict:
        engine = self._get_engine()
        suffix = _mime_to_suffix(mime_type)
        file_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(image_bytes)
                file_path = handle.name

            result = engine(file_path)
            lines = _extract_lines_from_result(result)
            if not lines:
                raise RuntimeError("OCR 未识别出可用文本")

            return parse_ocr_lines(lines, default_currency=default_currency, caption=caption)
        finally:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)

    def _get_engine(self):
        if self._engine is not None:
            return self._engine

        try:
            from rapidocr import RapidOCR
        except Exception as exc:
            raise RuntimeError(f"OCR 依赖未安装: {exc}") from exc

        self._engine = RapidOCR()
        return self._engine


def parse_ocr_lines(lines: Iterable[str], default_currency: str, caption: str = "") -> dict:
    normalized_lines = [str(line).strip() for line in lines if str(line).strip()]
    provider = _detect_provider(normalized_lines, caption)
    amount_text, amount_index = _find_summary_amount(normalized_lines)
    if amount_text is None:
        raise RuntimeError("OCR 未找到交易金额")

    payee = _find_header_payee(normalized_lines, amount_index)
    if not payee:
        payee = _find_labeled_value(normalized_lines, ['商户名称', '商户', '收款方全称', '收款方', '对方'])
    receiver_name = _find_labeled_value(normalized_lines, ['收款方全称', '收款方', '对方']) or payee
    category = _find_labeled_value(normalized_lines, ['账单分类', '交易类型']) or ''
    narration = _find_labeled_value(normalized_lines, ['商品说明', '商品', '转账说明', '备注'])
    payment_method = _find_labeled_value(normalized_lines, ['付款方式', '支付方式', '收款方式', '入账方式']) or ''
    tx_id = _find_labeled_value(normalized_lines, ['订单号', '交易单号', '微信单号', '商户单号']) or ''
    date_text = _find_labeled_value(normalized_lines, ['支付时间', '交易时间', '入账时间']) or ''
    order_amount = _find_labeled_amount(normalized_lines, ['订单金额', '商品金额', '原价'])
    discount_amount = _sum_labeled_amounts(
        normalized_lines,
        ['立减优惠', '微信立减金', '立减金', '立减', '红包抵扣', '优惠', '折扣', '优惠券', '到店支付红包'],
    )
    direction = _infer_direction(amount_text, category, narration, payment_method, normalized_lines)

    if not narration:
        if provider == 'wechat' and category:
            narration = category
        elif provider == 'alipay':
            narration = _find_labeled_value(normalized_lines, ['商品']) or ''

    notes = 'OCR fallback'
    if provider:
        notes = f'OCR fallback ({provider})'

    return {
        'date': _normalize_date(date_text),
        'transaction_time': date_text,
        'payee': payee or '',
        'receiver_name': receiver_name or '',
        'narration': narration or '',
        'order_amount': order_amount,
        'actual_amount': _amount_to_number(amount_text),
        'discount_amount': discount_amount,
        'currency': default_currency,
        'payment_method': payment_method,
        'category': category,
        'tx_id': tx_id,
        'direction': direction,
        'notes': notes,
        'confidence': 0.55,
        'needs_review': True,
    }


def _extract_lines_from_result(result) -> list[str]:
    if hasattr(result, 'txts'):
        return [str(text).strip() for text in result.txts if str(text).strip()]

    if isinstance(result, tuple) and result:
        return _extract_lines_from_result(result[0])

    if isinstance(result, list):
        lines = []
        for item in result:
            if isinstance(item, str):
                lines.append(item.strip())
                continue
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                lines.append(str(item[1]).strip())
        return [line for line in lines if line]

    return []


def _mime_to_suffix(mime_type: str) -> str:
    if mime_type == 'image/png':
        return '.png'
    if mime_type == 'image/webp':
        return '.webp'
    return '.jpg'


def _detect_provider(lines: list[str], caption: str) -> str:
    text = ' '.join(lines + [caption])
    if any(keyword in text for keyword in ['支付宝', '花呗', '余额宝', '商品说明', '收款方全称', '账单分类']):
        return 'alipay'
    if any(keyword in text for keyword in ['微信', '零钱', '零钱通', '微信支付', '微信转账', '扫码支付', '立减金', '已存入零钱']):
        return 'wechat'
    return ''


def _find_summary_amount(lines: list[str]) -> tuple[Optional[str], int]:
    for index, line in enumerate(lines[:16]):
        compact = _compact(line)
        if any(keyword in compact for keyword in ['支付时间', '交易时间', '订单金额', '订单号', '商户单号', '微信单号']):
            continue

        if compact.startswith('-') or compact.startswith('+'):
            value = _extract_amount_text(line)
            if value is not None:
                return value, index

        if re.fullmatch(r'[¥￥]?[+-]?\d+(?:\.\d{1,2})?', compact):
            value = _extract_amount_text(line)
            if value is not None:
                return value, index

    for index, line in enumerate(lines):
        value = _extract_amount_text(line)
        if value is None:
            continue
        compact = _compact(line)
        if any(keyword in compact for keyword in ['订单金额', '优惠', '立减', '红包', '支付时间', '交易时间']):
            continue
        return value, index

    return None, -1


def _find_header_payee(lines: list[str], amount_index: int) -> str:
    search_end = amount_index if amount_index > 0 else min(8, len(lines))
    for line in reversed(lines[:search_end]):
        compact = _compact(line)
        if not compact:
            continue
        if compact in TITLE_WORDS:
            continue
        if _extract_amount_text(line) is not None:
            continue
        if DATE_PATTERN.search(compact):
            continue
        return line.strip()
    return ''


def _find_labeled_value(lines: list[str], labels: list[str]) -> str:
    for index, line in enumerate(lines):
        stripped = line.strip()
        compact = _compact(stripped)
        for label in labels:
            if compact == label:
                next_value = _next_value_line(lines, index)
                if next_value:
                    return _clean_value(next_value)
            if compact.startswith(label):
                suffix_compact = compact[len(label):]
                if suffix_compact and not suffix_compact.startswith((':', '：')) and suffix_compact[0].isalnum():
                    continue
                raw_value = stripped[len(label):].strip(' :：\t')
                if raw_value:
                    return _clean_value(raw_value)
                next_value = _next_value_line(lines, index)
                if next_value:
                    return _clean_value(next_value)
    return ''


def _find_labeled_amount(lines: list[str], labels: list[str]) -> Optional[float]:
    for index, line in enumerate(lines):
        compact = _compact(line)
        for label in labels:
            if compact == label:
                next_value = _next_value_line(lines, index)
                value = _amount_to_number(next_value)
                if value is not None:
                    return abs(value)
            if compact.startswith(label):
                value = _amount_to_number(line[len(label):])
                if value is not None:
                    return abs(value)
    return None


def _sum_labeled_amounts(lines: list[str], labels: list[str]) -> Optional[float]:
    total = 0.0
    matched = False
    for index, line in enumerate(lines):
        compact = _compact(line)
        for label in labels:
            if compact == label:
                next_value = _next_value_line(lines, index)
                value = _amount_to_number(next_value)
                if value is not None:
                    total += abs(value)
                    matched = True
            elif compact.startswith(label):
                value = _amount_to_number(line[len(label):])
                if value is not None:
                    total += abs(value)
                    matched = True
    return round(total, 2) if matched else None


def _next_value_line(lines: list[str], index: int) -> str:
    for candidate in lines[index + 1:index + 4]:
        compact = _compact(candidate)
        if compact and compact not in TITLE_WORDS:
            return candidate.strip()
    return ''


def _extract_amount_text(text: str) -> Optional[str]:
    match = AMOUNT_PATTERN.search(text.replace(',', ''))
    if not match:
        return None
    sign = match.group('sign') or ''
    amount = match.group('amount')
    return f'{sign}{amount}'


def _amount_to_number(text: Optional[str]) -> Optional[float]:
    if text in (None, ''):
        return None
    match = AMOUNT_PATTERN.search(str(text).replace(',', ''))
    if not match:
        return None
    value = float(match.group('amount'))
    if match.group('sign') == '-':
        return -value
    return value


def _normalize_date(text: str) -> str:
    if not text:
        return ''
    match = DATE_PATTERN.search(_compact(text))
    if not match:
        return text.strip()
    year, month, day = match.groups()
    return f'{int(year):04d}-{int(month):02d}-{int(day):02d}'


def _infer_direction(amount_text: str, category: str, narration: str, payment_method: str, lines: list[str]) -> str:
    if amount_text.startswith('-'):
        return '支出'
    if amount_text.startswith('+'):
        return '收入'

    text = ' '.join(lines + [category, narration, payment_method])
    if any(keyword in text for keyword in ['已存入零钱', '已收钱', '收款成功', '到账', '退款成功', '退款']):
        return '收入'
    if any(keyword in text for keyword in ['支付成功', '付款方式', '扫码支付', '消费', '付款成功']):
        return '支出'
    return ''


def _clean_value(value: str) -> str:
    return value.strip().strip('>›').strip()


def _compact(text: str) -> str:
    return re.sub(r'\s+', '', text)
