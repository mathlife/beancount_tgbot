"""
账本模块单元测试

测试 LedgerAppender 的写入、验证、备份和撤销功能。
"""
import datetime
import shutil
from pathlib import Path
import pytest
from src.core.ledger import LedgerAppender

# 测试数据
TEST_BEAN_FILE = "tests/data/test.bean"
TEST_BACKUP_DIR = "tests/data/backups"

@pytest.fixture
def setup_ledger():
    """初始化测试环境"""
    # 创建测试目录
    Path("tests/data").mkdir(parents=True, exist_ok=True)
    
    # 清理旧文件
    if Path(TEST_BEAN_FILE).exists():
        Path(TEST_BEAN_FILE).unlink()
    if Path(TEST_BACKUP_DIR).exists():
        shutil.rmtree(TEST_BACKUP_DIR)
        
    # 创建空的 bean 文件
    with open(TEST_BEAN_FILE, 'w', encoding='utf-8') as f:
        f.write('option "title" "Test Ledger"\n\n')
        
    ledger = LedgerAppender(TEST_BEAN_FILE, TEST_BACKUP_DIR)
    yield ledger
    
    # 清理
    # if Path(TEST_BEAN_FILE).exists():
    #     Path(TEST_BEAN_FILE).unlink()
    # if Path(TEST_BACKUP_DIR).exists():
    #     shutil.rmtree(TEST_BACKUP_DIR)

class TestLedgerAppender:
    """测试 LedgerAppender"""
    
    def test_append_basic_transaction(self, setup_ledger):
        """测试写入基础交易"""
        ledger = setup_ledger
        success, msg = ledger.append_transaction(
            date=datetime.date(2026, 1, 26),
            narration="Lunch", # 使用英文避免测试输出乱码干扰
            amount=32.0,
            currency="CNY",
            asset_account="Assets:CN:WeChat",
            expense_account="Expenses:Food"
        )
        assert success is True
        
        with open(TEST_BEAN_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert '2026-01-26 * "Lunch"' in content
        # 验证包含关键数值和账户，忽略中间的对齐空格
        assert 'Expenses:Food' in content and '32.00 CNY' in content
        assert 'Assets:CN:WeChat' in content and '-32.00 CNY' in content
        assert content.index('Assets:CN:WeChat') < content.index('Expenses:Food')

    def test_append_with_payee(self, setup_ledger):
        """测试带商户的交易"""
        ledger = setup_ledger
        success, msg = ledger.append_transaction(
            date=datetime.date(2026, 1, 26),
            narration="Dinner",
            amount=50.0,
            currency="CNY",
            asset_account="Assets:CN:Cash",
            expense_account="Expenses:Food",
            payee="DaoHeFeng"
        )
        assert success is True
        
        with open(TEST_BEAN_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            
        assert '2026-01-26 * "DaoHeFeng" "Dinner"' in content

    def test_append_income(self, setup_ledger):
        """测试收入交易（金额取负）"""
        ledger = setup_ledger
        success, msg = ledger.append_transaction(
            date=datetime.date(2026, 1, 26),
            narration="Salary",
            amount=10000.0,
            currency="CNY",
            asset_account="Assets:CN:Bank",
            expense_account="Income:Salary"
        )
        assert success is True
        
        with open(TEST_BEAN_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 收入应为负数，资产应为正数
        assert 'Income:Salary' in content and '-10000.00 CNY' in content
        assert 'Assets:CN:Bank' in content and '10000.00 CNY' in content

    def test_append_with_discount(self, setup_ledger):
        """测试带优惠的交易"""
        ledger = setup_ledger
        success, msg = ledger.append_transaction(
            date=datetime.date(2026, 1, 26),
            narration="Taxi",
            amount=15.0,
            currency="CNY",
            asset_account="Assets:CN:WeChat",
            expense_account="Expenses:Transport",
            discount_tx=("Expenses:Discount", 3.0)
        )
        assert success is True
        
        with open(TEST_BEAN_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 检查优惠行和资产计算
        # Expense(15) + Discount(-3) + Asset = 0 => Asset = -12
        assert 'Expenses:Discount' in content and '-3.00 CNY' in content
        assert 'Assets:CN:WeChat' in content and '-12.00 CNY' in content
        assert content.index('Assets:CN:WeChat') < content.index('Expenses:Transport')

    def test_undo_last_transaction(self, setup_ledger):
        """测试撤销功能"""
        ledger = setup_ledger
        # 写入一笔
        ledger.append_transaction(
            date=datetime.date(2026, 1, 26),
            narration="测试交易",
            amount=10.0,
            currency="CNY",
            asset_account="Assets:Cash",
            expense_account="Expenses:Test"
        )
        
        with open(TEST_BEAN_FILE, 'r', encoding='utf-8') as f:
            content_before = f.read()
        assert "测试交易" in content_before
        
        # 撤销
        success = ledger.undo_last_entry()
        assert success is True
        
        with open(TEST_BEAN_FILE, 'r', encoding='utf-8') as f:
            content_after = f.read()
        assert "测试交易" not in content_after
        
        # 再次撤销应失败
        assert ledger.undo_last_entry() is False

    def test_validation_error(self, setup_ledger):
        """测试格式验证错误"""
        ledger = setup_ledger
        # 缺少账户
        success, msg = ledger.append_transaction(
            date=datetime.date(2026, 1, 26),
            narration="错误交易",
            amount=10.0,
            currency="CNY",
            asset_account="", # 如果为空
            expense_account="Expenses:Test"
        )
        # 我们的构建函数会生成空字符串的账户，如果验证逻辑检查了空行
        # _validate_entry 会检查 Expenses 和 Assets 关键字
        # asset_account="" -> 只有 Expenses 行，缺少 Assets 行
        assert success is False
        assert "验证失败" in msg

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
