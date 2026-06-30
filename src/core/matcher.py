from typing import Tuple, List, Optional
from src.core.loader import BeanLoader
from src.utils.ai_client import GeminiClient
import re

class HybridMatcher:
    def __init__(self, loader: BeanLoader, ai_client: GeminiClient, local_aliases: dict):
        self.loader = loader
        self.ai_client = ai_client
        self.local_expenses_map = local_aliases

    def resolve_asset(self, raw_input: str) -> Tuple[str, List[str]]:
        """
        Looking for asset alias in the input.
        Returns: (remaining_text, [possible_accounts])
        """
        # Split by spaces OR Chinese/English commas to identify tokens
        tokens = re.split(r'[，,\s]+', raw_input.strip())
        if not tokens:
            return raw_input, []
            
        last_word = tokens[-1]
        accounts = self.loader.get_accounts_by_alias(last_word)
        if accounts:
            # Asset found! Remove it from description
            if raw_input.strip().endswith(last_word):
                # Remove suffix
                new_text = raw_input.strip()[: -len(last_word)].strip()
                # Remove trailing punctuation like comma if left over
                new_text = re.sub(r'[，,]$', '', new_text).strip()
                return new_text, accounts
                
        return raw_input, []

    def get_all_aliases(self, prefixes=('Expenses:', 'Income:')) -> List[Tuple[str, str]]:
        """
        Returns a list of (alias, account) tuples that match the given prefixes.
        Sources: local_settings AND bean_file metadata.
        """
        candidates = []
        
        # 1. Local Map
        for alias, account in self.local_expenses_map.items():
            if any(account.startswith(p) for p in prefixes):
                candidates.append((alias, account))
                
        # 2. Loader Map
        for alias, account_list in self.loader.account_aliases.items():
            for account in account_list:
                if any(account.startswith(p) for p in prefixes):
                    candidates.append((alias, account))
        
        # Deduplicate by (alias, account) pair
        # Use set of tuples
        unique_set = set(candidates)
        # Sort by alias length (shorter first) then alphabetical
        unique = sorted(list(unique_set), key=lambda x: (len(x[0]), x[0]))
        return unique

    def predict_details(self, description: str) -> dict:
        """
        Layer 1: Local map (Exact match or simple regex) -> Returns simple dict
        Layer 2: AI Prediction -> Returns structured Payee/Narration/Account
        """
        # Layer 0: Prefix Heuristic (Deterministic)
        # Check if the description STARTS with a known alias (e.g. "晚饭 稻禾风")
        first_token = description.split(' ')[0]
        prefix_account = None
        
        # Check Settings Aliases
        for keyword, account in self.local_expenses_map.items():
            if keyword == first_token:
                prefix_account = account
                break
                
        # Check Bean Aliases (if not found in settings)
        if not prefix_account:
             for alias, accounts in self.loader.account_aliases.items():
                 if alias == first_token:
                     target_accs = [a for a in accounts if a.startswith("Expenses:") or a.startswith("Income:")]
                     if target_accs:
                         prefix_account = target_accs[0]
                         break
        
        if prefix_account:
            # Deterministic Match Found!
            narration = first_token
            payee = description[len(first_token):].strip()
            return {
                "payee": payee,
                "narration": narration,
                "account": prefix_account
            }

        # Layer 1: Local map (Exact match or simple regex) -> Returns simple dict
        # This handles cases like "放松" -> "Expenses:Entertainment:Sex" defined in .bean
        bean_aliases = self.loader.get_accounts_by_alias(description)
        # Filter for Expense/Income only
        valid_bean_aliases = [
            acc for acc in bean_aliases 
            if acc.startswith('Expenses:') or acc.startswith('Income:')
        ]
        
        local_account_match = None
        if valid_bean_aliases:
            local_account_match = valid_bean_aliases[0]

        # Layer 2: Local Map (Substring) AND Bean Aliases (Substring)
        if not local_account_match:
            # Check Settings Aliases
            for keyword, account in self.local_expenses_map.items():
                if keyword.lower() in description.lower():
                    local_account_match = account
                    break
            
            # Check Bean Aliases (if still not found)
            if not local_account_match:
                 for alias, accounts in self.loader.account_aliases.items():
                     if alias.lower() in description.lower():
                         # Filter for Expense/Income
                         target_accs = [a for a in accounts if a.startswith("Expenses:") or a.startswith("Income:")]
                         if target_accs:
                             local_account_match = target_accs[0]
                             break

        # Layer 2: AI
        # Filter for only Expenses/Income accounts to send to AI
        candidate_accounts = self.loader.get_expenses_and_income()
        ai_result = self.ai_client.predict_transaction_details(description, candidate_accounts)
        
        # Merge results
        if local_account_match:
            ai_result['account'] = local_account_match
            # We trust the local rule for categorization, but trust AI for parsing text
            
        return ai_result

    def parse_positional(self, text: str) -> Optional[dict]:
        """
        Strict positional parsing:
        Format: Payee Narration [Discount Name] [Discount Amount] Real Amount Asset Alias
        
        Logic:
        1. Tokenize input.
        2. Last token -> Asset Alias (must be valid).
        3. Second to last token -> Real Amount (must be number).
        4. Check for Discount Amount (number) preceding Real Amount.
           - If found, the token before it is Discount Name.
        5. Everything before (Real Amount / Discount Name) is Payee + Narration.
           - We arbitrarily split Payee/Narration? Or just return raw description?
           - User said "Payee Narration ...", so first token is Payee, rest is Narration.
        """
        # Split by spaces/commas using same logic as resolve_asset
        # But here we want to preserve order strictly
        tokens = re.split(r'[，,\s]+', text.strip())
        tokens = [t for t in tokens if t] # Filter empty
        
        if len(tokens) < 3:
            return None

        # 1. Identify Asset (Last Token)
        asset_alias = tokens[-1]
        asset_candidates = self.loader.get_accounts_by_alias(asset_alias)
        if not asset_candidates:
            return None # Last token MUST be a valid asset alias
        
        selected_asset = asset_candidates[0]
        
        # 2. Identify Expense Amount Block
        # Search backwards for the amount block
        remaining_end_index = -1
        
        # Block variables
        real_amount = 0.0
        currency = None
        converted_amount = None
        converted_currency = None
        
        # Helper to check if string is float
        def is_float(s):
            try:
                float(s)
                return True
            except ValueError:
                return False

        # Pattern: Amount1 Currency1 @@ Amount2 Currency2 (5 tokens)
        # Check tokens[-6:-1] vs tokens[-1] (Asset)
        # We start checking from end of tokens excluding Asset
        # Index of Asset is -1. So check tokens ending at -2.
        
        found_amount_block = False
        
        # Try Scheme A: A1 C1 @@ A2 C2 (5 tokens)
        # tokens[i], tokens[i+1], tokens[i+2], tokens[i+3], tokens[i+4]
        # Ends at -2
        if len(tokens) >= 6 and tokens[-4] == '@@':
             # ... A1 C1 @@ A2 C2 Asset
             # indices: -6 -5 -4 -3 -2 -1
             if is_float(tokens[-6]) and is_float(tokens[-3]):
                 # Confirmed
                 real_amount = float(tokens[-6])
                 currency = tokens[-5]
                 converted_amount = float(tokens[-3])
                 converted_currency = tokens[-2]
                 remaining_end_index = -6
                 found_amount_block = True
                 
        # Try Scheme B: Amount Currency (2 tokens)
        # ... A1 C1 Asset
        # indices: -3 -2 -1
        if not found_amount_block and len(tokens) >= 3:
            if is_float(tokens[-3]):
                 real_amount = float(tokens[-3])
                 currency = tokens[-2] # Assume this is currency if not @@
                 # But need to distinguish from Discount Amount.
                 # If user enters "Food 100", tokens are "Food", "100", "UnknownAsset" -> fails Asset check
                 # Here we passed Asset check.
                 # "Data 100 USD Cash" -> tokens: Data, 100, USD, Cash. -1=Cash. -2=USD. -3=100.
                 remaining_end_index = -3
                 found_amount_block = True
                 
        # Try Scheme C: Amount (1 token) - Legacy
        # ... A1 Asset
        # indices: -2 -1
        if not found_amount_block and len(tokens) >= 2:
             if is_float(tokens[-2]):
                 real_amount = float(tokens[-2])
                 remaining_end_index = -2
                 found_amount_block = True
        
        if not found_amount_block:
            return None

        # 3. Check for Discount (Optional)
        # Look at token before remaining_end_index
        discount_info = None
        
        # Discount pattern: DiscName DiscAmount (2 tokens)
        # Check tokens[remaining_end_index-2 : remaining_end_index]
        # Need at least 2 more tokens before amount block
        if remaining_end_index - 2 >= -len(tokens): # or just calculate absolute index
             # Absolute index of remaining_end_index start
             abs_end = len(tokens) + remaining_end_index
             # We need indices abs_end-1 (Amount) and abs_end-2 (Name)
             if abs_end >= 2:
                 d_amount_token = tokens[abs_end-1]
                 d_name_token = tokens[abs_end-2]
                 
                 if is_float(d_amount_token):
                     disc_amount = float(d_amount_token)
                     
                     # Check DiscName
                     disc_accounts = []
                     
                     lookup_token = d_name_token
                     # User Rule: If @@ (converted_currency) is present, "优惠" implies "优惠hk"
                     if converted_currency and lookup_token == "优惠":
                         lookup_token = "优惠hk"
                     
                     # 1. Check Settings
                     if lookup_token in self.local_expenses_map:
                         disc_accounts.append(self.local_expenses_map[lookup_token])
                         
                     # 2. Check Bean Loader (always check to find ambiguity)
                     d_acc_list = self.loader.get_accounts_by_alias(lookup_token)
                     if d_acc_list:
                         disc_accounts.extend(d_acc_list)
                     
                     # Deduplicate while preserving order
                     seen = set()
                     unique_accounts = []
                     for acc in disc_accounts:
                         if acc not in seen:
                             unique_accounts.append(acc)
                             seen.add(acc)
                     
                     if unique_accounts:
                         discount_info = (unique_accounts, disc_amount)
                         remaining_end_index -= 2

        # 4. Payee and Narration
        front_tokens = tokens[:remaining_end_index]
        if not front_tokens:
            return None
            
        payee = front_tokens[0]
        if len(front_tokens) > 1:
            narration = " ".join(front_tokens[1:])
        else:
            narration = payee 

        return {
            "payee": payee,
            "narration": narration,
            "amount": real_amount,
            "currency": currency,
            "converted_amount": converted_amount,
            "converted_currency": converted_currency,
            "asset": selected_asset,
            "discount_info": discount_info,
            "raw_asset_token": asset_alias
        }

    def parse_amounts(self, text: str) -> Tuple[str, List[float]]:
        """Extracts all amounts from text."""
        import re
        # Find all numbers (integer or float) embedded in text
        matches = re.findall(r'(\d+(?:\.\d+)?)', text)
        
        amounts = []
        for m in matches:
            try:
                amounts.append(float(m))
            except ValueError:
                pass
                
        clean_text = re.sub(r'\d+(?:\.\d+)?', '', text).strip()
        # Clean up punctuation (commas) left over
        clean_text = re.sub(r'[，,]', ' ', clean_text)
        # Clean up double spaces
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        return clean_text, amounts
