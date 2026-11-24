"""Notes PyQt6 view."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTextEdit,
    QVBoxLayout, QWidget,
)


class NotesView(QWidget):
    def __init__(self, parent: QWidget, mod):
        super().__init__(parent)
        self.mod = mod
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 24)
        header = QHBoxLayout()
        title = QLabel("Notes")
        title.setStyleSheet("font-size: 20px; font-weight: bold")
        header.addWidget(title)
        header.addStretch()
        add = QPushButton("Add note")
        add.setProperty("primary", True)
        add.clicked.connect(self.add)
        header.addWidget(add)
        root.addLayout(header)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search notes")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        root.addWidget(self.search)
        self.listbox = QListWidget()
        self.listbox.itemDoubleClicked.connect(self.edit)
        root.addWidget(self.listbox)
        actions = QHBoxLayout()
        edit = QPushButton("Edit")
        edit.clicked.connect(self.edit_selected)
        delete = QPushButton("Delete")
        delete.setProperty("danger", True)
        delete.clicked.connect(self.delete_selected)
        actions.addWidget(edit)
        actions.addWidget(delete)
        actions.addStretch()
        root.addLayout(actions)
        self.empty = QLabel()
        self.empty.setObjectName("muted")
        self.empty.setWordWrap(True)
        root.addWidget(self.empty)
        self.refresh()

    def refresh(self):
        self.listbox.clear()
        query = self.search.text().strip().casefold()
        visible = 0
        for n in (self.mod.list_notes() or []):
            title = str(n.get("title", "Untitled"))
            content = str(n.get("content", ""))
            if query and query not in f"{title} {content}".casefold():
                continue
            item = QListWidgetItem(title)
            item.setData(1, str(n.get("id", "")))
            item.setToolTip(content)
            self.listbox.addItem(item)
            visible += 1
        if visible:
            self.empty.setText("")
        elif query:
            self.empty.setText(f"No notes match “{query}”.")
        else:
            self.empty.setText("No notes yet. Add one to get started.")

    def add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Note")
        layout = QVBoxLayout(dlg)
        title = QLineEdit()
        content = QTextEdit()
        layout.addWidget(QLabel("Title"))
        layout.addWidget(title)
        layout.addWidget(QLabel("Content"))
        layout.addWidget(content)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            value = title.text().strip()
            if value:
                self.mod.add_note(value, content.toPlainText())
                self.refresh()

    def _selected_id(self):
        item = self.listbox.currentItem()
        return item.data(1) if item else None

    def edit_selected(self):
        item = self.listbox.currentItem()
        if item:
            self.edit(item)

    def edit(self, item):
        note_id = item.data(1)
        note = self.mod.get_note(note_id)
        if not note:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Note")
        layout = QVBoxLayout(dlg)
        title = QLineEdit(str(note.get("title", "")))
        content = QTextEdit(str(note.get("content", "")))
        layout.addWidget(QLabel("Title"))
        layout.addWidget(title)
        layout.addWidget(QLabel("Content"))
        layout.addWidget(content)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            value = title.text().strip()
            if not value:
                QMessageBox.warning(self, "Note title required", "Give the note a title.")
                return
            self.mod.update_note(note_id, value, content.toPlainText())
            self.refresh()

    def delete_selected(self):
        item = self.listbox.currentItem()
        if not item:
            return
        answer = QMessageBox.question(
            self,
            "Delete note",
            f"Delete “{item.text()}”? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.mod.delete_note(item.data(1))
            self.refresh()
