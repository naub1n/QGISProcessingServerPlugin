"""Ajoute « Exécuter sur le serveur ... » à la fenêtre d'exécution d'un algorithme Processing.

La fenêtre (processing.gui.AlgorithmDialog) n'offre pas de point d'extension : on enveloppe
son __init__ pour y ajouter un bouton à menu, placé après « Exécuter comme processus de lot ... ».
"""
import functools
import json

from qgis.core import Qgis, QgsMessageLog, QgsProcessingContext, QgsProject
from qgis.PyQt.QtWidgets import QDialogButtonBox, QMenu, QMessageBox, QPushButton

from ..api.client import ApiClient
from ..core.settings import ServerSettings
from .model_publish import make_context_action
from .schedule_dialog import ScheduleCreateDialog
from .widgets import confirm_prerequisites, run_api

LOG_TAG = "QGIS Processing Server Manager"
BUTTON_PROPERTY = "_psm_server_button"


def serialize_parameters(algorithm, parameters: dict) -> dict:
    """Convertit les paramètres de la fenêtre en JSON (les couches deviennent leur source)."""
    context = QgsProcessingContext()
    context.setProject(QgsProject.instance())
    result = {}
    for name, value in parameters.items():
        definition = algorithm.parameterDefinition(name)
        try:
            value = definition.valueAsJsonObject(value, context)
        except Exception:  # version de QGIS sans valueAsJsonObject, ou type non géré
            pass
        result[name] = value
    return json.loads(json.dumps(result, default=str))


class AlgorithmDialogIntegration:
    def __init__(self):
        self._dialog_class = None
        self._original_init = None
        self._context_actions = []

    def install(self) -> bool:
        """Retourne False si le plugin Processing n'est pas encore importable."""
        if self._dialog_class is not None:
            return True
        try:
            from processing.gui.AlgorithmDialog import AlgorithmDialog
        except ImportError:
            return False

        original = AlgorithmDialog.__init__
        integration = self

        @functools.wraps(original)
        def patched(dialog, *args, **kwargs):
            original(dialog, *args, **kwargs)
            try:
                integration.add_button(dialog)
            except Exception as e:  # ne jamais empêcher l'ouverture de la fenêtre
                QgsMessageLog.logMessage(f"Bouton serveur non ajouté : {e}", LOG_TAG, Qgis.Warning)

        AlgorithmDialog.__init__ = patched
        self._dialog_class = AlgorithmDialog
        self._original_init = original

        from processing.gui.ProviderActions import ProviderContextMenuActions

        self._context_actions = [make_context_action()]
        ProviderContextMenuActions.registerProviderContextMenuActions(self._context_actions)
        return True

    def uninstall(self) -> None:
        if self._context_actions:
            from processing.gui.ProviderActions import ProviderContextMenuActions

            ProviderContextMenuActions.deregisterProviderContextMenuActions(self._context_actions)
            self._context_actions = []
        if self._dialog_class is not None:
            self._dialog_class.__init__ = self._original_init
            self._dialog_class = None
            self._original_init = None

    # ---------- bouton ----------

    def add_button(self, dialog) -> None:
        if getattr(dialog, "in_place", False) or dialog.algorithm() is None:
            return
        if dialog.property(BUTTON_PROPERTY):
            return  # sous-classe appelant plusieurs fois l'init de base
        dialog.setProperty(BUTTON_PROPERTY, True)

        button = QPushButton("Exécuter sur le serveur ...")
        menu = QMenu(button)
        menu.addAction("Exécuter une seule fois").triggered.connect(lambda: self.run_once(dialog))
        menu.addAction("Planifier").triggered.connect(lambda: self.schedule(dialog))
        button.setMenu(menu)
        # Même rôle que « Exécuter comme processus de lot » et ajouté après lui : s'affiche à sa droite.
        dialog.buttonBox().addButton(button, QDialogButtonBox.ResetRole)

    # ---------- actions ----------

    def _collect(self, dialog):
        algorithm = dialog.algorithm()
        try:
            parameters = dialog.createProcessingParameters()
            if not parameters and dialog.mainWidget() is not None:
                # certaines versions de QGIS (modèles) renvoient {} depuis la fenêtre : on interroge le panneau
                parameters = dialog.mainWidget().createProcessingParameters()
        except Exception as e:
            QMessageBox.warning(dialog, "Paramètres invalides", str(e))
            return None
        if not parameters and algorithm.parameterDefinitions():
            QgsMessageLog.logMessage(
                f"Aucun paramètre collecté pour {algorithm.id()} alors que l'algorithme en déclare "
                f"{len(algorithm.parameterDefinitions())}.",
                LOG_TAG,
                Qgis.Warning,
            )
            answer = QMessageBox.question(
                dialog,
                "Aucun paramètre",
                "Aucun paramètre n'a pu être lu depuis la fenêtre : le job serait soumis sans paramètres.\n\nContinuer ?",
            )
            if answer != QMessageBox.Yes:
                return None
        return algorithm.id(), serialize_parameters(algorithm, parameters)

    def run_once(self, dialog) -> None:
        collected = self._collect(dialog)
        if collected is None:
            return
        algorithm_id, parameters = collected
        client = ApiClient(ServerSettings.load())
        if not confirm_prerequisites(dialog, client, algorithm_id):
            return
        result = run_api(dialog, client.create_job, algorithm_id, parameters)
        if result is None:
            return
        job_id = result.get("jobID") or result.get("jobId") or result.get("id") or result.get("_location", "")
        QMessageBox.information(
            dialog,
            "Job créé",
            f"« {algorithm_id} » soumis au serveur.\nIdentifiant : {job_id or '(non renvoyé)'}\n\n"
            "Suivez son avancement dans QGIS Processing Server Manager.",
        )

    def schedule(self, dialog) -> None:
        collected = self._collect(dialog)
        if collected is None:
            return
        algorithm_id, parameters = collected
        ScheduleCreateDialog(
            ApiClient(ServerSettings.load()), dialog, algorithm=algorithm_id, parameters=parameters
        ).exec()
