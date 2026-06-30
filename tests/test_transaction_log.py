import datetime

from src.core.transaction_log import TransactionLog


def test_get_recent_applies_status_updates(tmp_path):
    tx_log = TransactionLog(str(tmp_path))

    tx_id_1 = tx_log.log_transaction(
        {
            "date": datetime.date(2026, 6, 30),
            "payee": "商户A",
            "narration": "午饭",
            "amount": 32.0,
            "currency": "CNY",
            "asset": "Assets:Cash",
            "expense": "Expenses:Food",
        }
    )
    tx_id_2 = tx_log.log_transaction(
        {
            "date": datetime.date(2026, 6, 30),
            "payee": "商户B",
            "narration": "咖啡",
            "amount": 18.0,
            "currency": "CNY",
            "asset": "Assets:Cash",
            "expense": "Expenses:Drink",
        }
    )

    tx_log.update_status(tx_id_1, "confirmed")
    tx_log.update_status(tx_id_2, "cancelled")

    recent_confirmed = tx_log.get_recent(10, status="confirmed")

    assert len(recent_confirmed) == 1
    assert recent_confirmed[0].tx_id == tx_id_1
    assert recent_confirmed[0].status == "confirmed"


def test_get_today_summary_uses_final_confirmed_status(tmp_path):
    tx_log = TransactionLog(str(tmp_path))
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    today_tx_id = tx_log.log_transaction(
        {
            "date": today,
            "payee": "商户A",
            "narration": "晚饭",
            "amount": 45.5,
            "currency": "CNY",
            "asset": "Assets:Cash",
            "expense": "Expenses:Food",
        }
    )
    old_tx_id = tx_log.log_transaction(
        {
            "date": yesterday,
            "payee": "商户B",
            "narration": "早餐",
            "amount": 12.0,
            "currency": "CNY",
            "asset": "Assets:Cash",
            "expense": "Expenses:Food",
        }
    )

    tx_log.update_status(today_tx_id, "confirmed")
    tx_log.update_status(old_tx_id, "confirmed")

    summary = tx_log.get_today_summary()

    assert summary["date"] == today.isoformat()
    assert summary["count"] == 1
    assert summary["total_amount"] == 45.5
    assert summary["transactions"][0].tx_id == today_tx_id


def test_get_by_id_preserves_postings_and_metadata(tmp_path):
    tx_log = TransactionLog(str(tmp_path))

    tx_id = tx_log.log_transaction(
        {
            "date": datetime.date(2026, 6, 30),
            "payee": "支付宝花呗立减",
            "narration": "",
            "amount": -19.7,
            "currency": "CNY",
            "asset": "Liabilities:Alipay:HB",
            "expense": "Liabilities:Payable:Parents",
            "metadata": {"tx_id": "abc123", "category": "日用百货"},
            "postings": [
                {"account": "Liabilities:Alipay:HB", "amount": -19.7, "currency": "CNY"},
                {"account": "Expenses:CN:Discount", "amount": -0.3, "currency": "CNY"},
                {"account": "Liabilities:Payable:Parents", "amount": 20.0, "currency": "CNY"},
            ],
        }
    )
    tx_log.update_status(tx_id, "confirmed")

    record = tx_log.get_by_id(tx_id)

    assert record is not None
    assert record.status == "confirmed"
    assert record.metadata == {"tx_id": "abc123", "category": "日用百货"}
    assert record.postings[0]["account"] == "Liabilities:Alipay:HB"
    assert record.postings[2]["amount"] == 20.0
