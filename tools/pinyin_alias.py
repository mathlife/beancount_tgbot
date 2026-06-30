import os
import re
from pypinyin import lazy_pinyin, Style

def get_pinyin_initials(text):
    # Filter for Chinese characters primarily, or valid text
    # Strategy: convert entire string to initials
    # lazy_pinyin with FIRST_LETTER style
    initials = lazy_pinyin(text, style=Style.FIRST_LETTER)
    # Join and lower case
    return "".join(initials).lower()

def process_file(filepath):
    print(f"Processing {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    # Regex: 
    # 1. Open directive
    # 2. Capture alias line if it exists immediately after (to append)
    # Actually simpler to just parse line by line.

    open_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}\s+open\s+)([\w:]+)(.*)$')
    # Comment pattern: look for ; followed by text
    comment_pattern = re.compile(r';\s*([\u4e00-\u9fa5a-zA-Z0-9]+)')

    for i, line in enumerate(lines):
        new_lines.append(line)
        
        match = open_pattern.match(line)
        if match:
            # Check for comment in the suffix (group 3)
            suffix = match.group(3)
            comment_match = comment_pattern.search(suffix)
            
            if comment_match:
                chinese_text = comment_match.group(1)
                # Generate pinyin aliases
                # Strategy: 
                # 1. Full initials: "建设银行" -> "jsyh"
                # 2. Maybe first 2 chars? User example "Ping An" -> "pa"
                # Let's generate the Full Initials for now as it's deterministic.
                
                pinyin_alias = get_pinyin_initials(chinese_text)
                
                if not pinyin_alias or len(pinyin_alias) < 2:
                    continue

                # Check if next line is 'alias:'
                if i + 1 < len(lines):
                    next_line = lines[i+1]
                    if 'alias:' in next_line:
                        # Append to existing alias line
                        # Format: alias: "Existing, new"
                        # Extract existing
                        quote_match = re.search(r'"(.*)"', next_line)
                        if quote_match:
                            existing = quote_match.group(1)
                            # Avoid duplicates
                            if pinyin_alias not in existing.split(', '):
                                updated = f'{existing}, {pinyin_alias}'
                                # Modify the NEXT line in new_lines
                                # We haven't added next_line yet, it will be added in next iteration?
                                # No, we are in loop `lines`. We just appended `line` (the open directive).
                                # We need to MODIFY the next line when we get to it? 
                                # Easier to read-ahead or modify `lines` in place? 
                                # Better: Store pending modification?
                                pass

    # Refactored Approach: Read whole file, modify buffer.
    
    final_lines = []
    skip_next = False
    
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
            
        final_lines.append(line)
        
        match = open_pattern.match(line)
        if match:
            account_name = match.group(2)
            suffix = match.group(3)
            comment_match = comment_pattern.search(suffix)
            
            pinyin_to_remove = None
            pinyin_to_add = None
            
            if comment_match:
                 chinese_text = comment_match.group(1)
                 # Reconstruct the logic from previous run to identify what to remove
                 # Previous logic: lazy_pinyin on the WHOLE matched string
                 pinyin_to_remove = get_pinyin_initials(chinese_text)
                 
                 # New logic: First 2 chars only
                 if len(chinese_text) >= 2:
                     pinyin_to_add = get_pinyin_initials(chinese_text[:2])
                 else:
                     pinyin_to_add = pinyin_to_remove # fallback if short

            # Logic checks
            is_excluded = "Alipay" in account_name or "Wechat" in account_name
            
            # Look ahead for alias line
            if i + 1 < len(lines) and 'alias:' in lines[i+1]:
                next_line = lines[i+1]
                quote_match = re.search(r'"(.*)"', next_line)
                
                if quote_match:
                    existing_str = quote_match.group(1)
                    existing_list = [x.strip() for x in existing_str.split(',')]
                    
                    original_len = len(existing_list)
                    
                    # 1. Remove Bad
                    if pinyin_to_remove and pinyin_to_remove in existing_list:
                        # Be careful not to remove if it equals the 'good' one and we want to keep it?
                        # But simpler: Remove 'bad', then add 'good'.
                        # If bad == good, we effectively remove and re-add (idempotent).
                        # Exception: If we added `zfb` manually and `zfb` is calculated as bad?
                        # `Alipay` -> `zfb` (manual). `chinese_text` -> `支付宝` -> `zfb`.
                        # If we remove `zfb`, we lose the manual one too!
                        # User said "undo new added".
                        # How to distinguish manual `zfb` from script `zfb`? We can't easily.
                        # BUT, for Alipay/Wechat, the "Bad" one was `zfbwanghuiypu` (long) in some cases.
                        # `zfb` was manual.
                        # If comment was just `支付宝`, generated was `zfb`.
                        # If I remove `zfb`, I kill the manual one.
                        # SAFEGUARD: Don't remove alias if it looks like a "Generic" one we want to keep?
                        # OR: Only remove if length > 3? 
                        # user said: "revoke for alipay and wechat". 
                        # My previous script added `zfb` to `Assets:CN:Alipay:Lili` (; 支付宝wang...) -> `zfb` was added?
                        # No, `支付宝wang...` -> `zfbwang...`
                        # So removing `zfbwang...` is safe.
                        # What if comment was `; 支付宝` -> `zfb`.
                        # If I remove `zfb`, I clear the manual alias.
                        # Let's assume manual aliases are "precious".
                        # Hack: For Alipay/Wechat, ONLY remove if validly "weird" (long)? 
                        # Actually, user wants to revert my LAST action.
                        # My last action added `pinyin_to_remove`.
                        # If `pinyin_to_remove` == `zfb`, and existing had `zfb`.
                        # If I remove it, alias is gone.
                        # I will SKIP removal if the alias is `zfb`, `wx`, `wechat`, `weixin`.
                        
                        if pinyin_to_remove not in ['zfb', 'wx', 'weixin', 'wechat']:
                             existing_list.remove(pinyin_to_remove)
                             print(f"  - Removed '{pinyin_to_remove}' from {account_name}")

                    # 2. Add Good (If not excluded)
                    if not is_excluded and pinyin_to_add:
                        if pinyin_to_add not in existing_list:
                            existing_list.append(pinyin_to_add)
                            print(f"  + Added '{pinyin_to_add}' to {account_name}")
                            
                    # Reconstruct
                    if len(existing_list) != original_len or set(existing_list) != set([x.strip() for x in existing_str.split(',')]):
                        new_aliases = ", ".join(existing_list)
                        new_alias_line = f'  alias: "{new_aliases}"\n'
                        final_lines.append(new_alias_line)
                        skip_next = True
                    else:
                        pass # No change

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(final_lines)
    print("Done.")

def main():
    target_dir = 'data/accounts'
    if not os.path.exists(target_dir):
        return

    for filename in os.listdir(target_dir):
        if filename.endswith('.bean'):
            process_file(os.path.join(target_dir, filename))

if __name__ == '__main__':
    main()
