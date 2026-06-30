"""
账本追加器

负责将交易记录写入 Beancount 文件，包含错误处理和备份机制。
"""
import datetime
import shutil
import time
from pathlib import Path
from typing import Optional, Tuple

from src.utils.logger import get_core_logger
from src.core.exceptions import LedgerWriteError, LedgerValidationError

logger = get_core_logger()


class LedgerAppender:
    """账本追加器"""
    
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # 秒
    
    def __init__(self, bean_file_path: str, backup_dir: str = "data/backups"):
        """
        初始化账本追加器
        
        Args:
            bean_file_path: Beancount 文件路径
            backup_dir: 备份目录路径
        """
        self.bean_file_path = Path(bean_file_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._last_entry: Optional[str] = None
    
    def append_transaction(
        self,
        date: datetime.date,
        narration: str,
        amount: float,
        currency: str,
        asset_account: str,
        expense_account: str,
        payee: str = "",
        discount_tx: tuple = None,
        converted_amount: float = None,
        converted_currency: str = None
    ) -> Tuple[bool, str]:
        """
        追加交易到账本
        
        Args:
            date: 交易日期
            narration: 交易描述
            amount: 金额
            currency: 货币
            asset_account: 资产账户
            expense_account: 支出/收入账户
            payee: 商户名
            discount_tx: 优惠信息 (账户, 金额)
            converted_amount: 转换后金额
            converted_currency: 转换后货币
        
        Returns:
            (成功标志, 错误信息或成功消息)
        """
        # 构建交易条目
        entry = self._build_entry(
            date, narration, amount, currency,
            asset_account, expense_account, payee,
            discount_tx, converted_amount, converted_currency
        )
        
        # 验证条目格式
        validation_error = self._validate_entry(entry)
        if validation_error:
            logger.error(f"交易验证失败: {validation_error}")
            return False, f"验证失败: {validation_error}"
        
        # 创建备份
        backup_path = self._create_backup()
        
        # 尝试写入（带重试）
        for attempt in range(self.MAX_RETRIES):
            try:
                self._write_entry(entry)
                self._last_entry = entry
                logger.info(f"交易已写入: {narration} {amount} {currency}")
                return True, "写入成功"
            except Exception as e:
                logger.warning(f"写入失败 (尝试 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    # 恢复备份
                    if backup_path and backup_path.exists():
                        self._restore_backup(backup_path)
                    error_msg = f"写入失败，已恢复备份: {e}"
                    logger.error(error_msg)
                    return False, error_msg
        
        return False, "未知错误"

    def append_postings(
        self,
        date: datetime.date,
        postings: list,
        currency: str,
        payee: str = "",
        narration: str = "",
        metadata: dict = None
    ) -> Tuple[bool, str]:
        """直接写入多分录交易。"""
        entry = self._build_postings_entry(
            date=date,
            postings=postings,
            currency=currency,
            payee=payee,
            narration=narration,
            metadata=metadata or {}
        )

        validation_error = self._validate_entry(entry)
        if validation_error:
            logger.error(f"交易验证失败: {validation_error}")
            return False, f"验证失败: {validation_error}"

        backup_path = self._create_backup()

        for attempt in range(self.MAX_RETRIES):
            try:
                self._write_entry(entry)
                self._last_entry = entry
                logger.info(f"交易已写入: {payee} {narration}")
                return True, "写入成功"
            except Exception as e:
                logger.warning(f"写入失败 (尝试 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    if backup_path and backup_path.exists():
                        self._restore_backup(backup_path)
                    error_msg = f"写入失败，已恢复备份: {e}"
                    logger.error(error_msg)
                    return False, error_msg

        return False, "未知错误"

    def render_transaction(
        self,
        date: datetime.date,
        narration: str,
        amount: float,
        currency: str,
        asset_account: str,
        expense_account: str,
        payee: str = "",
        discount_tx: tuple = None,
        converted_amount: float = None,
        converted_currency: str = None
    ) -> str:
        """渲染普通双分录交易，不写入文件。"""
        return self._build_entry(
            date=date,
            narration=narration,
            amount=amount,
            currency=currency,
            asset_account=asset_account,
            expense_account=expense_account,
            payee=payee,
            discount_tx=discount_tx,
            converted_amount=converted_amount,
            converted_currency=converted_currency,
        )

    def render_postings(
        self,
        date: datetime.date,
        postings: list,
        currency: str,
        payee: str = "",
        narration: str = "",
        metadata: dict = None
    ) -> str:
        """渲染多分录交易，不写入文件。"""
        return self._build_postings_entry(
            date=date,
            postings=postings,
            currency=currency,
            payee=payee,
            narration=narration,
            metadata=metadata or {},
        )
    
    def _build_entry(
        self,
        date: datetime.date,
        narration: str,
        amount: float,
        currency: str,
        asset_account: str,
        expense_account: str,
        payee: str = "",
        discount_tx: tuple = None,
        converted_amount: float = None,
        converted_currency: str = None
    ) -> str:
        """构建 Beancount 交易条目"""
        # 交易头部
        if payee:
            header = f'{date} * "{payee}" "{narration}"'
        else:
            header = f'{date} * "{narration}"'
        
        # 收入账户金额取负
        if expense_account.startswith('Income'):
            amount = -abs(amount)
        
        # 确定平衡货币和金额
        balance_currency = currency
        balance_amount = amount
        
        expense_line_str = f"{amount:.2f} {currency}"
        
        if converted_amount and converted_currency:
            expense_line_str += f" @@ {converted_amount:.2f} {converted_currency}"
            balance_currency = converted_currency
            balance_amount = converted_amount
            if expense_account.startswith('Income'):
                balance_amount = -abs(balance_amount)
        
        running_total = balance_amount
        
        # 优惠行
        discount_lines = ""
        if discount_tx:
            disc_acc, disc_amt = discount_tx
            disc_val = -abs(disc_amt)
            discount_lines = f"    {disc_acc:<40} {disc_val:>10.2f} {balance_currency}\n"
            running_total += disc_val
        
        # 资产行（自动平衡）
        asset_val = -running_total
        asset_str = f"{asset_val:.2f}"
        
        entry = f"""
{header}
    {asset_account:<40} {asset_str:>10} {balance_currency}
{discount_lines}    {expense_account:<40} {expense_line_str:>10}
"""
        return entry

    def _build_postings_entry(
        self,
        date: datetime.date,
        postings: list,
        currency: str,
        payee: str = "",
        narration: str = "",
        metadata: dict = None
    ) -> str:
        """构建支持元数据的多分录 Beancount 条目。"""
        if payee:
            header = f'{date} * "{payee}" "{narration}"'
        else:
            header = f'{date} * "{narration}"'

        metadata_lines = []
        for key, value in (metadata or {}).items():
            if value in (None, ""):
                continue
            metadata_lines.append(f"  {key}: \"{value}\"")

        posting_lines = [
            f"    {item['account']:<51} {item['amount']:.2f} {item.get('currency', currency)}"
            for item in postings
        ]

        lines = [header]
        lines.extend(metadata_lines)
        lines.extend(posting_lines)
        return "\n" + "\n".join(lines) + "\n"
    
    def _validate_entry(self, entry: str) -> Optional[str]:
        """
        验证交易条目格式
        
        Args:
            entry: 交易条目字符串
        
        Returns:
            错误信息或 None（验证通过）
        """
        lines = entry.strip().split('\n')
        
        if len(lines) < 3:
            return "交易条目行数不足"
        
        # 检查日期行格式
        first_line = lines[0].strip()
        if not first_line or first_line[0] not in '0123456789':
            return "交易头部格式错误"
        
        # 检查是否包含必要的账户行
        has_expense = False
        has_asset = False
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith('Expenses:') or stripped.startswith('Income:'):
                has_expense = True
            if stripped.startswith('Assets:') or stripped.startswith('Liabilities:'):
                has_asset = True
        
        if not has_expense:
            return "缺少支出/收入账户"
        if not has_asset:
            return "缺少资产账户"
        
        return None
    
    def _create_backup(self) -> Optional[Path]:
        """创建当前账本文件的备份"""
        if not self.bean_file_path.exists():
            return None
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self.bean_file_path.stem}_{timestamp}.bak"
        backup_path = self.backup_dir / backup_name
        
        try:
            shutil.copy2(self.bean_file_path, backup_path)
            logger.debug(f"已创建备份: {backup_path}")
            
            # 清理旧备份（保留最近 10 个）
            self._cleanup_old_backups()
            
            return backup_path
        except Exception as e:
            logger.warning(f"创建备份失败: {e}")
            return None
    
    def _restore_backup(self, backup_path: Path):
        """从备份恢复账本文件"""
        try:
            shutil.copy2(backup_path, self.bean_file_path)
            logger.info(f"已从备份恢复: {backup_path}")
        except Exception as e:
            logger.error(f"恢复备份失败: {e}")
            raise LedgerWriteError(f"恢复备份失败: {e}", str(self.bean_file_path))
    
    def _cleanup_old_backups(self, keep_count: int = 10):
        """清理旧备份文件"""
        backups = sorted(
            self.backup_dir.glob(f"{self.bean_file_path.stem}_*.bak"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        for old_backup in backups[keep_count:]:
            try:
                old_backup.unlink()
                logger.debug(f"已删除旧备份: {old_backup}")
            except Exception as e:
                logger.warning(f"删除旧备份失败: {e}")
    
    def _write_entry(self, entry: str):
        """写入交易条目到文件"""
        try:
            with open(self.bean_file_path, 'a', encoding='utf-8') as f:
                f.write(entry)
        except IOError as e:
            raise LedgerWriteError(f"写入文件失败: {e}", str(self.bean_file_path))
    
    def get_last_entry(self) -> Optional[str]:
        """获取最后写入的交易条目"""
        return self._last_entry
    
    def undo_last_entry(self) -> bool:
        """
        撤销最后一笔交易（从文件中移除）
        
        Returns:
            是否撤销成功
        """
        if not self._last_entry:
            logger.warning("没有可撤销的交易")
            return False
        
        try:
            # 读取文件内容
            with open(self.bean_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 移除最后一笔交易
            if self._last_entry in content:
                new_content = content.replace(self._last_entry, '', 1)
                
                # 创建备份后写入
                self._create_backup()
                with open(self.bean_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                logger.info("已撤销最后一笔交易")
                self._last_entry = None
                return True
            else:
                logger.warning("未找到最后一笔交易")
                return False
        except Exception as e:
            logger.error(f"撤销失败: {e}")
            return False
