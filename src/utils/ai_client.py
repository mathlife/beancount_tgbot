import json
import time
from datetime import date
from typing import Any, List

from google import genai
from google.genai import types

from src.utils.image_ocr import OCRImageExtractor


class GeminiClient:
    def __init__(self, api_key: str):
        # Handle comma-separated keys.
        if ',' in api_key:
            self.keys = [k.strip() for k in api_key.split(',') if k.strip()]
        else:
            self.keys = [api_key]

        self.current_key_index = 0
        self._init_client()
        self.model_name = 'gemini-2.5-flash'
        self.ocr_extractor = OCRImageExtractor()

    def _init_client(self):
        print(f"Initializing Gemini Client with Key index {self.current_key_index}")
        self.client = genai.Client(api_key=self.keys[self.current_key_index])

    def _rotate_key(self):
        if len(self.keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.keys)
            print(f"Switching to API Key index {self.current_key_index}")
            self._init_client()
            return True
        return False

    def _generate_json(self, contents: Any) -> dict:
        max_retries = 3 + len(self.keys)
        base_delay = 2

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config={
                        'response_mime_type': 'application/json'
                    }
                )

                text = response.text.replace('```json', '').replace('```', '').strip()
                return json.loads(text)
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    print(f"Gemini Rate Limit (429) hit on Key index {self.current_key_index}")

                    if self._rotate_key():
                        time.sleep(1)
                        continue

                    if attempt < max_retries - 1:
                        sleep_time = base_delay * (2 ** attempt)
                        print(f"Retrying in {sleep_time}s...")
                        time.sleep(sleep_time)
                        continue

                raise

        raise RuntimeError("Gemini request failed after retries")

    def predict_transaction_details(self, description: str, expenses_list: List[str]) -> dict:
        """
        Extracts Payee, Narration and predicts Account from description.
        Returns: {
            "payee": str,
            "narration": str,
            "account": str
        }
        """
        accounts_str = "\n".join(expenses_list)

        prompt = f"""
        You are a smart accounting assistant.
        Analyze the following transaction description to extract the Payee (Merchant/Who) and the Narration (What), and select the best Account.

        Rules:
        1. **Payee**: The merchant, shop, person, or organization.
        2. **Narration**: The item bought, activity, or category.
        3. **Account**: Select the SINGLE best fit from the provided list.

        Valid Accounts List:
        {accounts_str}

        User Description: "{description}"

        Return a JSON object with keys: "payee", "narration", "account".
        """

        try:
            return self._generate_json(prompt)
        except Exception as e:
            print(f"Gemini API Error: {e}")
            return {"payee": "", "narration": description, "account": "Expenses:Unknown"}

    def extract_image_transaction(self, image_bytes: bytes, mime_type: str, default_currency: str, caption: str = "") -> dict:
        """Extract raw factual transaction fields from an image."""
        today = date.today().isoformat()
        prompt = f"""
        Extract one transaction from this payment or bill details screenshot.

        Return exactly one JSON object using these keys:
        "date", "payee", "receiver_name", "narration", "order_amount", "actual_amount",
        "discount_amount", "currency", "payment_method", "category", "tx_id",
        "direction", "transaction_time", "notes", "confidence", "needs_review".

        Rules:
        1. Prefer the actual paid or received amount for "actual_amount", and keep the sign shown in the screenshot if there is one.
        1.1. Put the full visible payment/transaction timestamp in "transaction_time" when present, for example "2026-06-30 12:34:56".
        2. If there is an order amount before discounts, put it in "order_amount".
        3. If there is a visible discount, coupon, red packet, or instant reduction amount, put it in "discount_amount" as a positive number.
        4. If the screenshot includes both a merchant label and a receiver full name, keep both.
        5. If the image is an Alipay bill details page, map:
           - 商品说明 -> narration
           - 收款方全称 -> receiver_name
           - 付款方式 -> payment_method
           - 账单分类 -> category
           - 订单号 -> tx_id
           - Set "direction" to "支出" or "收入" if the screenshot makes it clear.
        6. If the image is a WeChat bill details page, map:
           - 交易类型 -> category
           - 商品 / 转账说明 / 备注 -> narration
           - 收款方 / 对方 -> payee or receiver_name
           - 付款方式 / 支付方式 / 入账方式 -> payment_method
           - 微信单号 / 商户单号 / 交易单号 -> tx_id
           - 收支方向 or the signed amount -> direction
        7. Use "{default_currency}" if the currency is not shown.
        8. If year is missing, infer it from today's date: {today}.
        9. Keep strings short and factual. Do not infer accounts.
        10. If any key cannot be determined, use an empty string for text fields or null for numeric fields.
        11. Set "needs_review" to true if the screenshot is cropped, blurry, or ambiguous.

        Optional user caption:
        {caption}
        """

        try:
            return self._generate_json([
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt
            ])
        except Exception as exc:
            print(f"Gemini image extraction failed, falling back to OCR: {exc}")
            try:
                return self.ocr_extractor.extract_transaction(
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    default_currency=default_currency,
                    caption=caption,
                )
            except Exception as ocr_exc:
                raise RuntimeError(f"Gemini 图片识别失败，OCR 回退也失败: {ocr_exc}") from exc
