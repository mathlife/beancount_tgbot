import os

def clean_file(filepath):
    print(f"Cleaning {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    delete_block = False

    for line in lines:
        is_indented = line.startswith(' ') or line.startswith('\t')
        content_match = "deposit" in line.lower()

        if not is_indented:
            # New directive/top-level line
            if content_match:
                # Mark this block for deletion
                delete_block = True
                continue # Skip this line
            else:
                delete_block = False
                # Keep this line
                new_lines.append(line)
        else:
            # Indented line (metadata)
            if delete_block:
                # Skip because parent was deleted
                continue
            
            if content_match:
                # Skip because this specific line has "deposit" (e.g. alias: "Deposit")
                continue
            
            # Keep otherwise
            new_lines.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

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
