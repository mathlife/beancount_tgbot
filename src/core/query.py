"""
自然语言查询：纯 Python 账本查询（不依赖 bean-query CLI / beancount 查询引擎）

设计要点（对应项目约束）：
- 机器人是轻量化记账入口，宿主机不一定装有 Beancount 工具链，因此**不调用 `bean-query` 命令**，
  也不依赖 `beancount.query` 引擎，而是直接遍历 `BeanLoader` 已加载到内存的 `entries`
  （Beancount 解析后的指令列表），用纯 Python 做统计/分组。
- 自然语言 → 结构化查询意图（intent）：优先用 LLM（OpenAI-compatible / Gemini）解析，
  失败或无密钥时回退到本地启发式规则，保证离线可用。
- 不引入数据库；账本权威来源始终是文本文件。
"""
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple, Any
import re

from beancount.core.data import Transaction

# 账户大类前缀
EXPENSES = "Expenses:"
INCOME = "Income:"
ASSETS = "Assets:"
LIABILITIES = "Liabilities:"


# --------------------------------------------------------------------------- #
# 时间范围解析
# --------------------------------------------------------------------------- #
def resolve_time_range(name: Optional[str], today: Optional[date] = None) -> Tuple[Optional[date], Optional[date]]:
    """将时间范围描述解析为 (start, end) 日期闭区间。None 表示不限。"""
    today = today or date.today()
    name = (name or "").strip().lower()

    if name in ("", "all", "全部", "所有", "一共", "总共"):
        return None, None

    if name in ("this_month", "本月", "这个月", "当月", "这个月"):
        start = today.replace(day=1)
        if today.month == 12:
            end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return start, end

    if name in ("last_month", "上月", "上个月"):
        first_this = today.replace(day=1)
        last_month_end = first_this - timedelta(days=1)
        start = last_month_end.replace(day=1)
        return start, last_month_end

    if name in ("this_year", "今年"):
        return today.replace(month=1, day=1), today.replace(month=12, day=31)

    if name in ("last_year", "去年"):
        y = today.year - 1
        return date(y, 1, 1), date(y, 12, 31)

    # 形如 2026 / 2026-01 / 2026年1月
    m = re.match(r"^(\d{4})(?:[-/](\d{1,2}))?$", name)
    if not m:
        m = re.search(r"(\d{4})\s*年\s*(?:(\d{1,2})\s*月)?", name or "")
    if m:
        y = int(m.group(1))
        if m.group(2):
            mo = int(m.group(2))
            start = date(y, mo, 1)
            if mo == 12:
                end = date(y, 12, 31)
            else:
                end = date(y, mo + 1, 1) - timedelta(days=1)
            return start, end
        return date(y, 1, 1), date(y, 12, 31)

    # 无法识别 → 默认当月
    start = today.replace(day=1)
    if today.month == 12:
        end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    return start, end


def range_label(start: Optional[date], end: Optional[date]) -> str:
    if start is None and end is None:
        return "全部"
    if start and end and start == end:
        return str(start)
    if start and end:
        return f"{start} ~ {end}"
    return str(start or end)


