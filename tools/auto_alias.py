import os
import re
import sys

def process_file(filepath):
    print(f"Processing {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    # Regex to capture open directive
    # Pattern: Date open AccountName Currency
    # Example: 2020-01-01 open Assets:Bank:CMB CNY
    # Group 1: Leading date + open
    # Group 2: Account Name
    # Group 3: Rest (Currency etc)
    open_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}\s+open\s+)([\w:]+)(.*)$')
    
    # Metadata line pattern to check if alias exists immediately after
    meta_pattern = re.compile(r'^\s+alias:')

    for i, line in enumerate(lines):
        new_lines.append(line)
        
        match = open_pattern.match(line)
        if match:
            # Found an open directive
            prefix = match.group(1)
            account_name = match.group(2)
            suffix = match.group(3)
            
            # Extract last segment
            last_segment = account_name.split(':')[-1]
            
            # Check if next line is already an alias
            if i + 1 < len(lines):
                next_line = lines[i+1]
                if meta_pattern.match(next_line):
                    # Alias likely exists (or at least some metadata), skip basic auto-add to avoid duplicates
                    # A more robust parser would check specifically for 'alias', but this is a heuristic script.
                    # If the user wants to enforce it even if other metadata exists, logic needs to be complex.
                    # As per request, we "add" it. Be safer to skip if *any* alias is present.
                    if 'alias:' in next_line:
                         continue

            # Construct alias line
            # Indentation standard is 2 spaces usually
            alias_line = f'  alias: "{last_segment}"\n'
            
            # Append immediately after the open directive
            new_lines.append(alias_line)
            print(f"  + Added alias '{last_segment}' for {account_name}")

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Done.")

def main():
    target_dir = 'data/accounts'
    if not os.path.exists(target_dir):
        print(f"Directory {target_dir} does not exist.")
        return

    for filename in os.listdir(target_dir):
        if filename.endswith('.bean'):
            process_file(os.path.join(target_dir, filename))

if __name__ == '__main__':
    main()
