import json

from qgis.gui import QgsAuthConfigSelect
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..api.client import ApiClient, ApiError
from ..core.settings import ServerSettings
from .job_dialog import JobCreateDialog
from .schedule_dialog import ScheduleCreateDialog
from .widgets import JsonEdit, fill_table, first, make_table, run_api

AUTO_REFRESH_MS = 10_000


class ListDetailTab(QWidget):
    """Onglet générique : barre d'actions, tableau et panneau de détail JSON."""

    def __init__(self, headers: list, new_label: str, main: "MainDialog", sortable: bool = True):
        super().__init__()
        self.main = main
        layout = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.refresh_button = QPushButton("Actualiser")
        self.refresh_button.clicked.connect(self.refresh)
        self.new_button = QPushButton(new_label)
        self.new_button.clicked.connect(self.create)
        self.auto = QCheckBox(f"Actualisation auto ({AUTO_REFRESH_MS // 1000} s)")
        self.auto.toggled.connect(self.toggle_auto)
        bar.addWidget(self.refresh_button)
        bar.addWidget(self.new_button)
        bar.addStretch()
        bar.addWidget(self.auto)
        layout.addLayout(bar)

        self.table = make_table(headers, sortable)
        self.table.itemSelectionChanged.connect(self.show_detail)
        self.detail = JsonEdit(read_only=True)
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setSizes([300, 200])
        layout.addWidget(split)

        self.timer = QTimer(self)
        self.timer.timeout.connect(lambda: self.refresh(silent=True))

    def toggle_auto(self, on: bool) -> None:
        self.timer.start(AUTO_REFRESH_MS) if on else self.timer.stop()

    def selected_raw(self):
        rows = self.table.selectionModel().selectedRows()
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole) if rows else None

    def selected_key(self):
        raw = self.selected_raw()
        return self.key_of(raw) if raw else None

    def refresh(self, silent: bool = False) -> None:
        previous = self.selected_key()
        try:
            items = self.fetch(silent)
        except ApiError as e:
            if silent:
                self.auto.setChecked(False)
            QMessageBox.critical(self, "QGIS Processing Server Manager", str(e))
            return
        self.table.blockSignals(True)
        fill_table(self.table, [(self.cells(i), i) for i in items])
        self.table.blockSignals(False)
        for r in range(self.table.rowCount()):
            self.decorate_row(r, self.table.item(r, 0).data(Qt.UserRole))
        if previous is not None:
            for r in range(self.table.rowCount()):
                raw = self.table.item(r, 0).data(Qt.UserRole)
                if self.key_of(raw) == previous:
                    self.table.selectRow(r)
                    break

    def decorate_row(self, row: int, item: dict) -> None:
        """Point d'extension : ajoute des widgets (boutons) à une ligne."""

    # À surcharger
    def fetch(self, silent: bool) -> list:
        raise NotImplementedError

    def cells(self, item: dict) -> list:
        raise NotImplementedError

    def key_of(self, item: dict):
        raise NotImplementedError

    def show_detail(self) -> None:
        raise NotImplementedError

    def create(self) -> None:
        raise NotImplementedError


class JobsTab(ListDetailTab):
    def __init__(self, main):
        super().__init__(["ID", "Process", "Statut", "Créé", "Terminé", "Progression"], "Nouveau job…", main)

    def fetch(self, silent):
        return self.main.client().list_jobs()

    def key_of(self, job):
        return first(job, "jobID", "jobId", "id")

    def cells(self, job):
        return [
            self.key_of(job),
            first(job, "processID", "process_id"),
            job.get("status"),
            first(job, "created", "created_at"),
            first(job, "finished", "finished_at"),
            job.get("progress"),
        ]

    def show_detail(self):
        job_id = self.selected_key()
        if job_id is None:
            return
        data = run_api(self, self.main.client().get_job, str(job_id))
        if data is not None:
            self.detail.set_json(data)

    def create(self):
        if JobCreateDialog(self.main.client(), self).exec():
            self.refresh()


