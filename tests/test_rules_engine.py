import os
import tempfile

import pytest

from src.core.rules_engine import RulesEngine
from src.core.image_rules import load_rules
import datetime

from src.core.image_rules import ExtractedImageTransaction, apply_image_rules


SEED = {
    "payment_method_map": [
        {"match": "工商银行储蓄卡(3355)", "provider": "any", "account": "Assets:CN:DebitCard:ICBC:3355"},
        {"match": "花呗", "provider": "alipay", "account": "Liabilities:Alipay:HB", "priority": 10},
        {"match": "零钱通", "provider": "wechat", "account": "Assets:CN:FinTech:LQT:Mathlife", "priority": 10},
    ],
    "counterparty_map": [
        {"match": "美团", "provider": "any", "account": "Expenses:Food", "priority": 50},
        {"match": "转账红包", "provider": "alipay", "account_outflow": "Assets:CN:ZeroSum",
         "account_inflow": "Income:CN:RedEnvelope", "priority": 100},
        {"match": "红包", "provider": "wechat", "account_outflow": "Expenses:Unknown",
         "account_inflow": "Income:CN:RedEnvelope", "priority": 90},
    ],
    "bank_short_names": [
        {"match": "工商银行", "short": "工行"},
    ],
    "payee_rename": [
        {"match": "支付宝", "rename": "支付宝{bank}立减", "provider": "alipay"},
    ],
}


@pytest.fixture
def engine():
    return RulesEngine(rules=SEED)


def test_payment_resolution(engine):
    assert engine.resolve_payment_account("工商银行储蓄卡(3355) 支付", "alipay") == "Assets:CN:DebitCard:ICBC:3355"
    # provider 过滤：花呗只匹配 alipay，不匹配 wechat
    assert engine.resolve_payment_account("花呗", "alipay") == "Liabilities:Alipay:HB"
    assert engine.resolve_payment_account("花呗", "wechat") == ""
    # 零钱通仅 wechat
    assert engine.resolve_payment_account("零钱通", "wechat") == "Assets:CN:FinTech:LQT:Mathlife"


def test_counterparty_direction(engine):
    # 美团 -> Expenses:Food（不区分方向）
    assert engine.resolve_counterparty_account("美团外卖", "any") == "Expenses:Food"
    # 转账红包：支出 -> ZeroSum，收入 -> RedEnvelope
    assert engine.resolve_counterparty_account("转账红包 123", "alipay", is_outflow=True) == "Assets:CN:ZeroSum"
    assert engine.resolve_counterparty_account("转账红包 123", "alipay", is_outflow=False) == "Income:CN:RedEnvelope"
    # 红包方向（wechat）
    assert engine.resolve_counterparty_account("收到红包", "wechat", is_outflow=False) == "Income:CN:RedEnvelope"
    assert engine.resolve_counterparty_account("发出红包", "wechat", is_outflow=True) == "Expenses:Unknown"


def test_bank_short(engine):
    assert engine.resolve_bank_short("工商银行储蓄卡(3355)") == "工行"


def test_payee_rename_template(engine):
    assert engine.apply_payee_rename("支付宝", "工商银行储蓄卡(3355)", provider="alipay") == "支付宝工行立减"


def test_priority_ordering(engine):
    # 转账红包(p100) 优先于 美团(p50)
    assert engine.resolve_counterparty_account("转账红包 美团", "alipay", is_outflow=True) == "Assets:CN:ZeroSum"


def test_add_and_list(engine):
    new_id = engine.add_rule("counterparty_map", "星巴克", "Expenses:Food", provider="any")
    assert new_id >= 1
    items = engine.list_rules("counterparty_map")["counterparty_map"]
    matches = [e for _, e in items if e["match"] == "星巴克"]
    assert matches and matches[0]["account"] == "Expenses:Food"


def test_del_rule(engine):
    before = len(engine.list_rules("counterparty_map")["counterparty_map"])
    ok = engine.del_rule("counterparty_map", before)  # 删除最后一条（美团? 实际删除指定序号）
    assert ok
    after = len(engine.list_rules("counterparty_map")["counterparty_map"])
    assert after == before - 1


def test_save_and_reload(tmp_path):
    p = os.path.join(str(tmp_path), "rules.yaml")
    eng = RulesEngine(rules=SEED, path=p)
    eng.save()
    reloaded = RulesEngine.from_file(p)
    assert reloaded.resolve_payment_account("花呗", "alipay") == "Liabilities:Alipay:HB"
    assert reloaded.resolve_counterparty_account("美团", "any") == "Expenses:Food"


def test_load_real_seed_file():
    eng = load_rules()
    # 真实种子文件应至少包含各银行的资金账户映射
    assert eng.resolve_payment_account("中信银行储蓄卡(1709)", "alipay") == "Assets:CN:DebitCard:CITIC:1709"
    # 分类映射
    assert eng.resolve_counterparty_account("餐饮美食", "any") == "Expenses:Food"
    assert eng.resolve_counterparty_account("交通出行", "any") == "Expenses:Transport"


def _make_tx(payee, narration, category, method, amount, direction):
    return ExtractedImageTransaction(
        date=datetime.date(2026, 6, 30),
        payee=payee, receiver_name=payee, narration=narration,
        amount=amount, order_amount=None, discount_amount=None,
        currency="CNY", payment_method=method, category=category,
        tx_id="x", direction=direction,
    )


def test_custom_rule_overrides_seed():
    # 从文件新建独立引擎，避免污染 load_rules() 的全局缓存
    eng = RulesEngine.from_file(load_rules().path)
    # 新增一条更高优先级规则：某商户固定映射到自己的科目
    eng.add_rule("counterparty_map", "我的私人商户", "Expenses:MySpecial", provider="any", priority=200)
    resolved = apply_image_rules(
        _make_tx("我的私人商户", "", "日用百货", "花呗", -12.0, "支出"), rules=eng
    )
    assert resolved.counterparty_account == "Expenses:MySpecial"
