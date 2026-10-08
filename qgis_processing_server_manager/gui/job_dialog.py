import json

from qgis.gui import QgsCollapsibleGroupBox
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..api.client import ApiClient
from .widgets import JsonEdit, confirm_prerequisites, format_checks, run_api

EXAMPLE_PARAMETERS = {
    "AUTH_CONFIG": "",
    "DATA": "",
    "FAIL_ON_ERROR": True,
    "METHOD": 0,
    "URL": "https://qgis.github.io/qgis-uni-navigation/logo.svg",
}


class AlgorithmParametersForm(QFormLayout):
    """Champs communs aux jobs et aux planifications : algorithme + paramètres."""

    def __init__(self, dialog: QDialog, client: ApiClient):
        super().__init__()
        self.dialog = dialog
        self.client = client
        self.algorithm = QLineEdit("native:httprequest")
        self.algorithm.setPlaceholderText("ex. native:httprequest ou model:mon_modele")
        self.check_button = QPushButton("Vérifier sur le serveur")
        self.check_button.clicked.connect(self.run_check)
        self.parameters = JsonEdit(json.dumps(EXAMPLE_PARAMETERS, indent=2))
        self.addRow("Algorithme", self.algorithm)
        self.addRow("", self.check_button)
        self.addRow("Paramètres (JSON)", self.parameters)

    def run_check(self) -> None:
        algorithm = self.algorithm.text().strip()
        if not algorithm:
            QMessageBox.warning(self.dialog, "Vérification", "Saisissez un algorithme.")
            return
        results = run_api(self.dialog, self.client.check_prerequisites, algorithm)
        if results is not None:
            QMessageBox.information(self.dialog, "Vérification serveur", format_checks(results))

    def values(self):
        algorithm = self.algorithm.text().strip()
        if not algorithm:
            raise ValueError("Algorithme : champ vide.")
        return algorithm, self.parameters.value("Paramètres")


class JobCreateDialog(QDialog):
    def __init__(self, client: ApiClient, parent=None):
        super().__init__(parent)
        self.client = client
        self.setWindowTitle("Nouveau job")
        self.resize(560, 560)

        layout = QVBoxLayout(self)
        self.form = AlgorithmParametersForm(self, client)
        layout.addLayout(self.form)

        advanced = QgsCollapsibleGroupBox("Options avancées")
        advanced.setCollapsed(True)
        adv_form = QFormLayout(advanced)
        self.outputs = JsonEdit("")
        self.outputs.setPlaceholderText('{"nom": {"format": {"mediaType": "..."}, "transmissionMode": ["value"]}}')
        self.outputs.setMaximumHeight(90)
        self.response = QComboBox()
        self.response.addItems(["(défaut serveur)", "raw", "document"])
        self.success_uri = QLineEdit()
        self.progress_uri = QLineEdit()
        self.failed_uri = QLineEdit()
        adv_form.addRow("Outputs (JSON)", self.outputs)
        adv_form.addRow("Response", self.response)
        adv_form.addRow("successUri", self.success_uri)
        adv_form.addRow("inProgressUri", self.progress_uri)
        adv_form.addRow("failedUri", self.failed_uri)
        layout.addWidget(advanced)

        self.result_label = QLabel()
        layout.addWidget(self.result_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Lancer le job")
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.created = None

    def submit(self) -> None:
        try:
            algorithm, parameters = self.form.values()
            outputs = self.outputs.value("Outputs", allow_empty=True)
        except ValueError as e:
            QMessageBox.warning(self, "Saisie invalide", str(e))
            return

        response = self.response.currentText()
        response = None if response.startswith("(") else response
        subscriber = {
            k: v
            for k, v in (
                ("successUri", self.success_uri.text().strip()),
                ("inProgressUri", self.progress_uri.text().strip()),
                ("failedUri", self.failed_uri.text().strip()),
            )
            if v
        }

        if not confirm_prerequisites(self, self.client, algorithm):
            return
        result = run_api(
            self, self.client.create_job, algorithm, parameters, outputs, response, subscriber or None
        )
        if result is None:
            return
        self.created = result
        job_id = result.get("jobID") or result.get("jobId") or result.get("id") or result.get("_location", "")
        QMessageBox.information(self, "Job créé", f"Job soumis au serveur.\nIdentifiant : {job_id or '(non renvoyé)'}")
        self.accept()