class SchedulesTab(ListDetailTab):
    ACTIONS_COLUMN = 6

    def __init__(self, main):
        # Pas de tri : les boutons de la colonne Actions sont des widgets de cellule
        # qui ne suivent pas les lignes lors d'un tri.
        super().__init__(
            ["ID", "Process", "Déclencheur", "Arguments", "Activée", "Prochaine exécution", "Actions"],
            "Nouvelle planification…",
            main,
            sortable=False,
        )

    def fetch(self, silent):
        return self.main.client().list_schedules()

    def key_of(self, schedule):
        return first(schedule, "id", "schedule_id")

    def cells(self, s):
        args = s.get("trigger_args")
        return [
            self.key_of(s),
            s.get("process_id"),
            s.get("trigger"),
            json.dumps(args, ensure_ascii=False) if args is not None else "",
            s.get("enabled"),
            first(s, "next_run_time", "next_run"),
            "",
        ]

    def decorate_row(self, row, schedule):
        schedule_id = str(self.key_of(schedule))
        enabled = schedule.get("enabled")

        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(2, 0, 2, 0)
        for label, handler, active in (
            ("Activer", self.enable, enabled is not True),
            ("Désactiver", self.disable, enabled is not False),
            ("Supprimer", self.delete, True),
        ):
            button = QPushButton(label)
            button.setEnabled(active)
            button.clicked.connect(lambda _=False, h=handler, sid=schedule_id: h(sid))
            layout.addWidget(button)
        self.table.setCellWidget(row, self.ACTIONS_COLUMN, box)
        self.table.resizeColumnToContents(self.ACTIONS_COLUMN)

    def _act(self, func, schedule_id: str) -> None:
        if run_api(self, lambda: (func(schedule_id), True)[1]):
            self.refresh()

    def enable(self, schedule_id):
        self._act(self.main.client().enable_schedule, schedule_id)

    def disable(self, schedule_id):
        self._act(self.main.client().disable_schedule, schedule_id)

    def delete(self, schedule_id):
        answer = QMessageBox.question(
            self, "Supprimer la planification", f"Supprimer définitivement la planification « {schedule_id} » ?"
        )
        if answer == QMessageBox.Yes:
            self._act(self.main.client().delete_schedule, schedule_id)

    def show_detail(self):
        schedule_id = self.selected_key()
        if schedule_id is None:
            return
        data = run_api(self, self.main.client().get_schedule, str(schedule_id))
        if data is not None:
            self.detail.set_json(data)

    def create(self):
        if ScheduleCreateDialog(self.main.client(), self).exec():
            self.refresh()


class ConnectionTab(QWidget):
    def __init__(self, main):
        super().__init__()
        self.main = main
        s = ServerSettings.load()
        form = QFormLayout(self)

        self.base_url = QLineEdit(s.base_url)
        self.base_url.setPlaceholderText("https://qgis.example.org")
        self.oapi_prefix = QLineEdit(s.oapi_prefix)
        self.schedules_prefix = QLineEdit(s.schedules_prefix)
        self.auth = QgsAuthConfigSelect()
        self.auth.setConfigId(s.auth_cfg)
        self.headers = QPlainTextEdit(s.extra_headers)
        self.headers.setPlaceholderText("Authorization: Bearer <jeton>\nCookie: nom=valeur")
        self.headers.setMaximumHeight(80)
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 600)
        self.timeout.setSuffix(" s")
        self.timeout.setValue(s.timeout_s)

        form.addRow("URL du serveur", self.base_url)
        form.addRow("Préfixe OGC API", self.oapi_prefix)
        form.addRow("Préfixe planifications", self.schedules_prefix)
        form.addRow("Authentification QGIS", self.auth)
        form.addRow("En-têtes additionnels", self.headers)
        form.addRow("Délai d'attente", self.timeout)

        hint = QLabel(
            "L'authentification est assurée par Traefik (OIDC). Créez dans QGIS une configuration "
            "d'authentification <b>OAuth2</b> (flux code d'autorisation, même fournisseur que Traefik) "
            "ou « Jeton / en-tête » : QGIS enverra le jeton <i>Bearer</i> avec chaque requête. "
            "À défaut, un en-tête <i>Authorization</i> ou <i>Cookie</i> peut être saisi ci-dessus."
        )
        hint.setWordWrap(True)
        form.addRow(hint)

        row = QHBoxLayout()
        save = QPushButton("Enregistrer")
        save.clicked.connect(self.save)
        test = QPushButton("Tester la connexion")
        test.clicked.connect(self.test)
        row.addWidget(save)
        row.addWidget(test)
        row.addStretch()
        form.addRow(row)

    def current(self) -> ServerSettings:
        return ServerSettings(
            base_url=self.base_url.text().strip(),
            oapi_prefix=self.oapi_prefix.text().strip() or "/oapi",
            schedules_prefix=self.schedules_prefix.text().strip() or "/schedules",
            auth_cfg=self.auth.configId(),
            extra_headers=self.headers.toPlainText(),
            timeout_s=self.timeout.value(),
        )

    def save(self) -> None:
        self.current().save()

    def test(self) -> None:
        self.save()
        jobs = run_api(self, ApiClient(self.current()).list_jobs, 1)
        if jobs is not None:
            QMessageBox.information(self, "Connexion", "Connexion et authentification réussies.")


class MainDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QGIS Processing Server Manager")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(900, 650)

        self.tabs = QTabWidget()
        self.jobs = JobsTab(self)
        self.schedules = SchedulesTab(self)
        self.connection = ConnectionTab(self)
        self.tabs.addTab(self.jobs, "Jobs")
        self.tabs.addTab(self.schedules, "Planifications")
        self.tabs.addTab(self.connection, "Connexion")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        QVBoxLayout(self).addWidget(self.tabs)

        if not ServerSettings.load().base_url:
            self.tabs.setCurrentWidget(self.connection)

    def client(self) -> ApiClient:
        return ApiClient(ServerSettings.load())

    def on_tab_changed(self, index: int) -> None:
        tab = self.tabs.widget(index)
        if isinstance(tab, ListDetailTab) and tab.table.rowCount() == 0:
            tab.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if ServerSettings.load().base_url:
            self.on_tab_changed(self.tabs.currentIndex())

    def closeEvent(self, event) -> None:
        self.jobs.auto.setChecked(False)
        self.schedules.auto.setChecked(False)
        super().closeEvent(event)
