# GitHub Upload Instructions

Since `git` command execution failed in your terminal, here are the manual steps to upload your project.

## 1. Prepare Files (Done)
I have updated `.gitignore` to:
- **Ignore** `config/.env` (Secrets protections)
- **Ignore** `data/*.bean` (Privacy protection - checks out `data/` but ignores files inside except examples)
- **Ignore** `debug_*.py` (Cleanup)

## 2. Initialize Git (If you have Git installed)
Open your preferred terminal (Git Bash, PowerShell with Git) in `d:\TG_bot` and run:

```bash
git init
git add .
git commit -m "Initial commit: TG_bot with Gemini 2.0 and Multi-key support"
```

## 3. Create Repository on GitHub
1.  Go to [github.com/new](https://github.com/new).
2.  Repository Name: `tg_bot` (or your choice).
3.  Visibility: **Private** (Recommended).
4.  Do **not** initialize with README/gitignore (you already have them).
5.  Click "Create repository".

## 4. Push Code
Copy the commands shown on GitHub under "…or push an existing repository from the command line":

```bash
git remote add origin https://github.com/YOUR_USERNAME/tg_bot.git
git branch -M main
git push -u origin main
```

## Note on Data
By default, I excluded your financial data (`.bean` files) from Git to protect your privacy.
If you **want** to back up your data to the private repo, edit `.gitignore` and remove the line `data/` or add `!data/*.bean`.
