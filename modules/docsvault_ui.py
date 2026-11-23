from __future__ import annotations

import base64

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DocsVaultView(QWidget):
    def __init__(self, parent, module):
        super().__init__(parent)
        self.module = module

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Document Vault"))
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Name", "Size (bytes)"])
        layout.addWidget(self.tree)

        buttons = QHBoxLayout()
        buttons.addStretch()
        add_button = QPushButton("Add")
        add_button.clicked.connect(self._add)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh)
        buttons.addWidget(add_button)
        buttons.addWidget(refresh_button)
        layout.addLayout(buttons)
        self._refresh()

    def _refresh(self):
        self.tree.clear()
        for document in (self.module.docs.all() or []):
            name = document.get("name", "")
            data = document.get("data", "")
            self.tree.addTopLevelItem(QTreeWidgetItem([name, str(len(data))]))

    def _add(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Document")
        form = QFormLayout(dialog)
        name_input = QLineEdit(dialog)
        data_input = QLineEdit(dialog)
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
            name = name_input.text()
            data = data_input.text().encode()
            if name:
                self.module.docs.put(
                    name,
                    {
                        "id": f"doc_{name}",
                        "name": name,
                        "data": base64.b64encode(data).decode(),
                    },
                )
                self._refresh()
