from beancount import loader
from typing import Dict, List, Tuple

class BeanLoader:
    def __init__(self, bean_file_path: str):
        self.bean_file_path = bean_file_path
        self.entries = []
        self.errors = []
        self.options = {}
        self.account_aliases: Dict[str, List[str]] = {}  # alias -> [account_names]
        self.all_accounts: List[str] = []

    def load(self):
        """Loads the beancount file and extracts metadata."""
        self.entries, self.errors, self.options = loader.load_file(self.bean_file_path)
        self._extract_accounts_and_aliases()
    
    def _extract_accounts_and_aliases(self):
        """Iterates through open directives to find aliases."""
        self.account_aliases.clear()
        self.all_accounts.clear()

        for entry in self.entries:
            if entry.__class__.__name__ == "Open":
                account = entry.account
                self.all_accounts.append(account)
                
                # Check for metadata
                if entry.meta:
                    aliases = []
                    
                    if 'alias' in entry.meta:
                        raw_alias = entry.meta['alias']
                        # Handle comma separated list
                        if isinstance(raw_alias, str):
                            aliases.extend([a.strip() for a in raw_alias.split(',')])
                        else:
                             # Fallback if it's somehow not a string, though usually is
                             aliases.append(str(raw_alias))
                                
                    # Also support standard 'name' if useful
                    if 'name' in entry.meta:
                         aliases.append(entry.meta['name'])
                    
                    for a in aliases:
                        if a:
                            key = a.lower()
                            if key not in self.account_aliases:
                                self.account_aliases[key] = []
                            self.account_aliases[key].append(account)

    def get_accounts_by_alias(self, alias: str) -> List[str]:
        return self.account_aliases.get(alias.lower(), [])

    def get_assets_and_liabilities(self) -> List[str]:
        return [acc for acc in self.all_accounts 
                if acc.startswith("Assets:") or acc.startswith("Liabilities:")]

    def get_expenses_and_income(self) -> List[str]:
        return [acc for acc in self.all_accounts 
                if acc.startswith("Expenses:") or acc.startswith("Income:")]