# --------------------------------------------------------------------------- #
# 纯 Python 查询执行器
# --------------------------------------------------------------------------- #
class LedgerQuery:
    """直接遍历内存中的 Beancount entries 进行统计，无需任何外部命令。"""

    def __init__(self, loader=None, entries: Optional[List] = None):
        if loader is not None:
            self.entries = getattr(loader, "entries", []) or []
        elif entries is not None:
            self.entries = entries
        else:
            self.entries = []

    # ---- 内部迭代器 ---- #
    def _iter_postings(self, start, end, prefix=None, keyword=None):
        for e in self.entries:
            if not isinstance(e, Transaction):
                continue
            if start and e.date < start:
                continue
            if end and e.date > end:
                continue
            for p in e.postings:
                if prefix and not p.account.startswith(prefix):
                    continue
                if keyword:
                    hay = f"{e.payee or ''} {e.narration or ''}"
                    if keyword.lower() not in hay.lower():
                        continue
                yield e, p

    def _sum_by_currency(self, start, end, prefix=None, keyword=None) -> Dict[str, float]:
        totals: Dict[str, float] = {}
        for _e, p in self._iter_postings(start, end, prefix, keyword):
            c = p.units.currency
            totals[c] = totals.get(c, 0.0) + float(p.units.number)
        return totals

    def _by_category(self, start, end, prefix, keyword) -> List[Tuple[str, Dict[str, float]]]:
        agg: Dict[str, Dict[str, float]] = {}
        for _e, p in self._iter_postings(start, end, prefix, keyword):
            agg.setdefault(p.account, {})
            c = p.units.currency
            agg[p.account][c] = agg[p.account].get(c, 0.0) + float(p.units.number)
        return sorted(agg.items(), key=lambda kv: -sum(abs(v) for v in kv[1].values()))

    def _trend(self, start, end, prefix, keyword) -> List[Tuple[str, Dict[str, float]]]:
        agg: Dict[str, Dict[str, float]] = {}
        for e, p in self._iter_postings(start, end, prefix, keyword):
            ym = f"{e.date.year}-{e.date.month:02d}"
            agg.setdefault(ym, {})
            c = p.units.currency
            agg[ym][c] = agg[ym].get(c, 0.0) + float(p.units.number)
        return sorted(agg.items())

    def _count_txns(self, start, end, prefix, keyword) -> int:
        cnt = 0
        for e in self.entries:
            if not isinstance(e, Transaction):
                continue
            if start and e.date < start:
                continue
            if end and e.date > end:
                continue
            matched = any(
                (not prefix or p.account.startswith(prefix))
                and (
                    not keyword
                    or keyword.lower() in f"{e.payee or ''} {e.narration or ''}".lower()
                )
                for p in e.postings
            )
            if matched:
                cnt += 1
        return cnt

    def _list(self, start, end, prefix, keyword, limit, default_currency) -> List[Tuple]:
        out = []
        for e in self.entries:
            if not isinstance(e, Transaction):
                continue
            if start and e.date < start:
                continue
            if end and e.date > end:
                continue
            ps = [
                p for p in e.postings
                if (not prefix or p.account.startswith(prefix))
                and (not keyword or keyword.lower() in f"{e.payee or ''} {e.narration or ''}".lower())
            ]
            if not ps:
                continue
            amt = sum(float(p.units.number) for p in ps if p.units.currency == default_currency)
            accs = sorted({p.account for p in ps})
            out.append((e.date, e.payee, e.narration, amt, accs))
        return out[-limit:]

    # ---- 格式化 ---- #
    @staticmethod
    def _fmt_amounts(label: str, totals: Dict[str, float]) -> str:
        if not totals:
            return f"{label}\n（无相关交易）"
        parts = " / ".join(
            f"{v:,.2f} {c}" for c, v in sorted(totals.items(), key=lambda x: -abs(x[1]))
        )
        return f"{label}\n{parts}"

    @staticmethod
    def _fmt_by_category(cats, title_range: str) -> str:
        if not cats:
            return f"📊 分类汇总 {title_range}\n（无相关交易）"
        lines = [f"📊 分类汇总 {title_range}（共 {len(cats)} 类）", ""]
        for acc, cur in cats[:15]:
            amts = " / ".join(
                f"{v:,.2f} {c}" for c, v in sorted(cur.items(), key=lambda x: -abs(x[1]))
            )
            lines.append(f"• {acc}: {amts}")
        return "\n".join(lines)

    @staticmethod
    def _fmt_list(rows, title_range: str) -> str:
        if not rows:
            return f"📋 交易明细 {title_range}\n（无相关交易）"
        lines = [f"📋 交易明细 {title_range}（最近 {len(rows)} 笔）", ""]
        for d, payee, narration, amt, accs in rows:
            title = payee or narration or "未命名"
            lines.append(f"{d} | {title}")
            lines.append(f"   {amt:,.2f}  {accs[0] if accs else ''}")
        return "\n".join(lines)

    @staticmethod
    def _fmt_trend(months) -> str:
        if not months:
            return "📈 月度趋势\n（无相关交易）"
        lines = ["📈 月度趋势", ""]
        for ym, cur in months:
            amts = " / ".join(
                f"{v:,.2f} {c}" for c, v in sorted(cur.items(), key=lambda x: -abs(x[1]))
            )
            lines.append(f"• {ym}: {amts}")
        return "\n".join(lines)

    # ---- 入口 ---- #
    def run_intent(self, intent: Dict[str, Any], default_currency: str = "CNY") -> str:
        metric = (intent.get("metric") or "total").lower()
        start, end = resolve_time_range(intent.get("time_range"))
        prefix = intent.get("account_prefix") or intent.get("account")
        keyword = intent.get("keyword")
        try:
            limit = int(intent.get("limit") or 10)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))
        title = range_label(start, end)

        if metric == "balance":
            if not prefix:
                return "❓ 请指定要查询余额的账户，例如：/query 余额 Assets:CN:DebitCard:CITIC:1709"
            bal = self._sum_by_currency(None, None, prefix, keyword)
            return self._fmt_amounts(f"💼 账户余额 {prefix}：", bal)

        if metric == "by_category":
            prefix = prefix or EXPENSES
            cats = self._by_category(start, end, prefix, keyword)
            return self._fmt_by_category(cats, title)

        if metric == "list":
            rows = self._list(start, end, prefix, keyword, limit, default_currency)
            return self._fmt_list(rows, title)

        if metric == "trend":
            prefix = prefix or EXPENSES
            months = self._trend(start, end, prefix, keyword)
            return self._fmt_trend(months)

        if metric == "count":
            n = self._count_txns(start, end, prefix, keyword)
            tail = f"（关键词：{keyword}）" if keyword else ""
            return f"🔢 {title} 共 {n} 笔交易{tail}"

        # 默认：支出合计
        prefix = prefix or EXPENSES
        totals = self._sum_by_currency(start, end, prefix, keyword)
        label = f"💰 支出合计 {title}"
        if keyword:
            label += f"（关键词：{keyword}）"
        return self._fmt_amounts(label + "：", totals)


