import datetime
import pytest

from src.core.image_rules import ExtractedImageTransaction, apply_image_rules, meal_payee_for_food


def test_alipay_bill_with_huabei_and_discount():
    tx = ExtractedImageTransaction(
        date=datetime.date(2026, 6, 30),
        payee="便民服务",
        receiver_name="**英(个人)",
        narration="收钱码收款",
        amount=19.70,
        order_amount=20.00,
        discount_amount=0.30,
        currency="CNY",
        payment_method="花呗",
        category="日用百货",
        tx_id="2026063022001473841456865125",
        direction="支出",
    )

    resolved = apply_image_rules(tx)

    assert resolved.payee == "支付宝花呗立减"
    assert resolved.narration == ""
    assert resolved.funding_account == "Liabilities:Alipay:HB"
    assert resolved.counterparty_account == "Liabilities:Payable:Parents"
    assert resolved.postings[0].account == "Liabilities:Alipay:HB"
    assert resolved.postings[0].amount == -19.70
    assert resolved.postings[1].account == "Expenses:CN:Discount"
    assert resolved.postings[1].amount == -0.30
    assert resolved.postings[2].account == "Liabilities:Payable:Parents"
    assert resolved.postings[2].amount == 20.00


def test_wechat_transfer_income():
    tx = ExtractedImageTransaction(
        date=datetime.date(2026, 6, 16),
        payee="小丸子 (小丸子)",
        receiver_name="小丸子 (小丸子)",
        narration="微信转账",
        amount=217.00,
        order_amount=None,
        discount_amount=None,
        currency="CNY",
        payment_method="零钱",
        category="微信转账",
        tx_id="wx-income-1",
        direction="收入",
    )

    resolved = apply_image_rules(tx)

    assert resolved.funding_account == "Assets:CN:Wechat:Mathlife"
    assert resolved.counterparty_account == "Income:Unknown"
    assert resolved.postings[0].account == "Assets:CN:Wechat:Mathlife"
    assert resolved.postings[0].amount == 217.00
    assert resolved.postings[1].account == "Income:Unknown"
    assert resolved.postings[1].amount == -217.00


def test_wechat_transfer_expense():
    tx = ExtractedImageTransaction(
        date=datetime.date(2026, 6, 16),
        payee="徐汇小霸王 🐾🐾 (徐汇小霸王 🐾🐾)",
        receiver_name="徐汇小霸王 🐾🐾 (徐汇小霸王 🐾🐾)",
        narration="微信转账",
        amount=-217.00,
        order_amount=None,
        discount_amount=None,
        currency="CNY",
        payment_method="零钱",
        category="微信转账",
        tx_id="wx-expense-1",
        direction="支出",
    )

    resolved = apply_image_rules(tx)

    assert resolved.funding_account == "Assets:CN:Wechat:Mathlife"
    assert resolved.counterparty_account == "Expenses:Unknown"
    assert resolved.postings[0].account == "Assets:CN:Wechat:Mathlife"
    assert resolved.postings[0].amount == -217.00
    assert resolved.postings[1].account == "Expenses:Unknown"
    assert resolved.postings[1].amount == 217.00


def test_wechat_qr_payment():
    tx = ExtractedImageTransaction(
        date=datetime.date(2026, 6, 19),
        payee="榆社县建明商店",
        receiver_name="榆社县建明商店",
        narration="榆社县建明商店 - 扫码支付",
        amount=-499.00,
        order_amount=None,
        discount_amount=None,
        currency="CNY",
        payment_method="零钱",
        category="扫码支付",
        tx_id="wx-expense-2",
        direction="支出",
    )

    resolved = apply_image_rules(tx)

    assert resolved.counterparty_account == "Expenses:Unknown"
    assert resolved.postings[0].account == "Assets:CN:Wechat:Mathlife"
    assert resolved.postings[0].amount == -499.00
    assert resolved.postings[1].account == "Expenses:Unknown"
    assert resolved.postings[1].amount == 499.00


def test_wechat_takeout_settlement():
    tx = ExtractedImageTransaction(
        date=datetime.date(2026, 6, 20),
        payee="外卖女王🌹🌹🌹🌹🌹🌹",
        receiver_name="外卖女王🌹🌹🌹🌹🌹🌹",
        narration="外卖回款",
        amount=81.08,
        order_amount=None,
        discount_amount=None,
        currency="CNY",
        payment_method="零钱",
        category="转账",
        tx_id="wx-income-2",
        direction="收入",
    )

    resolved = apply_image_rules(tx)

    assert resolved.counterparty_account == "Assets:CN:ZeroSum"
    assert resolved.postings[0].account == "Assets:CN:Wechat:Mathlife"
    assert resolved.postings[0].amount == 81.08
    assert resolved.postings[1].account == "Assets:CN:ZeroSum"
    assert resolved.postings[1].amount == -81.08


def test_food_payee_uses_meal_name_from_transaction_time():
    tx = ExtractedImageTransaction(
        date=datetime.date(2026, 6, 30),
        payee="厦门市思明区秋佳小吃店",
        receiver_name="厦门市思明区秋佳小吃店",
        narration="扫码支付",
        amount=-19.00,
        order_amount=None,
        discount_amount=None,
        currency="CNY",
        payment_method="零钱",
        category="扫码支付",
        tx_id="wx-food-1",
        direction="支出",
        transaction_time="2026-06-30 12:06:00",
    )

    resolved = apply_image_rules(tx)

    assert resolved.payee == "午饭"
    assert resolved.counterparty_account == "Expenses:Food"
    assert resolved.postings[0].account == "Assets:CN:Wechat:Mathlife"
    assert resolved.postings[1].account == "Expenses:Food"


@pytest.mark.parametrize(
    ("transaction_time", "expected"),
    [
        ("2026-06-30 10:59:00", "早餐"),
        ("2026-06-30 11:00:00", "午饭"),
        ("2026-06-30 16:59:00", "午饭"),
        ("2026-06-30 17:00:00", "晚饭"),
        ("2026-06-30 21:59:00", "晚饭"),
        ("2026-06-30 22:00:00", "夜宵"),
        ("2026-06-30 04:30:00", "早餐"),
    ],
)
def test_food_meal_boundaries(transaction_time, expected):
    assert meal_payee_for_food("Expenses:Food", transaction_time) == expected
