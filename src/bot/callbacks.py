"""
Telegram 回调处理器

从 main.py 提取的按钮回调处理逻辑。
"""
import math
import datetime
from html import escape
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.utils.logger import get_bot_logger
from src.core.transaction_log import TransactionLog
from src.core.image_rules import meal_payee_for_food

logger = get_bot_logger()


class CallbackHandlers:
    """按钮回调处理器类"""
    
    def __init__(self, matcher, ledger, config, tx_log: TransactionLog = None):
        """
        初始化处理器
        
        Args:
            matcher: HybridMatcher 实例
            ledger: LedgerAppender 实例
            config: AppConfig 实例
            tx_log: TransactionLog 实例
        """
        self.matcher = matcher
        self.ledger = ledger
        self.config = config
        self.tx_log = tx_log
        self.currency = config.default_currency
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """统一按钮回调处理入口"""
        query = update.callback_query
        await query.answer()

        callback_data = query.data
        if callback_data.startswith('view_tx_'):
            await self._handle_view_transaction(update, context, callback_data)
            return
        if callback_data == 'recent_back':
            await self._handle_recent_back(update, context)
            return

        data = context.user_data.get('pending_tx')
        ambiguous_data = context.user_data.get('pending_ambiguous')

        if not data and not ambiguous_data and callback_data != 'cancel':
            await query.edit_message_text("⏰ 会话已过期。")
            return

        # 路由到具体处理函数
        if callback_data.startswith('sel_disc_'):
            await self._handle_discount_selection(update, context, callback_data)
        elif callback_data.startswith('sel_asset_'):
            await self._handle_asset_selection(update, context, callback_data)
        elif callback_data.startswith('sel_alias_'):
            await self._handle_alias_selection(update, context, callback_data)
        elif callback_data.startswith('alias_page_'):
            await self._handle_alias_pagination(update, context, callback_data)
        elif callback_data == 'alias_manual':
            await self._handle_manual_input(update, context)
        elif callback_data == 'confirm':
            await self._handle_confirm(update, context)
        elif callback_data == 'cancel':
            await self._handle_cancel(update, context)
        elif callback_data == 'edit_expense':
            await self._handle_edit_expense(update, context)

    async def _handle_view_transaction(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        callback_data: str
    ):
        """查看已保存交易的完整分录详情。"""
        query = update.callback_query
        tx_id = callback_data.removeprefix('view_tx_')

        if not self.tx_log:
            await query.edit_message_text("❌ 交易日志未启用。")
            return

        record = self.tx_log.get_by_id(tx_id)
        if not record:
            await query.edit_message_text("❌ 未找到这笔交易记录。")
            return

        entry_text = self._render_record_entry(record)
        summary_lines = [
            "📘 交易详情",
            "",
            f"状态: {record.status}",
            f"日期: {record.date}",
        ]
        if record.payee:
            summary_lines.append(f"商户: {record.payee}")
        if record.narration:
            summary_lines.append(f"描述: {record.narration}")
        summary_lines.extend([
            f"金额: {abs(record.amount):.2f} {record.currency}",
            f"交易ID: {record.tx_id}",
            "",
            "Beancount 分录:",
            escape(entry_text.strip()),
        ])

        keyboard = [[InlineKeyboardButton("⬅️ 返回列表", callback_data='recent_back')]]
        await query.edit_message_text(
            "<pre>" + escape("\n".join(summary_lines[:-1])) + "\n" + summary_lines[-1] + "</pre>",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML',
        )

    async def _handle_recent_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """返回最近交易列表。"""
        query = update.callback_query
        tx_ids = context.user_data.get('recent_records')

        if not tx_ids or not self.tx_log:
            await query.edit_message_text("⏰ 最近交易列表已过期，请重新发送 /recent。")
            return

        records = [self.tx_log.get_by_id(tx_id) for tx_id in tx_ids]
        records = [record for record in records if record and record.status == 'confirmed']
        if not records:
            await query.edit_message_text("📚 暂无已存入的交易记录。")
            return

        lines = [f"📚 最近已存入交易（最近 {len(records)} 笔）", ""]
        keyboard = []

        for idx, tx in enumerate(reversed(records), start=1):
            title = tx.payee or tx.narration or "未命名交易"
            lines.append(f"{idx}. {tx.date} | {abs(tx.amount):.2f} {tx.currency} | {title}")
            if tx.payee and tx.narration:
                lines.append(f"描述: {tx.narration}")
            lines.append(f"{tx.asset_account} -> {tx.expense_account}")
            if tx.discount_account and tx.discount_amount:
                lines.append(f"优惠: {tx.discount_account} (-{tx.discount_amount:.2f})")
            lines.append("")
            keyboard.append([
                InlineKeyboardButton(f"查看第 {idx} 笔", callback_data=f"view_tx_{tx.tx_id}")
            ])

        await query.edit_message_text(
            "\n".join(lines).rstrip(),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    
    async def _handle_discount_selection(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
        callback_data: str
    ):
        """处理优惠账户选择"""
        query = update.callback_query
        
        if callback_data.startswith('sel_disc_legacy_'):
            # 处理遗留解析流程的优惠歧义
            idx = int(callback_data.split('_')[-1])
            saved_data = context.user_data.get('pending_ambiguous_discount')
            if not saved_data:
                await query.edit_message_text("⏰ 会话已过期。")
                return
            
            selected_disc_acc = saved_data['discount_vals'][0][idx]
            disc_val = saved_data['discount_vals'][1]
            
            description = saved_data['description']
            main_amount = saved_data['amount']
            asset_candidates = saved_data['asset_candidates']
            discount_info = (selected_disc_acc, disc_val)
            
            context.user_data.pop('pending_ambiguous_discount', None)
            
            # 继续检查资产歧义
            if asset_candidates and len(asset_candidates) > 1:
                context.user_data['pending_ambiguous'] = {
                    'description': description,
                    'amount': main_amount,
                    'discount_info': discount_info,
                    'candidates': asset_candidates
                }
                
                keyboard = []
                for i, acc in enumerate(asset_candidates):
                    label = acc.split(':')[-1]
                    keyboard.append([InlineKeyboardButton(
                        f"💳 {label} ({acc})", 
                        callback_data=f'sel_asset_{i}'
                    )])
                keyboard.append([InlineKeyboardButton("❌ 取消", callback_data='cancel')])
                
                await query.edit_message_text(
                    f"✅ 已选择优惠: {selected_disc_acc}\n\n⚠️ **资产账户有歧义！**\n请选择：",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
                return
            
            asset_account = asset_candidates[0] if asset_candidates else "Assets:Unknown"
            await self._resume_prediction(update, context, description, main_amount, asset_account, discount_info)
            return
        
        else:
            # 处理位置解析流程的优惠歧义
            idx = int(callback_data.split('_')[-1])
            saved_data = context.user_data.get('pending_ambiguous_discount')
            if not saved_data:
                await query.edit_message_text("⏰ 会话已过期。")
                return
            
            candidates = saved_data['candidates']
            selected_acc = candidates[idx]
            original_data = saved_data['data']
            
            amount = original_data['discount_info'][1]
            original_data['discount_info'] = (selected_acc, amount)
            
            context.user_data.pop('pending_ambiguous_discount', None)
            
            await query.edit_message_text(f"✅ 已选择优惠: {selected_acc}\n正在处理...")
            
            await self._resume_prediction(
                update, context,
                description=f"{original_data['payee']} {original_data['narration']}",
                amount=original_data['amount'],
                asset_account=original_data['asset'],
                discount_info=original_data['discount_info'],
                pre_parsed_data=original_data
            )
    
    async def _handle_asset_selection(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
        callback_data: str
    ):
        """处理资产账户选择"""
        query = update.callback_query
        idx = int(callback_data.split('_')[-1])
        
        ambiguous_data = context.user_data.get('pending_ambiguous')
        if not ambiguous_data:
            await query.edit_message_text("⏰ 会话已过期。")
            return
        
        selected_asset = ambiguous_data['candidates'][idx]
        disc_info = ambiguous_data.get('discount_info')
        context.user_data.pop('pending_ambiguous', None)
        
        await query.edit_message_text("🤖 资产已选择，正在分析...")
        
        result = self.matcher.predict_details(ambiguous_data['description'])
        expense_account = result.get('account') or "Expenses:Unknown"
        payee = result.get('payee', "")
        narration = result.get('narration', ambiguous_data['description'])
        
        context.user_data['pending_tx'] = {
            'date': datetime.date.today(),
            'payee': payee,
            'narration': narration,
            'amount': ambiguous_data['amount'],
            'currency': self.currency,
            'asset': selected_asset,
            'expense': expense_account,
            'discount_info': disc_info
        }
        
        await self._show_confirmation(update, context)
    
    async def _handle_alias_selection(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
        callback_data: str
    ):
        """处理别名选择"""
        query = update.callback_query
        idx = int(callback_data.split('_')[-1])
        
        data = context.user_data.get('alias_selection')
        if not data:
            await query.edit_message_text("⏰ 会话已过期。")
            return
        
        alias, account = data['candidates'][idx]
        context.user_data.pop('alias_selection', None)
        
        if context.user_data.get('pending_tx'):
            context.user_data['pending_tx']['expense'] = account
            postings = context.user_data['pending_tx'].get('postings')
            if postings:
                counterparty_index = context.user_data['pending_tx'].get('counterparty_posting_index', len(postings) - 1)
                if 0 <= counterparty_index < len(postings):
                    postings[counterparty_index]['account'] = account
            self._apply_food_payee(context.user_data['pending_tx'])
            await self._show_confirmation(update, context)
    
    async def _handle_alias_pagination(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
        callback_data: str
    ):
        """处理别名分页"""
        page = int(callback_data.split('_')[-1])
        await self.show_alias_selection(update, context, page)
    
    async def _handle_manual_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理手动输入请求"""
        query = update.callback_query
        context.user_data.pop('alias_selection', None)
        await query.edit_message_text("请输入新的分类账户名称：")
        context.user_data['awaiting_expense_edit'] = True
    
    async def _handle_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理确认操作"""
        query = update.callback_query
        data = context.user_data.get('pending_tx')
        
        if not data:
            await query.edit_message_text("⏰ 会话已过期。")
            return
        
        # 记录交易日志
        tx_id = None
        if self.tx_log:
            tx_id = self.tx_log.log_transaction(data, 'pending')
        
        # 写入账本
        if data.get('postings'):
            success, message = self.ledger.append_postings(
                date=data['date'],
                postings=data['postings'],
                currency=data['currency'],
                payee=data.get('payee', ""),
                narration=data['narration'],
                metadata=data.get('metadata'),
            )
        else:
            success, message = self.ledger.append_transaction(
                data['date'],
                data['narration'],
                data['amount'],
                data['currency'],
                data['asset'],
                data['expense'],
                payee=data.get('payee', ""),
                discount_tx=data.get('discount_info'),
                converted_amount=data.get('converted_amount'),
                converted_currency=data.get('converted_currency')
            )
        
        if success:
            # 更新日志状态
            if self.tx_log and tx_id:
                self.tx_log.update_status(tx_id, 'confirmed')
            
            await query.edit_message_text(
                f"✅ 已保存:\n"
                f"📝 {data['narration']}\n"
                f"💰 {data['amount']} {data['currency']}"
            )
        else:
            # 更新日志状态为失败
            if self.tx_log and tx_id:
                self.tx_log.update_status(tx_id, 'failed', message)
            
            await query.edit_message_text(
                f"❌ 保存失败:\n{message}\n\n"
                f"请重试或联系管理员。"
            )
        
        context.user_data.pop('pending_tx', None)
    
    async def _handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理取消操作"""
        query = update.callback_query
        await query.edit_message_text("❌ 已取消。")
        context.user_data.pop('pending_tx', None)
        context.user_data.pop('pending_ambiguous', None)
        context.user_data.pop('pending_ambiguous_discount', None)
    
    async def _handle_edit_expense(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理修改分类请求"""
        aliases = self.matcher.get_all_aliases()
        context.user_data['alias_selection'] = {
            'candidates': aliases,
            'page': 0
        }
        await self.show_alias_selection(update, context, 0)
    
    async def show_alias_selection(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
        page: int = 0
    ):
        """显示别名选择界面"""
        data = context.user_data.get('alias_selection')
        if not data:
            await update.effective_message.edit_text("⏰ 会话已过期。")
            return
        
        aliases = data['candidates']
        per_page = 30
        total_pages = math.ceil(len(aliases) / per_page) if aliases else 1
        
        # 限制页码范围
        page = max(0, min(page, total_pages - 1))
        
        start_idx = page * per_page
        end_idx = start_idx + per_page
        current_batch = aliases[start_idx:end_idx]
        
        keyboard = []
        row = []
        for i, (alias, acc) in enumerate(current_batch):
            abs_idx = start_idx + i
            label = alias[:12] + "..." if len(alias) > 15 else alias
            row.append(InlineKeyboardButton(label, callback_data=f'sel_alias_{abs_idx}'))
            
            if len(row) == 3:
                keyboard.append(row)
                row = []
        
        if row:
            keyboard.append(row)
        
        # 导航按钮
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f'alias_page_{page-1}'))
        nav_row.append(InlineKeyboardButton("📝 手动输入", callback_data='alias_manual'))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton("下一页 ➡️", callback_data=f'alias_page_{page+1}'))
        
        keyboard.append(nav_row)
        keyboard.append([InlineKeyboardButton("❌ 取消", callback_data='cancel')])
        
        await update.effective_message.edit_text(
            f"**选择账户 (第 {page+1}/{total_pages} 页)**:\n选择匹配的分类别名。",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _show_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示确认卡片"""
        query = update.callback_query
        tx_data = context.user_data.get('pending_tx')
        
        if not tx_data:
            await query.edit_message_text("⏰ 会话已过期。")
            return
        
        expense_account = tx_data['expense']
        
        keyboard = [
            [InlineKeyboardButton(f"✅ 确认: {expense_account}", callback_data='confirm')],
            [InlineKeyboardButton("✏️ 修改分类", callback_data='edit_expense')],
            [InlineKeyboardButton("❌ 取消", callback_data='cancel')]
        ]
        
        discount_str = ""
        if tx_data.get('discount_info'):
            acc, val = tx_data['discount_info']
            discount_str = f"**优惠**: {acc} (-{val})\n"
        
        payee = tx_data.get('payee', "")
        payee_line = f"**商户**: {payee}\n" if payee else ""
        
        display_amount = abs(tx_data['amount']) if tx_data.get('postings') else tx_data['amount']
        amount_display = f"{display_amount} {tx_data['currency']}"
        if tx_data.get('converted_amount') and tx_data.get('converted_currency'):
            amount_display += f" @@ {tx_data['converted_amount']} {tx_data['converted_currency']}"

        review_line = ""
        if tx_data.get('needs_review'):
            review_line = "**复核**: 截图识别存在不确定字段\n"

        notes_line = ""
        if tx_data.get('notes'):
            notes_line = f"**备注**: {tx_data['notes']}\n"
        
        account_lines = (
            f"**支出(借方)**: {tx_data['asset']}\n"
            f"**收入(贷方)**: {expense_account}"
            if tx_data.get('postings')
            else f"**资金账户**: {tx_data['asset']}\n**对手账户**: {expense_account}"
        )

        await query.edit_message_text(
            f"📝 **确认交易**\n\n"
            f"**日期**: {tx_data.get('date')}\n"
            f"{payee_line}"
            f"**描述**: {tx_data['narration']}\n"
            f"**金额**: {amount_display}\n"
            f"{review_line}"
            f"{notes_line}"
            f"{discount_str}"
            f"{account_lines}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def _resume_prediction(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        description: str,
        amount: float,
        asset_account: str,
        discount_info=None,
        pre_parsed_data=None
    ):
        """恢复预测流程"""
        query = update.callback_query
        
        result = self.matcher.predict_details(description)
        expense_account = result.get('account') or "Expenses:Unknown"
        
        if pre_parsed_data:
            payee = pre_parsed_data.get('payee', '')
            narration = pre_parsed_data.get('narration', description)
            tx_currency = pre_parsed_data.get('currency') or self.currency
            converted_amount = pre_parsed_data.get('converted_amount')
            converted_currency = pre_parsed_data.get('converted_currency')
        else:
            payee = result.get('payee', "")
            narration = result.get('narration', description)
            tx_currency = self.currency
            converted_amount = None
            converted_currency = None
        
        context.user_data['pending_tx'] = {
            'date': datetime.date.today(),
            'payee': payee,
            'narration': narration,
            'amount': amount,
            'currency': tx_currency,
            'converted_amount': converted_amount,
            'converted_currency': converted_currency,
            'asset': asset_account,
            'expense': expense_account,
            'discount_info': discount_info
        }
        self._apply_food_payee(context.user_data['pending_tx'])
        
        await self._show_confirmation(update, context)

    def _apply_food_payee(self, tx_data: dict):
        metadata = tx_data.get('metadata') or {}
        payee = meal_payee_for_food(tx_data.get('expense', ''), metadata.get('transaction_time', ''))
        if payee:
            tx_data['payee'] = payee

    def _render_record_entry(self, record) -> str:
        """将日志记录渲染为 Beancount 分录文本。"""
        if record.postings:
            return self.ledger.render_postings(
                date=datetime.date.fromisoformat(record.date),
                postings=record.postings,
                currency=record.currency,
                payee=record.payee,
                narration=record.narration,
                metadata=record.metadata or {},
            )

        discount_tx = None
        if record.discount_account and record.discount_amount:
            discount_tx = (record.discount_account, record.discount_amount)

        return self.ledger.render_transaction(
            date=datetime.date.fromisoformat(record.date),
            narration=record.narration,
            amount=record.amount,
            currency=record.currency,
            asset_account=record.asset_account,
            expense_account=record.expense_account,
            payee=record.payee,
            discount_tx=discount_tx,
            converted_amount=record.converted_amount,
            converted_currency=record.converted_currency,
        )