# --------------------------------------------------------------------------- #
# 自然语言 → 查询意图
# --------------------------------------------------------------------------- #
def parse_intent_heuristic(text: str, loader=None, aliases: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """本地启发式：无 LLM 时把中文问题解析为 intent。"""
    t = (text or "").lower()

    # 时间
    if any(w in t for w in ["本月", "这个月", "当月"]):
        time_range = "this_month"
    elif any(w in t for w in ["上月", "上个月"]):
        time_range = "last_month"
    elif "今年" in t:
        time_range = "this_year"
    elif "去年" in t:
        time_range = "last_year"
    elif any(w in t for w in ["全部", "所有", "一共", "总共", "总"]):
        time_range = "all"
    else:
        m = re.search(r"(\d{4})\s*年\s*(?:(\d{1,2})\s*月)?", text or "")
        if m:
            time_range = f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)
        else:
            time_range = "this_month"

    # 指标
    if any(w in t for w in ["余额", "还剩", "净资产", "资产"]):
        metric = "balance"
    elif any(w in t for w in ["分类", "各类", "各", "占比", "分别", "构成"]):
        metric = "by_category"
    elif any(w in t for w in ["趋势", "每月", "按月", "每个月", "月报"]):
        metric = "trend"
    elif any(w in t for w in ["笔数", "几笔", "多少笔", "多少条"]):
        metric = "count"
    elif any(w in t for w in ["明细", "记录", "最近", "看看", "列", "清单"]):
        metric = "list"
    else:
        metric = "total"

    # 账户解析：优先别名（settings.yaml），其次 bean 元数据别名，再次账户名末段
    account = None
    keyword = None
    search_maps = []
    if aliases:
        search_maps.append(aliases)
    if loader is not None:
        search_maps.append(getattr(loader, "account_aliases", {}) or {})
    for amap in search_maps:
        for alias, acc in amap.items():
            if alias and alias in t:
                account = acc[0] if isinstance(acc, list) else acc
                break
        if account:
            break
    if not account and loader is not None:
        for acc in getattr(loader, "all_accounts", []) or []:
            last = acc.split(":")[-1].lower()
            if last and last in t:
                account = acc
                break
    # 用户直接输入账户前缀
    mm = re.search(r"(?:expenses|assets|income|liabilities):[A-Za-z0-9:]+", t)
    if mm:
        account = mm.group(0).capitalize()

    return {
        "metric": metric,
        "time_range": time_range,
        "keyword": keyword,
        "account": account,
        "limit": 10,
    }


def nl_to_intent(
    text: str,
    ai_client=None,
    loader=None,
    aliases: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """自然语言 → intent：优先 LLM，失败回退启发式。"""
    accounts_ctx = "\n".join((getattr(loader, "all_accounts", []) or [])[:200])
    intent: Dict[str, Any] = {}
    if ai_client is not None:
        try:
            intent = ai_client.nl_to_query_intent(text, accounts_ctx)
        except Exception as e:  # noqa: BLE001
            print(f"[query] LLM 解析失败，回退启发式: {e}")
            intent = {}
    if not isinstance(intent, dict) or not intent.get("metric"):
        intent = parse_intent_heuristic(text, loader, aliases)
    return intent
