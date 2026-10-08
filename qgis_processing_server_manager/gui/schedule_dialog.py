import json
import re

from qgis.PyQt.QtCore import QRegularExpression
from qgis.PyQt.QtGui import QRegularExpressionValidator
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from ..api.client import ApiClient
from .job_dialog import AlgorithmParametersForm
from .widgets import JsonEdit, confirm_prerequisites, run_api

SCHEDULE_ID_PATTERN = r"[A-Za-z0-9_-]+"  # ni espace ni caractère spécial

# Modèles d'arguments (déclencheurs de type APScheduler)
TRIGGER_TEMPLATES = {
    "cron": {"minute": "*/2"},
    "interval": {"minutes": 5},
    "date": {"run_date": "2030-01-01T00:00:00"},
}


class ScheduleCreateDialog(QDialog):
    def __init__(self, client: ApiClient, parent=None, algorithm: str = "", parameters: dict = None):
        super().__init__(parent)
        self.client = client
        self.setWindowTitle("Nouvelle planification")
        self.resize(560, 620)

        layout = QVBoxLayout(self)
        head = QFormLayout()
        self.schedule_id = QLineEdit()
        self.schedule_id.setValidator(QRegularExpressionValidator(QRegularExpression(SCHEDULE_ID_PATTERN)))
        self.schedule_id.setPlaceholderText("lettres, chiffres, _ et - uniquement")
        self.trigger = QComboBox()
        self.trigger.addItems(list(TRIGGER_TEMPLATES))
        self.trigger_args = JsonEdit(json.dumps(TRIGGER_TEMPLATES["cron"], indent=2))
        self.trigger_args.setMaximumHeight(90)
        self.enabled = QCheckBox("Activée")
        self.enabled.setChecked(True)
        head.addRow("Identifiant", self.schedule_id)
        head.addRow("Déclencheur", self.trigger)
        head.addRow("trigger_args (JSON)", self.trigger_args)
        head.addRow("", self.enabled)
        layout.addLayout(head)

        self.form = AlgorithmParametersForm(self, client)
        if algorithm:
            self.form.algorithm.setText(algorithm)
        if parameters is not None:
            self.form.parameters.set_json(parameters)
        layout.addLayout(self.form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Créer")
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._last_trigger = "cron"
        self.trigger.currentTextChanged.connect(self.on_trigger_changed)

    def on_trigger_changed(self, trigger: str) -> None:
        # Ne remplace les arguments que s'ils sont encore ceux du modèle précédent.
        try:
            untouched = self.trigger_args.value("trigger_args") == TRIGGER_TEMPLATES[self._last_trigger]
        except ValueError:
            untouched = False
        if untouched:
            self.trigger_args.set_json(TRIGGER_TEMPLATES[trigger])
        self._last_trigger = trigger

    def submit(self) -> None:
        try:
            schedule_id = self.schedule_id.text().strip()
            if not schedule_id:
                raise ValueError("Identifiant : champ vide.")
            if not re.fullmatch(SCHEDULE_ID_PATTERN, schedule_id):
                raise ValueError("Identifiant : lettres, chiffres, « _ » et « - » uniquement (ni espace ni caractère spécial).")
            trigger_args = self.trigger_args.value("trigger_args")
            algorithm, parameters = self.form.values()
        except ValueError as e:
            QMessageBox.warning(self, "Saisie invalide", str(e))
            return

        if not confirm_prerequisites(self, self.client, algorithm):
            return
        result = run_api(
            self,
            self.client.create_schedule,
            schedule_id,
            self.trigger.currentText(),
            trigger_args,
            algorithm,
            parameters,
            self.enabled.isChecked(),
        )
        if result is None:
            return
        QMessageBox.information(self, "Planification créée", f"Planification « {schedule_id} » créée.")
        self.accept()
