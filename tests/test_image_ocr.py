from src.utils.image_ocr import parse_ocr_lines


def test_parse_alipay_ocr_lines():
    raw = parse_ocr_lines(
        [
            "账单详情",
            "便民服务",
            "-19.70",
            "交易成功",
            "订单金额",
            "20.00",
            "到店支付红包",
            "-0.30",
            "支付时间",
            "2026-06-30 07:12:17",
            "付款方式",
            "花呗",
            "商品说明",
            "收钱码收款",
            "收款方全称",
            "**英(个人)",
            "订单号",
            "2026063022001473841456865125",
            "账单分类",
            "日用百货",
        ],
        default_currency="CNY",
    )

    assert raw["payee"] == "便民服务"
    assert raw["receiver_name"] == "**英(个人)"
    assert raw["narration"] == "收钱码收款"
    assert raw["actual_amount"] == -19.70
    assert raw["order_amount"] == 20.00
    assert raw["discount_amount"] == 0.30
    assert raw["payment_method"] == "花呗"
    assert raw["category"] == "日用百货"
    assert raw["direction"] == "支出"
    assert raw["transaction_time"] == "2026-06-30 07:12:17"


def test_parse_wechat_ocr_lines():
    raw = parse_ocr_lines(
        [
            "微信支付",
            "账单详情",
            "外卖女王🌹🌹🌹🌹🌹🌹",
            "+81.08",
            "已存入零钱",
            "交易类型",
            "转账",
            "转账说明",
            "外卖回款",
            "入账方式",
            "零钱",
            "交易时间",
            "2026-06-20 12:06:00",
            "微信单号",
            "1000000000000000001",
        ],
        default_currency="CNY",
    )

    assert raw["payee"] == "外卖女王🌹🌹🌹🌹🌹🌹"
    assert raw["narration"] == "外卖回款"
    assert raw["actual_amount"] == 81.08
    assert raw["payment_method"] == "零钱"
    assert raw["category"] == "转账"
    assert raw["direction"] == "收入"
    assert raw["transaction_time"] == "2026-06-20 12:06:00"
    assert raw["needs_review"] is True
