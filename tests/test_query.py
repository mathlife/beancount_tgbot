"""
自然语言查询单元测试（不依赖 Telegram / 网络 / bean-query CLI）。

直接用 beancount 解析一小段文本得到 entries，验证：
- 时间范围解析
- 纯 Python 执行器（合计 / 分类 / 明细 / 趋势 / 笔数 / 余额）
- 启发式意图解析（无 LLM 回退）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from beancount import loader as bloader  # noqa: E402
from src.core.query import (  # noqa: E402
    LedgerQuery,
    resolve_time_range,
    range_label,
    parse_intent_heuristic,
)
from datetime import date  # noqa: E402


BEAN = """
2026-01-05 * "麦当劳" "早饭"
  Expenses:Food     12.00 CNY
  Assets:CN:Cash   -12.00 CNY

2026-01-20 * "滴滴" "打车"
  Expenses:Transport     15.50 CNY
  Assets:CN:DebitCard:CITIC:1709   -15.50 CNY

2026-02-03 * "全家" "晚饭"
  Expenses:Food     38.00 CNY
  Assets:CN:DebitCard:CITIC:1709   -38.00 CNY

2026-02-10 * "工资" "月薪"
  Income:CN:Salary   -8000.00 CNY
  Assets:CN:DebitCard:CITIC:1709    8000.00 CNY
"""


class TestQuery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        entries, _errors, _opts = bloader.load_string(BEAN)
        cls.entries = entries
        cls.lq = LedgerQuery(entries=entries)

    def test_time_range_this_month(self):
        s, e = resolve_time_range("this_month", today=date(2026, 6, 15))
        self.assertEqual((s, e), (date(2026, 6, 1), date(2026, 6, 30)))

    def test_time_range_year(self):
        s, e = resolve_time_range("2026")
        self.assertEqual((s, e), (date(2026, 1, 1), date(2026, 12, 31)))

    def test_time_range_month(self):
        s, e = resolve_time_range("2026-02")
        self.assertEqual((s, e), (date(2026, 2, 1), date(2026, 2, 28)))

    def test_time_range_all(self):
        self.assertEqual(resolve_time_range("all"), (None, None))

    def test_range_label(self):
        self.assertEqual(range_label(None, None), "全部")

    def test_total_all(self):
        out = self.lq.run_intent({"metric": "total", "time_range": "all"}, default_currency="CNY")
        self.assertIn("支出合计", out)
        self.assertIn("65.50", out)  # 12 + 15.5 + 38

    def test_total_food(self):
        out = self.lq.run_intent(
            {"metric": "total", "time_range": "all", "account": "Expenses:Food"},
            default_currency="CNY",
        )
        self.assertIn("50.00", out)  # 12 + 38

    def test_by_category_feb(self):
        out = self.lq.run_intent(
            {"metric": "by_category", "time_range": "2026-02"}, default_currency="CNY"
        )
        self.assertIn("Expenses:Food", out)
        self.assertIn("38.00", out)

    def test_trend(self):
        out = self.lq.run_intent(
            {"metric": "trend", "time_range": "all"}, default_currency="CNY"
        )
        self.assertIn("2026-01", out)
        self.assertIn("2026-02", out)

    def test_count(self):
        out = self.lq.run_intent(
            {"metric": "count", "time_range": "all"}, default_currency="CNY"
        )
        self.assertIn("4 笔", out)

    def test_balance_account(self):
        out = self.lq.run_intent(
            {"metric": "balance", "account": "Assets:CN:DebitCard:CITIC:1709"},
            default_currency="CNY",
        )
        # 8000 - 15.5 - 38 = 7946.5
        self.assertIn("7,946.50", out)

    def test_balance_no_account(self):
        out = self.lq.run_intent({"metric": "balance"}, default_currency="CNY")
        self.assertIn("请指定", out)

    def test_heuristic_total_this_month(self):
        intent = parse_intent_heuristic("这个月吃饭花了多少")
        self.assertEqual(intent["metric"], "total")
        self.assertEqual(intent["time_range"], "this_month")

    def test_heuristic_category(self):
        intent = parse_intent_heuristic("上月各类支出占比")
        self.assertEqual(intent["metric"], "by_category")
        self.assertEqual(intent["time_range"], "last_month")

    def test_heuristic_account_alias(self):
        aliases = {"饭": "Expenses:Food", "打车": "Expenses:Transport"}
        intent = parse_intent_heuristic("这个月饭花了多少", aliases=aliases)
        self.assertEqual(intent["account"], "Expenses:Food")


if __name__ == "__main__":
    unittest.main(verbosity=2)
