"""
护栏（Guardrails）

隐私优先的记账机器人必须防止两类风险：
1. **提示注入（injection）**：用户（或转发的消息 / 图片说明）试图改写机器人的
   系统指令，让 AI 做出超出记账/查询范围的事。
2. **数据外泄（exfiltration）**：诱导机器人把账本原始数据、系统设定等私密的
   内容以非预期方式输出。

所有用户输入在交给 AI 解析或写入账本之前，先经过 :meth:`Guardrail.scan`。
命中即拒绝，且不回显原始输入，避免二次泄露。
"""
import re
from dataclasses import dataclass
from typing import List


@dataclass
class ScanResult:
    blocked: bool
    category: str                  # injection | exfiltration | none
    reason: str = ""


class Guardrail:
    # 提示注入：试图改写 / 忽略系统指令
    INJECTION_PATTERNS: List[str] = [
        r"忽略.{0,6}(之前|以上|先前|上面|所有|你的).{0,6}(指令|规则|提示|设定|prompt|system)",
        r"无视.{0,6}(之前|以上|先前|上面|所有).{0,6}(指令|规则|提示|设定)",
        r"忘记.{0,6}(之前|以上|先前).{0,6}(指令|规则|提示|设定)",
        r"system\s*prompt",
        r"your\s+(previous\s+)?instructions",
        r"ignore\s+(all\s+)?(previous|above|the\s+)?instructions",
        r"reveal\s+(your|the)\s+(instructions|system\s+prompt|prompt)",
        r"repeat\s+your\s+instructions",
        r"越狱|jailbreak",
    ]
    # 数据外泄：明确的泄露/外发动词 + 账本数据指代
    EXFIL_PATTERNS: List[str] = [
        r"把.{0,6}(账本|交易|记录|流水).{0,6}(都|全部|所有|每一个).{0,6}(发|告诉|输出|打印|给)",
        r"(输出|打印|导出|泄露|dump|send).{0,8}(所有|全部|整个).{0,8}(账本|交易|记录|流水)",
        r"(reveal|dump|export|print|send).{0,6}(all|every).{0,6}(transaction|ledger|record|entry)",
        r"(泄露|透露|公开).{0,6}(你的|系统|内部|账本)",
    ]

    def __init__(self):
        self._inj = [re.compile(p, re.I) for p in self.INJECTION_PATTERNS]
        self._exf = [re.compile(p, re.I) for p in self.EXFIL_PATTERNS]

    def scan(self, text: str) -> ScanResult:
        """扫描文本，返回是否拦截及原因。"""
        if not text:
            return ScanResult(False, "none")

        for r in self._inj:
            if r.search(text):
                return ScanResult(True, "injection", "检测到可能的提示注入")

        for r in self._exf:
            if r.search(text):
                return ScanResult(True, "exfiltration", "检测到可能的账本数据外泄请求")

        return ScanResult(False, "none")

    @staticmethod
    def refusal_message() -> str:
        return (
            "🛡️ 出于隐私安全，我无法执行该请求。\n"
            "本机器人只处理：记账（描述 + 金额）与账本查询。"
        )
