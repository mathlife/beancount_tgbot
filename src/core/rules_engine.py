"""
账户映射规则引擎

把原来硬编码在 image_rules.py 中的「付款方式 -> 资金账户」「收款方/备注/分类关键词 -> 对手方账户」
「银行简称」「payee 重命名」等映射，迁移到可编辑的纯文本 YAML 配置（config/rules.yaml），
让用户可以在一开始就设定自己的规则，并随时增减。

设计约束：单用户、隐私优先、纯文本、无数据库 —— 规则持久化到 YAML 文件，不引入任何 DB。
"""
import os
from typing import Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


# 各规则种类的键名
KIND_PAYMENT = "payment_method_map"
KIND_COUNTERPARTY = "counterparty_map"
KIND_BANK_SHORT = "bank_short_names"
KIND_PAYEE_RENAME = "payee_rename"

_SUPPORTED_KINDS = (KIND_PAYMENT, KIND_COUNTERPARTY, KIND_BANK_SHORT, KIND_PAYEE_RENAME)


def _norm_entry(entry: dict, kind: str) -> dict:
    """规整单条规则，补全默认值。"""
    out = dict(entry)
    out["match"] = str(out.get("match", "")).strip()
    out["provider"] = str(out.get("provider", "any")).strip().lower() or "any"
    out["priority"] = int(out.get("priority", 0) or 0)
    out["regex"] = bool(out.get("regex", False))
    # 对手方/付款方式支持方向感知（收入/支出分别映射到不同账户）
    out["account"] = str(out.get("account", "") or "").strip()
    out["account_outflow"] = str(out.get("account_outflow", "") or "").strip()
    out["account_inflow"] = str(out.get("account_inflow", "") or "").strip()
    if kind == KIND_BANK_SHORT:
        out["short"] = str(out.get("short", "") or "").strip()
    if kind == KIND_PAYEE_RENAME:
        out["rename"] = str(out.get("rename", "") or "")
        out["requires"] = str(out.get("requires", "") or "").strip()
    return out


def _sort_key(e: dict):
    # 优先级高者优先；同优先级时更长的匹配串优先（更具体）
    return (-e["priority"], -len(e["match"]))


