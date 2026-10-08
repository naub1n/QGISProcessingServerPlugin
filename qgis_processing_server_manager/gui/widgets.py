import json
from typing import Any, Callable

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QFontDatabase
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QMessageBox,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..api.client import ApiClient, ApiError

STATUS_LABEL = {"ok": "✔", "missing": "✘", "unknown": "?"}


class JsonEdit(QPlainTextEdit):
    def __init__(self, text: str = "", read_only: bool = False, parent: QWidget = None):
        super().__init__(parent)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.setReadOnly(read_only)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setPlainText(text)

    def set_json(self, data: Any) -> None:
        self.setPlainText(data if isinstance(data, str) else json.dumps(data, indent=2, ensure_ascii=False))

    def value(self, label: str, expect=dict, allow_empty: bool = False):
        """Parse le contenu. Lève ValueError avec un message lisible."""
        text = self.toPlainText().strip()
        if not text:
            if allow_empty:
                return None
            raise ValueError(f"{label} : champ vide.")
        try:
            data = json.loads(text)
        except ValueError as e:
            raise ValueError(f"{label} : JSON invalide ({e}).") from e
        if not isinstance(data, expect):
            raise ValueError(f"{label} : un objet JSON est attendu.")
        return data


def make_table(headers: list, sortable: bool = True) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.setSortingEnabled(sortable)
    return table


def fill_table(table: QTableWidget, rows: list) -> None:
    """rows : liste de listes de valeurs. La 1re colonne reçoit les données brutes en UserRole."""
    sorting = table.isSortingEnabled()
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for r, (cells, raw) in enumerate(rows):
        for c, value in enumerate(cells):
            item = QTableWidgetItem("" if value is None else str(value))
            if c == 0:
                item.setData(Qt.UserRole, raw)
            table.setItem(r, c, item)
    table.setSortingEnabled(sorting)
    table.resizeColumnsToContents()


def first(d: dict, *keys, default=None):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return default


def run_api(parent: QWidget, func: Callable, *args, **kwargs):
    """Exécute un appel API avec curseur d'attente ; affiche l'erreur et retourne None en cas d'échec."""
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        return func(*args, **kwargs)
    except ApiError as e:
        QMessageBox.critical(parent, "QGIS Processing Server Manager", str(e))
        return None
    finally:
        QApplication.restoreOverrideCursor()


def format_checks(results: list) -> str:
    return "\n".join(f"{STATUS_LABEL[r.status]} {r.label} — {r.message}" for r in results)


def confirm_prerequisites(parent: QWidget, client: ApiClient, algorithm: str) -> bool:
    """Vérifie algorithme / .model3 côté serveur. Retourne True si l'envoi peut continuer."""
    results = run_api(parent, client.check_prerequisites, algorithm)
    if results is None:
        return False
    if any(r.status == "missing" for r in results):
        QMessageBox.critical(
            parent, "Éléments manquants sur le serveur", format_checks(results) + "\n\nEnvoi annulé."
        )
        return False
    if any(r.status == "unknown" for r in results):
        answer = QMessageBox.question(
            parent,
            "Vérification impossible",
            format_checks(results) + "\n\nEnvoyer quand même ?",
        )
        return answer == QMessageBox.Yes
    return True
