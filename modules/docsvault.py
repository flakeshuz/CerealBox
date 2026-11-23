from __future__ import annotations

import base64

from .base import Module


class DocsVaultModule(Module):
    def create_view(self, parent):
        from .docsvault_ui import DocsVaultView
        return DocsVaultView(parent, self)
    name = "docsvault"
    title = "Document Vault"
    show_in_navigation = True

    def setup(self):
        # All documents stored under the 'docsvault.docs' collection
        self.docs = self.col("docs")
        self._legacy_docs = self.col("docsvault.docs")

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
        if self.docs:
            document = self.docs.get(doc_id)
            if document:
                return document
        return self._legacy_docs.get(doc_id) if self._legacy_docs else None

    def list_documents(self) -> list:
        documents = {str(document.get("id") or document.get("name")): document
                     for document in (self.docs.all() if self.docs else [])}
        for document in (self._legacy_docs.all() if self._legacy_docs else []):
            key = str(document.get("id") or document.get("name"))
            documents.setdefault(key, document)
        return list(documents.values())

    def delete_document(self, doc_id: str) -> bool:
        deleted = bool(self.docs.delete(doc_id)) if self.docs else False
        legacy_deleted = False
        if self._legacy_docs:
            for document in self._legacy_docs.all():
                if str(document.get("id")) == doc_id or str(document.get("name")) == doc_id:
                    legacy_deleted = bool(
                        self._legacy_docs.delete(str(document.get("name")))
                    ) or legacy_deleted
        return deleted or legacy_deleted
