"""Entrée « Publier le modèle sur le serveur ... » du menu contextuel des modèles (boîte à outils Processing)."""
import os
import tempfile

from qgis.core import QgsProcessingAlgorithm, QgsProcessingModelAlgorithm
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.utils import iface

from ..api.client import ApiClient
from ..core.settings import ServerSettings
from .widgets import run_api

TITLE = "Publier le modèle"


def model_to_xml(model: QgsProcessingModelAlgorithm) -> str:
    """Sérialise le modèle au format .model3 (XML)."""
    handle, path = tempfile.mkstemp(suffix=".model3")
    os.close(handle)
    try:
        if not model.toFile(path):
            raise RuntimeError("Impossible de sérialiser le modèle.")
        with open(path, encoding="utf-8") as f:
            return f.read()
    finally:
        os.remove(path)


def missing_algorithms(model: QgsProcessingModelAlgorithm, available: set) -> list:
    """Identifiants des algorithmes utilisés par le modèle et absents du worker."""
    used = {child.algorithmId() for child in model.childAlgorithms().values()}
    return sorted(used - available)


def publish_model(parent, model: QgsProcessingModelAlgorithm) -> None:
    client = ApiClient(ServerSettings.load())
    model_id = model.id()

    exists = run_api(parent, client.check_algorithm, model_id)
    if exists is None:
        return
    if exists.status == "ok":
        answer = QMessageBox.question(
            parent,
            TITLE,
            f"Le modèle « {model.displayName()} » existe déjà sur le serveur.\n\nLe remplacer ?",
        )
        if answer != QMessageBox.Yes:
            return

    available = run_api(parent, client.list_algorithm_ids)
    if available is None:
        return
    missing = missing_algorithms(model, available)
    if missing:
        QMessageBox.critical(
            parent,
            TITLE,
            "Algorithmes du modèle absents du serveur :\n- " + "\n- ".join(missing) + "\n\nPublication annulée.",
        )
        return

    try:
        xml = model_to_xml(model)
    except Exception as e:
        QMessageBox.critical(parent, TITLE, str(e))
        return
    if run_api(parent, client.publish_model, model.name(), xml) is None:
        return
    QMessageBox.information(parent, TITLE, f"Modèle « {model.displayName()} » publié sur le serveur.")


def make_context_action():
    """Crée l'action (import tardif : le plugin Processing peut ne pas être encore chargé)."""
    from processing.gui.ContextAction import ContextAction

    class PublishModelAction(ContextAction):
        def __init__(self):
            super().__init__()
            self.name = "Publier le modèle sur le serveur ..."

        def isEnabled(self):
            return isinstance(self.itemData, QgsProcessingAlgorithm) and self.itemData.provider().id() in (
                "model",
                "project",
            )

        def execute(self):
            publish_model(iface.mainWindow(), self.itemData)

    return PublishModelAction()
