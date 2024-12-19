import json
import os
from typing import Dict, List, Optional

class UserManager:
    def __init__(self, data_file: str = "data/users.json"):
        self.data_file = data_file
        self.users: Dict[str, dict] = self._load_users()
        # Initialize owners list if not exists
        if not self._get_owners():
            owner_id = os.getenv("OWNER_ID")
            if owner_id:
                self._add_owner(owner_id)

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

    def _get_owners(self) -> List[str]:
        """Get list of owner IDs."""
        if "owners" not in self.users:
            self.users["owners"] = []
            self._save_users()
        return self.users["owners"]

    def _add_owner(self, user_id: str) -> None:
        """Add a user to owners list."""
        owners = self._get_owners()
        if str(user_id) not in owners:
            owners.append(str(user_id))
            self.users["owners"] = owners
            self._save_users()

    def _remove_owner(self, user_id: str) -> bool:
        """Remove a user from owners list."""
        owners = self._get_owners()
        user_id_str = str(user_id)
        if user_id_str in owners:
            owners.remove(user_id_str)
            self.users["owners"] = owners
            self._save_users()
            return True
        return False

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
        users_copy = self.users.copy()
        if "owners" in users_copy:
            del users_copy["owners"]
        return users_copy

    def is_user_active(self, user_id: int) -> bool:
        """Check if user exists and is not expired or limited"""
        user_id_str = str(user_id)
        if user_id_str not in self.users:
            return False

        user_data = self.users[user_id_str]
        access_limit = user_data.get("access_limit", 0)
        if access_limit <= 0:
            return False

        return True

    def add_owner(self, user_id: int) -> None:
        """Add a user as an owner."""
        self._add_owner(str(user_id))
        # Also ensure the user is whitelisted with no limits
        self.add_user(user_id, access_limit=None)

    def remove_owner(self, user_id: int) -> bool:
        """Remove a user from owners."""
        return self._remove_owner(str(user_id))

    def is_owner(self, user_id: int) -> bool:
        """Check if the user is an owner."""
        return str(user_id) in self._get_owners()

    def get_owners(self) -> List[int]:
        """Get list of all owners."""
        return [int(owner_id) for owner_id in self._get_owners()]
