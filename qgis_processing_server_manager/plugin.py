import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .gui.main_dialog import MainDialog
from .gui.processing_integration import AlgorithmDialogIntegration

MENU = "&QGIS Processing Server Manager"


class ProcessingServerManagerPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None
        self.integration = AlgorithmDialogIntegration()

    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), "icon.svg"))
        self.action = QAction(icon, "QGIS Processing Server Manager", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dialog)
        self.iface.addPluginToMenu(MENU, self.action)
        self.iface.addToolBarIcon(self.action)
        # Le plugin Processing peut ne pas être encore chargé : on réessaie à la fin de l'initialisation.
        if not self.integration.install():
            self.iface.initializationCompleted.connect(self.integration.install)

    def unload(self):
        try:
            self.iface.initializationCompleted.disconnect(self.integration.install)
        except TypeError:
            pass
        self.integration.uninstall()
        if self.action is not None:
            self.iface.removePluginMenu(MENU, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None

    def show_dialog(self):
        if self.dialog is None:
            self.dialog = MainDialog(self.iface.mainWindow())
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
