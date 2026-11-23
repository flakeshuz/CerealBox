from __future__ import annotations

import base64

from .base import Module


class DocsVaultModule(Module):
    def create_view(self, parent):
        from .docsvault_ui import DocsVaultView
        return DocsVaultView(parent, self)
    name = "docsvault"
    title = "Document Vault"

    def setup(self):
        # All documents stored under the 'docsvault.docs' collection
        self.docs = self.col("docsvault.docs")

    def services(self):
        return {
            "put_document": self.put_document,
            "get_document": self.get_document,
            "list_documents": self.list_documents,
            "delete_document": self.delete_document,
        }

    def put_document(self, doc_id: str, name: str, data: bytes, notes: str = "") -> dict:
        payload = {
            "id": doc_id,
            "name": name,
            "data": base64.b64encode(data).decode("ascii"),
            "notes": notes,
        }
        self.docs.put(doc_id, payload)
        return payload

    def get_document(self, doc_id: str) -> dict | None:
        return self.docs.get(doc_id) if self.docs else None

    def list_documents(self) -> list:
        return self.docs.all() if self.docs else []

    def delete_document(self, doc_id: str) -> bool:
        return self.docs.delete(doc_id)
