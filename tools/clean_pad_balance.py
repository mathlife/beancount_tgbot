import os
import re

def clean_file(filepath):
    print(f"Cleaning {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    # Pattern: 2024-05-14 pad ... OR 2024-05-15 balance ... OR 2024-05-31 close ...
    # We look for lines starting with date, followed by 'pad', 'balance' or 'close'
    pattern = re.compile(r'^\d{4}-\d{2}-\d{2}\s+(pad|balance|close)\s+')

    removed_count = 0
    for line in lines:
        if pattern.match(line):
            removed_count += 1
            continue
        new_lines.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"  - Removed {removed_count} lines.")

def main():
    target_dir = 'data/accounts'
    if not os.path.exists(target_dir):
        print(f"Directory {target_dir} does not exist.")
        return

    for filename in os.listdir(target_dir):
        if filename.endswith('.bean'):
            clean_file(os.path.join(target_dir, filename))

if __name__ == '__main__':
    main()
