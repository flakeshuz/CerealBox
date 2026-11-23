"""Health UI scaffold"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class HealthView(QWidget):
    def __init__(self, parent, mod):
        super().__init__(parent)
        self.mod = mod

        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(QLabel("Health"))
        heading.addStretch()
        add_button = QPushButton("Add appointment")
        add_button.clicked.connect(self.add_appointment)
        heading.addWidget(add_button)
        layout.addLayout(heading)

        lists = QHBoxLayout()
        self.appt_list = QListWidget()
        self.med_list = QListWidget()
        appointments = QVBoxLayout()
        appointments.addWidget(QLabel("Appointments"))
        appointments.addWidget(self.appt_list)
        medications = QVBoxLayout()
        medications.addWidget(QLabel("Medications"))
        medications.addWidget(self.med_list)
        lists.addLayout(appointments)
        lists.addLayout(medications)
        layout.addLayout(lists)
        self.refresh()

    def refresh(self):
        self._refresh_appointments()
        self._refresh_medications()

    def _refresh_appointments(self):
        self.appt_list.clear()
        for appointment in (self.mod.list_appointments() or []):
            self.appt_list.addItem(
                f"{appointment.get('title', '')} - {appointment.get('date', '')}"
            )

    def _refresh_medications(self):
        self.med_list.clear()
        for medication in (self.mod.list_medications() or []):
            self.med_list.addItem(
                f"{medication.get('name', '')} - {medication.get('dose', '')}"
            )

    def add_appointment(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add appointment")
        form = QFormLayout(dialog)
        title_input = QLineEdit(dialog)
        date_input = QLineEdit(dialog)
        form.addRow("Title", title_input)
        form.addRow("Date", date_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            title = title_input.text().strip()
            date = date_input.text().strip()
            if title and date:
                self.mod.add_appointment(title, date)
                self._refresh_appointments()
