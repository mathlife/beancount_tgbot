import asyncio
import os
import tempfile

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.rules_engine import RulesEngine
from src.bot.handlers import MessageHandlers


class _FakeConfig:
    allowed_user_id = 12345
    default_currency = "CNY"
    aliases = {}


SEED = {
    "payment_method_map": [
        {"match": "工商银行储蓄卡(3355)", "provider": "any", "account": "Assets:CN:DebitCard:ICBC:3355"},
    ],
    "counterparty_map": [
        {"match": "美团", "provider": "any", "account": "Expenses:Food", "priority": 50},
    ],
    "bank_short_names": [
        {"match": "工商银行", "short": "工行"},
    ],
    "payee_rename": [],
}


@pytest.fixture
def handler(tmp_path):
    h = MessageHandlers(MagicMock(), MagicMock(), _FakeConfig())
    p = os.path.join(str(tmp_path), "rules.yaml")
    h.rules = RulesEngine(rules=SEED, path=p)
    h.allowed_user_id = 12345
    return h


def _run(handler, update, args):
    ctx = MagicMock()
    ctx.args = args
    return asyncio.run(handler.rules_command(update, ctx))


def test_rules_list(handler):
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.reply_text = AsyncMock()
    _run(handler, update, [])
    out = update.message.reply_text.call_args[0][0]
    assert "当前账户映射规则" in out
    assert "工商银行储蓄卡(3355)" in out


def test_rules_add_and_persist(handler, tmp_path):
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.reply_text = AsyncMock()
    _run(handler, update, ["add", "counterparty", "星巴克", "Expenses:Food"])
    # 引擎已更新
    assert handler.rules.resolve_counterparty_account("星巴克", "any") == "Expenses:Food"
    # 已写盘
    reloaded = RulesEngine.from_file(os.path.join(str(tmp_path), "rules.yaml"))
    assert reloaded.resolve_counterparty_account("星巴克", "any") == "Expenses:Food"


def test_rules_del(handler):
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.reply_text = AsyncMock()
    _run(handler, update, ["add", "payment", "我的卡", "Assets:CN:DebitCard:MINE"])
    before = len(handler.rules.list_rules("payment_method_map")["payment_method_map"])
    _run(handler, update, ["del", "payment", str(before)])
    after = len(handler.rules.list_rules("payment_method_map")["payment_method_map"])
    assert after == before - 1


def test_rules_unauthorized(handler):
    update = MagicMock()
    update.effective_user.id = 99999  # 非授权用户
    update.message.reply_text = AsyncMock()
    _run(handler, update, [])
    update.message.reply_text.assert_not_called()
