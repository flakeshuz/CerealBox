from __future__ import annotations

import base64

from ..core.ids import new_id
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


def decoded_text(document: dict) -> str:
    data = document.get("data", "")
    if not isinstance(data, str):
        return ""
    try:
        return base64.b64decode(data, validate=True).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return ""


def document_bytes(document: dict) -> int:
    data = document.get("data", "")
    if not isinstance(data, str):
        return 0
    try:
        return len(base64.b64decode(data, validate=True))
    except (ValueError, UnicodeDecodeError):
        try:
            return len(data.encode("utf-8"))
        except UnicodeEncodeError:
            return 0


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class DocsVaultView(QWidget):
    def __init__(self, parent, module):
        super().__init__(parent)
        self.module = module
        self._documents: dict[str, dict] = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Document Vault"))
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search documents")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search documents")
        self.search.textChanged.connect(self._refresh)
        search_row.addWidget(self.search)
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Name", "Size"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.itemSelectionChanged.connect(self._show_selected)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select a document to preview its text.")
        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.preview)
        splitter.setSizes([330, 470])
        layout.addLayout(search_row)
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        add_button = QPushButton("Add document")
        add_button.setProperty("primary", True)
        add_button.clicked.connect(self._add)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh)
        delete_button = QPushButton("Delete")
        delete_button.setProperty("danger", True)
        delete_button.clicked.connect(self._delete)
        self.delete_button = delete_button
        buttons.addWidget(add_button)
        buttons.addWidget(refresh_button)
        buttons.addWidget(delete_button)
        layout.addLayout(buttons)
        self.status = QLabel()
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self._refresh()

    def _refresh(self):
        self.tree.clear()
        self._documents = {}
        query = self.search.text().strip().casefold()
        try:
            documents = self.module.list_documents()
        except Exception as exc:
            self.status.setText(f"Could not load documents: {exc}")
            return
        visible = 0
        for document in documents:
            name = str(document.get("name", "Untitled"))
            if query and query not in name.casefold():
                continue
            document_id = str(document.get("id") or name)
            self._documents[document_id] = document
            item = QTreeWidgetItem([name, format_bytes(document_bytes(document))])
            item.setData(0, 1, document_id)
            self.tree.addTopLevelItem(item)
            visible += 1
        if not documents:
            self.status.setText("No documents yet. Add one to get started.")
            self.preview.clear()
        elif not visible:
            self.status.setText(f"No documents match “{self.search.text().strip()}”.")
            self.preview.clear()
        else:
            self.status.setText(f"{visible} document{'s' if visible != 1 else ''}")
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _show_selected(self):
        items = self.tree.selectedItems()
        if not items:
            self.preview.clear()
            self.delete_button.setEnabled(False)
            return
        document_id = items[0].data(0, 1)
        document = self._documents.get(document_id)
        if document is None:
            self.preview.clear()
            self.delete_button.setEnabled(False)
            return
        self.preview.setPlainText(decoded_text(document))
        self.delete_button.setEnabled(True)

    def _add(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Document")
        form = QFormLayout(dialog)
        name_input = QLineEdit(dialog)
        data_input = QPlainTextEdit(dialog)
        form.addRow("Name", name_input)
        form.addRow("Data (text)", data_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_input.text().strip()
            data = data_input.toPlainText().encode("utf-8")
            if not name:
                QMessageBox.warning(self, "Document name required", "Give the document a name.")
                return
            try:
                document_id = new_id("doc")
                self.module.put_document(document_id, name, data)
                self._refresh()
                self.status.setText(f"Added “{name}”.")
            except Exception as exc:
                self.status.setText(f"Could not add document: {exc}")

    def _delete(self):
        items = self.tree.selectedItems()
        if not items:
            return
        document_id = items[0].data(0, 1)
        name = items[0].text(0)
        answer = QMessageBox.question(
            self,
            "Delete document",
            f"Delete “{name}”? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            if self.module.delete_document(document_id):
                self._refresh()
                self.status.setText(f"Deleted “{name}”.")
            else:
                self.status.setText(f"Could not delete “{name}”.")
        except Exception as exc:
            self.status.setText(f"Could not delete document: {exc}")