class RulesEngine:
    """加载、匹配与管理账户映射规则。"""

    def __init__(self, rules: Optional[dict] = None, path: Optional[str] = None):
        self.path = path
        self.rules: dict = rules if rules is not None else {}
        self._build_index()

    # ---------- 构建 / 加载 ----------
    def _build_index(self):
        self.payment_method_map: List[dict] = [
            _norm_entry(e, KIND_PAYMENT) for e in self.rules.get(KIND_PAYMENT, [])
        ]
        self.counterparty_map: List[dict] = [
            _norm_entry(e, KIND_COUNTERPARTY) for e in self.rules.get(KIND_COUNTERPARTY, [])
        ]
        self.bank_short_names: List[dict] = [
            _norm_entry(e, KIND_BANK_SHORT) for e in self.rules.get(KIND_BANK_SHORT, [])
        ]
        self.payee_rename: List[dict] = [
            _norm_entry(e, KIND_PAYEE_RENAME) for e in self.rules.get(KIND_PAYEE_RENAME, [])
        ]
        for lst in (self.payment_method_map, self.counterparty_map,
                    self.bank_short_names, self.payee_rename):
            lst.sort(key=_sort_key)

    @classmethod
    def from_file(cls, path: str) -> "RulesEngine":
        if not os.path.exists(path):
            raise FileNotFoundError(f"规则文件不存在: {path}")
        if yaml is None:  # pragma: no cover
            raise RuntimeError("缺少 yaml 依赖，无法加载规则文件")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(rules=data, path=path)

    def save(self) -> None:
        """把当前规则写回 YAML 文件（纯文本持久化）。"""
        if not self.path:
            raise RuntimeError("未指定规则文件路径，无法保存")
        if yaml is None:  # pragma: no cover
            raise RuntimeError("缺少 yaml 依赖，无法保存规则文件")
        with open(self.path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.rules, f, allow_unicode=True, sort_keys=False)

    # ---------- 匹配底层 ----------
    @staticmethod
    def _matches(entry: dict, text: str, provider: str) -> bool:
        if entry["provider"] not in ("any", provider):
            return False
        match = entry["match"]
        if not match:
            return False
        if entry["regex"]:
            import re
            try:
                return re.search(match, text) is not None
            except re.error:
                return False
        return match.lower() in text.lower()

    @staticmethod
    def _pick_account(entry: dict, is_outflow: Optional[bool]) -> str:
        """按方向选择账户：优先 account，其次 outflow/inflow。"""
        if entry.get("account"):
            return entry["account"]
        if is_outflow is True and entry.get("account_outflow"):
            return entry["account_outflow"]
        if is_outflow is False and entry.get("account_inflow"):
            return entry["account_inflow"]
        # 方向未知时退而求其次
        if entry.get("account_outflow"):
            return entry["account_outflow"]
        if entry.get("account_inflow"):
            return entry["account_inflow"]
        return ""

    # ---------- 解析接口 ----------
    def resolve_payment_account(self, method_text: str, provider: str = "any",
                               is_outflow: Optional[bool] = None) -> str:
        text = (method_text or "").strip()
        for e in self.payment_method_map:
            if self._matches(e, text, provider):
                return self._pick_account(e, is_outflow)
        return ""

    def resolve_counterparty_account(self, search_text: str, provider: str = "any",
                                    is_outflow: Optional[bool] = None) -> str:
        text = (search_text or "").strip()
        for e in self.counterparty_map:
            if self._matches(e, text, provider):
                acct = self._pick_account(e, is_outflow)
                if acct:
                    return acct
        return ""

    def resolve_bank_short(self, method_text: str) -> str:
        """从付款方式文本中解析银行简称；命中返回 short（缺省回退 match）。"""
        text = (method_text or "").strip()
        for e in self.bank_short_names:
            if self._matches(e, text, "any"):
                return e.get("short") or e["match"]
        return ""

    def apply_payee_rename(self, payee: str, search_text: str,
                           provider: str = "any") -> str:
        """按规则重命名 payee；支持模板 {bank}（用银行简称替换）。"""
        import re
        result = payee or ""
        for e in self.payee_rename:
            if e["provider"] not in ("any", provider):
                continue
            requires = e.get("requires", "")
            if requires and requires.lower() not in (search_text or "").lower():
                continue
            match = e["match"]
            if not match:
                continue
            if e["regex"]:
                if re.search(match, result) is None:
                    continue
            else:
                if match.lower() not in result.lower():
                    continue
            rename = e.get("rename", "")
            if "{bank}" in rename:
                bank = self.resolve_bank_short(search_text)
                rename = rename.replace("{bank}", bank)
            if e["regex"]:
                result = re.sub(match, rename, result)
            else:
                result = rename
        return result

    # ---------- 管理接口 ----------
    def list_rules(self, kind: Optional[str] = None) -> Dict[str, List[tuple]]:
        """返回 {kind: [(display_id, entry_dict), ...]}，display_id 从 1 开始。"""
        out: Dict[str, List[tuple]] = {}
        targets = {kind: getattr(self, kind)} if kind in _SUPPORTED_KINDS else {
            k: getattr(self, k) for k in _SUPPORTED_KINDS
        }
        for k, lst in targets.items():
            out[k] = [(i + 1, e) for i, e in enumerate(lst)]
        return out

    def add_rule(self, kind: str, match: str, account: str,
                 provider: str = "any", regex: bool = False,
                 priority: int = 0, account_outflow: str = "",
                 account_inflow: str = "") -> int:
        if kind not in _SUPPORTED_KINDS:
            raise ValueError(f"不支持的规则类型: {kind}")
        entry = {
            "match": match,
            "provider": provider,
            "regex": regex,
            "priority": priority,
        }
        if kind == KIND_PAYEE_RENAME:
            entry["rename"] = account  # 复用 account 字段承载 rename 模板
            entry["requires"] = ""
        else:
            if account_outflow or account_inflow:
                entry["account_outflow"] = account_outflow
                entry["account_inflow"] = account_inflow
            else:
                entry["account"] = account
        self.rules.setdefault(kind, []).append(entry)
        self._build_index()
        # 返回该条在排序后的 display_id
        target_norm = _norm_entry(entry, kind)
        lst = getattr(self, kind)
        for i, e in enumerate(lst):
            if e == target_norm:
                return i + 1
        return len(lst)

    def del_rule(self, kind: str, display_id: int) -> bool:
        if kind not in _SUPPORTED_KINDS:
            raise ValueError(f"不支持的规则类型: {kind}")
        lst = getattr(self, kind)
        if display_id < 1 or display_id > len(lst):
            return False
        target = lst[display_id - 1]
        # 从原始 rules 中按身份移除
        raw_list = self.rules.get(kind, [])
        for i, e in enumerate(raw_list):
            if _norm_entry(e, kind) is target or _norm_entry(e, kind) == target:
                raw_list.pop(i)
                break
        self._build_index()
        return True

    def reset(self, seed: dict) -> None:
        """用新的种子规则覆盖当前规则（例如恢复默认）。"""
        self.rules = seed
        self._build_index()
        if self.path:
            self.save()
