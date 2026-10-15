"""
意图路由（Intent Routing）

将用户的自由文本分类为三种意图：
- ``transaction``：记账（描述 + 金额）
- ``query``：     查询账本（自然语言问题）
- ``chitchat``：  闲聊 / 不在机器人职责范围内的请求

设计原则（与项目约束一致）：
- 启发式优先，离线可用、零 API 成本、确定性强；
- 可选注入 ``ai_client`` 做 LLM 增强，但默认不调用 AI（保持轻量、私密）。
"""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IntentResult:
    intent: str                       # transaction | query | chitchat
    confidence: float                 # 0..1
    reason: str = ""
    raw: dict = field(default_factory=dict)


class IntentRouter:
    # 明确的查询关键词（即使没有金额也判为查询）
    QUERY_KEYWORDS = [
        "查", "查询", "多少", "花费", "花销", "支出多少", "收入多少",
        "分类", "明细", "笔数", "本月", "上月", "今年", "去年", "全部",
        "所有", "统计", "汇总", "报表", "月报", "年报", "上半年", "下半年",
        "balance", "report", "summary", "how much", "spent", "total", "trend",
        "list", "stats", "query",
    ]
    # 无论是否含金额，始终判为查询的词（余额/报表类）
    QUERY_ALWAYS = ["余额", "结余", "balance", "report", "summary"]

    _AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?")

    def __init__(self, ai_client=None, accounts_hint: str = ""):
        self.ai_client = ai_client
        self.accounts_hint = accounts_hint

    def classify(self, text: str) -> IntentResult:
        """对一条文本做意图分类，返回 :class:`IntentResult`。"""
        if not text or not text.strip():
            return IntentResult("chitchat", 1.0, "空消息")

        t = text.strip()
        low = t.lower()

        has_amount = bool(self._AMOUNT_RE.search(t))
        has_query_word = any(k in low for k in self.QUERY_KEYWORDS)

        # 1) 始终是查询的词（余额/报表）优先
        if any(k in low for k in self.QUERY_ALWAYS):
            return IntentResult("query", 0.85, "命中余额/报表类关键词")

        # 2) 无金额 + 查询关键词 -> 查询
        if not has_amount and has_query_word:
            return IntentResult("query", 0.9, "含查询关键词且无金额")

        # 3) 有金额 -> 记账（记账是机器人的首要职责）
        if has_amount:
            return IntentResult("transaction", 0.9, "含金额，按记账处理")

        # 4) 其余（无金额、无查询关键词）-> 闲聊 / 不在范围内
        return IntentResult("chitchat", 0.8, "无金额、无查询关键词")

    def classify_via_llm(self, text: str) -> Optional[IntentResult]:
        """可选的 LLM 增强：当启发式置信度不足时使用。AI 不可用时返回 None。"""
        if not self.ai_client:
            return None
        try:
            raw = self.ai_client.classify_intent(text, self.accounts_hint)
        except Exception:  # noqa: BLE001
            return None
        if not raw or "intent" not in raw:
            return None
        intent = raw["intent"]
        if intent not in ("transaction", "query", "chitchat"):
            return None
        try:
            conf = float(raw.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        return IntentResult(intent, conf, "llm", raw)
