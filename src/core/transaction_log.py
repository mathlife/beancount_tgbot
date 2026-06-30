"""
交易日志系统

记录所有交易操作，支持查询和恢复。
"""
import json
import os
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

from src.utils.logger import get_core_logger

logger = get_core_logger()


@dataclass
class TransactionRecord:
    """交易记录"""
    tx_id: str
    timestamp: str
    status: str  # pending, confirmed, failed, cancelled
    date: str
    payee: str
    narration: str
    amount: float
    currency: str
    asset_account: str
    expense_account: str
    converted_amount: Optional[float] = None
    converted_currency: Optional[str] = None
    discount_account: Optional[str] = None
    discount_amount: Optional[float] = None
    postings: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TransactionRecord':
        return cls(**data)


class TransactionLog:
    """交易日志管理器"""
    
    def __init__(self, log_dir: str = "data/logs"):
        """
        初始化交易日志
        
        Args:
            log_dir: 日志目录路径
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_log_file = self._get_log_file_path()

    def _refresh_log_file(self):
        """刷新当前日志文件路径，避免跨月运行仍写旧文件。"""
        self._current_log_file = self._get_log_file_path()
    
    def _get_log_file_path(self) -> Path:
        """获取当前日志文件路径（按月分割）"""
        today = datetime.now()
        filename = f"transactions_{today.year}_{today.month:02d}.jsonl"
        return self.log_dir / filename
    
    def _generate_tx_id(self) -> str:
        """生成交易 ID"""
        return f"tx_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    
    def log_transaction(
        self,
        tx_data: dict,
        status: str = "pending"
    ) -> str:
        """
        记录交易
        
        Args:
            tx_data: 交易数据字典
            status: 交易状态
        
        Returns:
            交易 ID
        """
        self._refresh_log_file()
        tx_id = self._generate_tx_id()
        
        # 处理 date 字段
        tx_date = tx_data.get('date')
        if isinstance(tx_date, date):
            tx_date = tx_date.isoformat()
        
        # 处理 discount_info
        discount_account = None
        discount_amount = None
        if tx_data.get('discount_info'):
            discount_account, discount_amount = tx_data['discount_info']
        
        record = TransactionRecord(
            tx_id=tx_id,
            timestamp=datetime.now().isoformat(),
            status=status,
            date=tx_date or datetime.now().date().isoformat(),
            payee=tx_data.get('payee', ''),
            narration=tx_data.get('narration', ''),
            amount=tx_data.get('amount', 0.0),
            currency=tx_data.get('currency', 'CNY'),
            asset_account=tx_data.get('asset', ''),
            expense_account=tx_data.get('expense', ''),
            converted_amount=tx_data.get('converted_amount'),
            converted_currency=tx_data.get('converted_currency'),
            discount_account=discount_account,
            discount_amount=discount_amount,
            postings=tx_data.get('postings'),
            metadata=tx_data.get('metadata'),
        )
        
        self._append_record(record)
        logger.info(f"交易已记录: {tx_id}")
        return tx_id
    
    def update_status(self, tx_id: str, status: str, error_message: str = None) -> bool:
        """
        更新交易状态
        
        Args:
            tx_id: 交易 ID
            status: 新状态
            error_message: 错误信息（如果失败）
        
        Returns:
            是否更新成功
        """
        self._refresh_log_file()

        # 追加一条状态更新记录
        update_record = {
            "type": "status_update",
            "tx_id": tx_id,
            "timestamp": datetime.now().isoformat(),
            "new_status": status,
            "error_message": error_message
        }
        
        try:
            with open(self._current_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(update_record, ensure_ascii=False) + '\n')
            logger.info(f"交易状态已更新: {tx_id} -> {status}")
            return True
        except Exception as e:
            logger.error(f"更新交易状态失败: {e}")
            return False
    
    def _append_record(self, record: TransactionRecord):
        """追加记录到日志文件"""
        try:
            with open(self._current_log_file, 'a', encoding='utf-8') as f:
                data = {"type": "transaction", **record.to_dict()}
                f.write(json.dumps(data, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"写入交易日志失败: {e}")
            raise

    def _load_records(self) -> List[TransactionRecord]:
        """加载并回放所有交易及其状态更新。"""
        records_by_id = {}
        tx_order = []

        for log_file in sorted(self.log_dir.glob("transactions_*.jsonl")):
            with open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue

                    entry_type = data.get('type')
                    if entry_type == 'transaction':
                        tx_data = dict(data)
                        del tx_data['type']
                        record = TransactionRecord.from_dict(tx_data)
                        records_by_id[record.tx_id] = record
                        tx_order.append(record.tx_id)
                    elif entry_type == 'status_update':
                        tx_id = data.get('tx_id')
                        record = records_by_id.get(tx_id)
                        if not record:
                            continue
                        record.status = data.get('new_status', record.status)
                        if 'error_message' in data:
                            record.error_message = data.get('error_message')

        return [records_by_id[tx_id] for tx_id in tx_order if tx_id in records_by_id]

    def get_recent(self, count: int = 10, status: Optional[str] = None) -> List[TransactionRecord]:
        """
        获取最近的交易记录
        
        Args:
            count: 返回数量
            status: 可选状态过滤
        
        Returns:
            交易记录列表
        """
        records = self._load_records()
        if status:
            records = [record for record in records if record.status == status]

        return records[-count:]
    
    def get_by_id(self, tx_id: str) -> Optional[TransactionRecord]:
        """
        根据 ID 获取交易记录
        
        Args:
            tx_id: 交易 ID
        
        Returns:
            交易记录或 None
        """
        for record in reversed(self._load_records()):
            if record.tx_id == tx_id:
                return record
        return None
    
    def get_today_summary(self) -> Dict[str, Any]:
        """
        获取今日交易汇总
        
        Returns:
            汇总信息字典
        """
        today = datetime.now().date().isoformat()
        today_records = [
            record
            for record in self._load_records()
            if record.date == today and record.status == 'confirmed'
        ]
        
        total_amount = sum(r.amount for r in today_records)
        
        return {
            'date': today,
            'count': len(today_records),
            'total_amount': total_amount,
            'transactions': today_records
        }
