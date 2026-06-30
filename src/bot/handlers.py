"""
Telegram 消息处理器

从 main.py 提取的消息处理逻辑。
"""
import datetime
import re
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.image_rules import ExtractedImageTransaction, apply_image_rules, meal_payee_for_food
from src.core.transaction_log import TransactionLog
from src.utils.logger import get_bot_logger

logger = get_bot_logger()


class MessageHandlers:
    """消息处理器类"""

    def __init__(self, matcher, ledger, config, tx_log: TransactionLog = None):
        self.matcher = matcher
        self.ledger = ledger
        self.config = config
        self.tx_log = tx_log
        self.allowed_user_id = config.allowed_user_id
        self.currency = config.default_currency
        self.aliases = config.aliases

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令"""
        await update.message.reply_text(
            "🤖 Beancount Bot Ready!\n"
            "格式: 描述 金额 [账户别名]\n"
            "示例: 午饭 32 wx\n"
            "也可以直接上传支付截图自动识别。\n"
            "命令: /today 查看今日汇总, /recent 查看最近已存交易。"
        )

    async def reload_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /reload 命令"""
        if update.effective_user.id != self.allowed_user_id:
            return

        args = context.args if context.args else []

        try:
            if 'config' in args or 'all' in args:
                from src.config import load_config

                new_config = load_config()
                self.aliases = new_config.aliases
                self.currency = new_config.default_currency
                self.matcher.local_expenses_map = new_config.aliases
                await update.message.reply_text("✅ 配置已重新加载。")

            if 'config' not in args or 'all' in args:
                self.matcher.loader.load()
                count = len(self.matcher.loader.all_accounts)
                await update.message.reply_text(f"✅ Beancount 已重新加载！发现 {count} 个账户。")
        except Exception as e:
            logger.error(f"重新加载失败: {e}")
            await update.message.reply_text(f"❌ 重新加载失败: {e}")

    async def undo_last(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /undo 命令 - 撤销最后一笔交易"""
        if update.effective_user.id != self.allowed_user_id:
            return

        if self.ledger.undo_last_entry():
            await update.message.reply_text("✅ 已撤销最后一笔交易。")
            if self.tx_log:
                recent = self.tx_log.get_recent(1)
                if recent:
                    self.tx_log.update_status(recent[0].tx_id, 'cancelled')
        else:
            await update.message.reply_text("❌ 没有可撤销的交易。")

    async def today_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /today 命令 - 显示今日交易汇总"""
        if update.effective_user.id != self.allowed_user_id:
            return

        if not self.tx_log:
            await update.message.reply_text("❌ 交易日志未启用。")
            return

        summary = self.tx_log.get_today_summary()

        if summary['count'] == 0:
            await update.message.reply_text("📊 今日暂无交易记录。")
            return

        lines = [
            f"📊 **今日交易汇总** ({summary['date']})",
            f"共 {summary['count']} 笔交易",
            f"总金额: {summary['total_amount']:.2f} {self.currency}",
            "",
            "**明细：**",
        ]

        for tx in summary['transactions'][-10:]:
            lines.append(f"• {tx.narration}: {tx.amount:.2f} {tx.currency}")

        if len(summary['transactions']) > 10:
            lines.append(f"...还有 {len(summary['transactions']) - 10} 笔")

        await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

    async def recent_transactions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /recent 命令 - 显示最近已存入的交易记录"""
        if update.effective_user.id != self.allowed_user_id:
            return

        if not self.tx_log:
            await update.message.reply_text("❌ 交易日志未启用。")
            return

        count = 10
        if context.args:
            try:
                count = int(context.args[0])
            except ValueError:
                await update.message.reply_text("❌ 用法: /recent [数量]，数量必须是整数。")
                return

        count = max(1, min(count, 20))
        records = self.tx_log.get_recent(count, status='confirmed')

        if not records:
            await update.message.reply_text("📚 暂无已存入的交易记录。")
            return

        context.user_data['recent_records'] = [tx.tx_id for tx in records]

        lines = [f"📚 最近已存入交易（最近 {len(records)} 笔）", ""]
        keyboard = []

        for idx, tx in enumerate(reversed(records), start=1):
            title = tx.payee or tx.narration or "未命名交易"
            lines.append(
                f"{idx}. {tx.date} | {abs(tx.amount):.2f} {tx.currency} | {title}"
            )
            if tx.payee and tx.narration:
                lines.append(f"描述: {tx.narration}")
            lines.append(f"{tx.asset_account} -> {tx.expense_account}")
            if tx.discount_account and tx.discount_amount:
                lines.append(f"优惠: {tx.discount_account} (-{tx.discount_amount:.2f})")
            lines.append("")
            keyboard.append([
                InlineKeyboardButton(
                    f"查看第 {idx} 笔",
                    callback_data=f"view_tx_{tx.tx_id}"
                )
            ])

        await update.message.reply_text(
            "\n".join(lines).rstrip(),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def image_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理截图/图片消息，识别成待确认交易。"""
        if update.effective_user.id != self.allowed_user_id:
            return

        message = update.message
        if not message:
            return

        status_msg = await message.reply_text("🖼️ 正在识别截图...")

        try:
            telegram_file, mime_type = await self._get_image_file(message)
            if not telegram_file:
                await status_msg.edit_text("❌ 请上传图片或图片文件。")
                return

            image_bytes = bytes(await telegram_file.download_as_bytearray())
            raw = self.matcher.ai_client.extract_image_transaction(
                image_bytes=image_bytes,
                mime_type=mime_type,
                default_currency=self.currency,
                caption=message.caption or ""
            )

            extracted = self._build_extracted_transaction(raw)
            resolved = apply_image_rules(extracted)

            context.user_data['pending_tx'] = {
                'date': resolved.date,
                'payee': resolved.payee,
                'narration': resolved.narration,
                'amount': extracted.amount,
                'currency': resolved.currency,
                'asset': resolved.funding_account or "Assets:Unknown",
                'expense': resolved.counterparty_account or "Expenses:Unknown",
                'discount_info': self._extract_discount_info(resolved.postings),
                'needs_review': resolved.needs_review,
                'confidence': resolved.confidence,
                'notes': resolved.notes,
                'funding_posting_index': resolved.funding_index,
                'counterparty_posting_index': resolved.counterparty_index,
                'metadata': {
                    'tx_id': resolved.tx_id,
                    'category': resolved.category,
                    'method': resolved.method,
                    'transaction_time': resolved.transaction_time,
                },
                'postings': [
                    {'account': posting.account, 'amount': posting.amount, 'currency': resolved.currency}
                    for posting in resolved.postings
                ],
            }

            await self._show_confirmation_message(status_msg, context.user_data['pending_tx'])
        except Exception as e:
            logger.error(f"截图识别失败: {e}")
            await status_msg.edit_text(f"❌ {self._format_image_error(e)}")

    async def _get_image_file(self, message):
        """返回 Telegram 文件对象和 MIME 类型。"""
        if message.photo:
            return await message.photo[-1].get_file(), "image/jpeg"

        document = message.document
        if document and document.mime_type and document.mime_type.startswith("image/"):
            return await document.get_file(), document.mime_type

        return None, None

    def _build_extracted_transaction(self, raw: dict) -> ExtractedImageTransaction:
        amount = self._parse_amount_value_with_sign(raw.get('actual_amount'), keep_sign=True)
        if amount is None:
            raise ValueError("截图中没有识别到实付金额")

        return ExtractedImageTransaction(
            date=self._parse_transaction_date(raw.get('date')),
            payee=str(raw.get('payee') or "").strip(),
            receiver_name=str(raw.get('receiver_name') or "").strip(),
            narration=str(raw.get('narration') or "").strip(),
            amount=amount,
            order_amount=self._parse_amount_value(raw.get('order_amount')),
            discount_amount=self._parse_amount_value(raw.get('discount_amount')),
            currency=str(raw.get('currency') or self.currency).strip() or self.currency,
            payment_method=str(raw.get('payment_method') or "").strip(),
            category=str(raw.get('category') or "").strip(),
            tx_id=str(raw.get('tx_id') or "").strip(),
            direction=str(raw.get('direction') or "").strip(),
            transaction_time=self._extract_transaction_time(raw),
            notes=str(raw.get('notes') or "").strip(),
            confidence=raw.get('confidence'),
            needs_review=bool(raw.get('needs_review')),
        )

    def _extract_transaction_time(self, raw: dict) -> str:
        transaction_time = str(raw.get('transaction_time') or "").strip()
        if transaction_time:
            return transaction_time

        date_value = raw.get('date')
        if date_value and re.search(r'\d{1,2}[:：时点]\d{0,2}', str(date_value)):
            return str(date_value).strip()
        return ""

    def _extract_discount_info(self, postings: list):
        for posting in postings:
            if ("Discount" in posting.account or posting.account == "Assets:CN:WXLJJ") and posting.amount < 0:
                return (posting.account, abs(posting.amount))
        return None

    def _parse_amount_value(self, value) -> Optional[float]:
        return self._parse_amount_value_with_sign(value, keep_sign=False)

    def _parse_amount_value_with_sign(self, value, keep_sign: bool) -> Optional[float]:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            number = float(value)
            return number if keep_sign else abs(number)

        match = re.search(r'[+-]?\d+(?:,\d{3})*(?:\.\d+)?|[+-]?\d+(?:\.\d+)?', str(value))
        if not match:
            return None

        number = float(match.group(0).replace(',', ''))
        return number if keep_sign else abs(number)

    def _format_image_error(self, error: Exception) -> str:
        message = str(error)
        if 'User location is not supported for the API use' in message:
            return '服务器出口地区不支持 Gemini 图片接口，且 OCR 回退也没有成功。'
        return f'截图识别失败: {message}'

    def _parse_transaction_date(self, value) -> datetime.date:
        if not value:
            return datetime.date.today()
        if isinstance(value, datetime.date):
            return value

        raw = str(value).strip().replace('/', '-')
        try:
            return datetime.date.fromisoformat(raw[:10])
        except ValueError:
            match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', raw)
            if match:
                year, month, day = map(int, match.groups())
                return datetime.date(year, month, day)
        return datetime.date.today()

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理用户消息"""
        if update.effective_user.id != self.allowed_user_id:
            return

        text = update.message.text
        positional_result = self.matcher.parse_positional(text)
        if positional_result:
            return await self._handle_positional_result(update, context, positional_result, text)

        remaining_text, asset_candidates = self.matcher.resolve_asset(text)
        description, amounts_list = self.matcher.parse_amounts(remaining_text)

        if not amounts_list:
            await update.message.reply_text("❌ 无法识别金额。")
            return

        main_amount = amounts_list[0]
        discount_info = None

        if len(amounts_list) >= 2:
            discount_info, description = self._check_discount(
                description, amounts_list, asset_candidates, update, context
            )
            if discount_info == "PENDING":
                return

        if asset_candidates and len(asset_candidates) > 1:
            return await self._handle_ambiguous_asset(
                update, context, description, main_amount, asset_candidates, discount_info
            )

        if asset_candidates:
            asset_account = asset_candidates[0]
        else:
            cash_candidates = self.matcher.loader.get_accounts_by_alias('cash')
            asset_account = cash_candidates[0] if cash_candidates else "Assets:Unknown"

        await self.process_prediction(update, context, description, main_amount, asset_account, discount_info)

    async def _handle_positional_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE, result: dict, original_text: str):
        """处理位置解析成功的结果"""
        discount_info = result.get('discount_info')

        if discount_info:
            disc_accs, disc_amt = discount_info
            if isinstance(disc_accs, list) and len(disc_accs) > 1:
                context.user_data['pending_ambiguous_discount'] = {
                    'description': original_text,
                    'data': result,
                    'candidates': disc_accs,
                }

                keyboard = []
                for idx, acc in enumerate(disc_accs):
                    label = acc.split(':')[-1]
                    keyboard.append([InlineKeyboardButton(f"🎟️ {label} ({acc})", callback_data=f'sel_disc_{idx}')])
                keyboard.append([InlineKeyboardButton("❌ 取消", callback_data='cancel')])

                await update.message.reply_text(
                    "⚠️ **优惠账户有歧义！**\n请选择：",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown',
                )
                return
            elif isinstance(disc_accs, list) and len(disc_accs) == 1:
                result['discount_info'] = (disc_accs[0], disc_amt)

        await self.process_prediction(
            update,
            context,
            description=f"{result['payee']} {result['narration']}",
            amount=result['amount'],
            asset_account=result['asset'],
            discount_info=result.get('discount_info'),
            pre_parsed_data=result,
        )

    def _check_discount(self, description: str, amounts_list: list, asset_candidates: list, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """检查是否包含优惠信息"""
        found_key = None
        found_accounts = []

        for key, account in self.aliases.items():
            if key in description and ("Discount" in account or "Rebate" in account):
                found_key = key
                found_accounts = [account]
                break

        if not found_key:
            for alias, accounts in self.matcher.loader.account_aliases.items():
                if alias in description:
                    valid_accs = [a for a in accounts if "Discount" in a or "Rebate" in a]
                    if valid_accs:
                        found_key = alias
                        found_accounts = valid_accs
                        break

        if not found_key:
            return None, description

        disc_val = amounts_list[1]
        main_amount = amounts_list[0]

        if len(found_accounts) > 1:
            context.user_data['pending_ambiguous_discount'] = {
                'description': description.replace(found_key, "").strip(),
                'amount': main_amount,
                'asset_candidates': asset_candidates,
                'discount_vals': (found_accounts, disc_val),
                'found_key': found_key,
            }
            return "PENDING", description

        if found_accounts:
            clean_desc = description.replace(found_key, "").strip()
            clean_desc = re.sub(r'\s+', ' ', clean_desc).strip()
            return (found_accounts[0], disc_val), clean_desc

        return None, description

    async def _handle_ambiguous_asset(self, update: Update, context: ContextTypes.DEFAULT_TYPE, description: str, amount: float, candidates: list, discount_info):
        """处理资产账户歧义"""
        context.user_data['pending_ambiguous'] = {
            'description': description,
            'amount': amount,
            'discount_info': discount_info,
            'candidates': candidates,
        }

        keyboard = []
        for idx, acc in enumerate(candidates):
            label = acc.split(':')[-1]
            keyboard.append([InlineKeyboardButton(f"💳 {label} ({acc})", callback_data=f'sel_asset_{idx}')])
        keyboard.append([InlineKeyboardButton("❌ 取消", callback_data='cancel')])

        await update.message.reply_text(
            "⚠️ **资产账户有歧义！**\n请选择：",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown',
        )

    async def process_prediction(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        description: str,
        amount: float,
        asset_account: str,
        discount_info=None,
        pre_parsed_data=None,
    ):
        """处理预测并显示确认卡片"""
        msg = await update.message.reply_text("🤖 正在分析...")

        result = self.matcher.predict_details(description)
        expense_account = result.get('account') or "Expenses:Unknown"

        if pre_parsed_data:
            payee = pre_parsed_data['payee']
            narration = pre_parsed_data['narration']
        else:
            payee = result.get('payee', "")
            narration = result.get('narration', description)

        tx_currency = self.currency
        converted_amount = None
        converted_currency = None

        if pre_parsed_data:
            if pre_parsed_data.get('currency'):
                tx_currency = pre_parsed_data['currency']
            converted_amount = pre_parsed_data.get('converted_amount')
            converted_currency = pre_parsed_data.get('converted_currency')

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
            'discount_info': discount_info,
        }

        await self._show_confirmation_message(msg, context.user_data['pending_tx'])

    async def _show_confirmation_message(self, message, tx_data: dict):
        keyboard = [
            [InlineKeyboardButton(f"✅ 确认: {tx_data['expense']}", callback_data='confirm')],
            [InlineKeyboardButton("✏️ 修改分类", callback_data='edit_expense')],
            [InlineKeyboardButton("❌ 取消", callback_data='cancel')],
        ]

        discount_str = ""
        if tx_data.get('discount_info'):
            acc, val = tx_data['discount_info']
            discount_str = f"**优惠**: {acc} (-{val})\n"

        payee_line = f"**商户**: {tx_data.get('payee', '')}\n" if tx_data.get('payee') else ""
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
            f"**收入(贷方)**: {tx_data['expense']}"
            if tx_data.get('postings')
            else f"**支出**: {tx_data['asset']}\n**分类**: {tx_data['expense']}"
        )

        await message.edit_text(
            f"📝 **确认交易**\n\n"
            f"**日期**: {tx_data['date']}\n"
            f"{payee_line}"
            f"**描述**: {tx_data['narration']}\n"
            f"**金额**: {amount_display}\n"
            f"{review_line}"
            f"{notes_line}"
            f"{discount_str}"
            f"{account_lines}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown',
        )

    async def text_handler_wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """文本消息包装器"""
        if context.user_data.get('awaiting_expense_edit'):
            new_account = update.message.text.strip()
            context.user_data['pending_tx']['expense'] = new_account
            postings = context.user_data['pending_tx'].get('postings')
            counterparty_index = context.user_data['pending_tx'].get('counterparty_posting_index')
            if postings and isinstance(counterparty_index, int) and 0 <= counterparty_index < len(postings):
                postings[counterparty_index]['account'] = new_account
            self._apply_food_payee(context.user_data['pending_tx'])
            context.user_data['awaiting_expense_edit'] = False

            data = context.user_data['pending_tx']
            keyboard = [
                [InlineKeyboardButton(f"✅ 确认: {new_account}", callback_data='confirm')],
                [InlineKeyboardButton("❌ 取消", callback_data='cancel')],
            ]

            discount_str = ""
            if data.get('discount_info'):
                _, val = data['discount_info']
                discount_str = f"(优惠: {val}) "

            await update.message.reply_text(
                f"已更新分类: {new_account}\n{discount_str}确认？",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        else:
            await self.handle_message(update, context)

    def _apply_food_payee(self, tx_data: dict):
        metadata = tx_data.get('metadata') or {}
        payee = meal_payee_for_food(tx_data.get('expense', ''), metadata.get('transaction_time', ''))
        if payee:
            tx_data['payee'] = payee
