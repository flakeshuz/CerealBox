# Passwords module scaffold
from ..base import Module


class PasswordsModule(Module):
    name = "passwords"
    title = "Passwords"

    def setup(self):
        self.passwords = self.col("passwords")

    def services(self):
        return {
            "store_credential": self.store_credential,
            "get_credential": self.get_credential,
            "list_credentials": self.list_credentials,
        }

    def create_view(self, parent):
        from .ui import PasswordsView
        return PasswordsView(parent, self)

    def store_credential(self, key: str, value: str) -> dict:
        rec = {"key": key, "value": value}
        self.passwords.put(key, rec)
        return rec

    def get_credential(self, key: str) -> dict | None:
        return self.passwords.get(key)

    def list_credentials(self) -> list:
        return self.passwords.all() or []
