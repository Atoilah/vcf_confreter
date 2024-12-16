import json
import os
from typing import Dict, List, Optional

class UserManager:
    def __init__(self, data_file: str = "data/users.json"):
        self.data_file = data_file
        self.users: Dict[str, dict] = self._load_users()

    def _load_users(self) -> Dict[str, dict]:
        """Load users from JSON file."""
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_users(self) -> None:
        """Save users to JSON file."""
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        with open(self.data_file, 'w') as f:
            json.dump(self.users, f, indent=4)

    def add_user(self, user_id: int, access_limit: Optional[int] = None) -> None:
        """Add a user to the whitelist."""
        self.users[str(user_id)] = {
            "access_limit": access_limit
        }
        self._save_users()

    def remove_user(self, user_id: int) -> bool:
        """Remove a user from the whitelist."""
        if str(user_id) in self.users:
            del self.users[str(user_id)]
            self._save_users()
            return True
        return False

    def is_whitelisted(self, user_id: int) -> bool:
        """Check if a user is whitelisted."""
        return str(user_id) in self.users

    def get_access_limit(self, user_id: int) -> Optional[int]:
        """Get user's access limit."""
        user = self.users.get(str(user_id))
        return user["access_limit"] if user else None

    def set_access_limit(self, user_id: int, limit: int) -> None:
        """Set user's access limit."""
        if str(user_id) in self.users:
            self.users[str(user_id)]["access_limit"] = limit
            self._save_users()

    def decrement_access_limit(self, user_id: int) -> None:
        """Decrement user's access limit."""
        user_id_str = str(user_id)
        if user_id_str in self.users and self.users[user_id_str]["access_limit"] is not None:
            self.users[user_id_str]["access_limit"] -= 1
            if self.users[user_id_str]["access_limit"] <= 0:
                self.users[user_id_str]["access_limit"] = 0
            self._save_users()

    def get_all_users(self) -> Dict[str, dict]:
        """Get all users and their limits."""
        return self.users.copy()
