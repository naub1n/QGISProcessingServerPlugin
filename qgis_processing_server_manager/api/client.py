import json
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import quote, urlencode

from qgis.core import QgsBlockingNetworkRequest
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from ..core.settings import ServerSettings

PROCESS_ID = "qgis"  # process unique, non modifiable


class ApiError(Exception):
    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass
class CheckResult:
    """Résultat d'une vérification côté serveur.

    status: "ok" (présent), "missing" (absent) ou "unknown" (vérification impossible).
    """

    label: str
    status: str
    message: str = ""


class ApiClient:
    """Client HTTP synchrone. L'authentification (Traefik OIDC) est portée par la
    configuration d'authentification QGIS (``auth_cfg``) et/ou des en-têtes personnalisés."""

    def __init__(self, settings: ServerSettings):
        self.settings = settings

    # ---------- bas niveau ----------

    def _url(self, prefix: str, path: str, params: Optional[dict] = None) -> str:
        base = self.settings.base_url.strip().rstrip("/")
        if not base:
            raise ApiError("L'URL du serveur n'est pas configurée (onglet Connexion).")
        url = f"{base}/{prefix.strip('/')}/{path.lstrip('/')}".rstrip("/")
        if params:
            url += "?" + urlencode({k: v for k, v in params.items() if v not in (None, "")})
        return url

    def _oapi(self, path: str, params: Optional[dict] = None) -> str:
        return self._url(self.settings.oapi_prefix, path, params)

    def _schedules(self, path: str = "", params: Optional[dict] = None) -> str:
        return self._url(self.settings.schedules_prefix, path, params)

    def _request(self, method: str, url: str, payload: Any = None, raise_on_http_error: bool = True):
        """Retourne (status_http, en-têtes, corps JSON décodé ou texte)."""
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"Accept", b"application/json")
        for name, value in self.settings.parsed_headers().items():
            req.setRawHeader(name.encode(), value.encode())
        if hasattr(req, "setTransferTimeout"):
            req.setTransferTimeout(self.settings.timeout_s * 1000)

        blocking = QgsBlockingNetworkRequest()
        if self.settings.auth_cfg:
            blocking.setAuthCfg(self.settings.auth_cfg)

        if method == "GET":
            blocking.get(req, forceRefresh=True)
        elif method == "POST":
            req.setRawHeader(b"Content-Type", b"application/json")
            body = json.dumps(payload).encode("utf-8") if payload is not None else b""
            blocking.post(req, QByteArray(body))
        elif method == "DELETE":
            blocking.deleteResource(req)
        else:
            raise ValueError(method)

        reply = blocking.reply()
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) or 0
        headers = {bytes(k).decode().lower(): bytes(reply.rawHeader(k)).decode() for k in reply.rawHeaderList()}
        text = bytes(reply.content()).decode("utf-8", errors="replace")

        if status == 0:
            raise ApiError(f"Connexion impossible : {reply.errorString()}", 0, text)
        # Traefik OIDC redirige vers le fournisseur d'identité quand la session est absente.
        if status in (301, 302, 303, 307, 308) or (
            status == 200 and "text/html" in headers.get("content-type", "")
        ):
            raise ApiError(
                "Authentification requise : le serveur a renvoyé une redirection / page HTML "
                "(Traefik OIDC). Vérifiez la configuration d'authentification.",
                status,
                text,
            )

        try:
            data = json.loads(text) if text.strip() else None
        except ValueError:
            data = text

        if raise_on_http_error and status >= 400:
            detail = data.get("detail") or data.get("description") or data if isinstance(data, dict) else text
            raise ApiError(f"HTTP {status} : {detail}", status, text)
        return status, headers, data

    # ---------- jobs ----------

    def list_jobs(self, limit: int = 100) -> list:
        _, _, data = self._request("GET", self._oapi("jobs", {"limit": limit}))
        if isinstance(data, dict):
            data = data.get("jobs", [])
        return data if isinstance(data, list) else []

    def get_job(self, job_id: str) -> Any:
        return self._request("GET", self._oapi(f"jobs/{quote(job_id, safe='')}"))[2]

    def create_job(
        self,
        algorithm: str,
        parameters: dict,
        outputs: Optional[dict] = None,
        response: Optional[str] = None,
        subscriber: Optional[dict] = None,
    ) -> dict:
        body: dict = {"inputs": {"algorithm": algorithm, "parameters": parameters}}
        if outputs:
            body["outputs"] = outputs
        if response:
            body["response"] = response
        if subscriber:
            body["subscriber"] = subscriber
        status, headers, data = self._request("POST", self._oapi(f"processes/{PROCESS_ID}/execution"), body)
        result = data if isinstance(data, dict) else {"response": data}
        result.setdefault("_status", status)
        if "location" in headers:
            result.setdefault("_location", headers["location"])
        return result

    # ---------- planifications ----------

    def list_schedules(self) -> list:
        _, _, data = self._request("GET", self._schedules())
        if isinstance(data, dict):
            data = data.get("schedules", [])
        return data if isinstance(data, list) else []

    def get_schedule(self, schedule_id: str) -> Any:
        return self._request("GET", self._schedules(quote(schedule_id, safe="")))[2]

    def create_schedule(
        self,
        schedule_id: str,
        trigger: str,
        trigger_args: dict,
        algorithm: str,
        parameters: dict,
        enabled: bool = True,
    ) -> Any:
        body = {
            "id": schedule_id,
            "process_id": PROCESS_ID,
            "trigger": trigger,
            "trigger_args": trigger_args,
            "inputs": {"algorithm": algorithm, "parameters": parameters},
            "enabled": enabled,
        }
        return self._request("POST", self._schedules(), body)[2]

    def enable_schedule(self, schedule_id: str) -> Any:
        return self._request("POST", self._schedules(f"{quote(schedule_id, safe='')}/enable"))[2]

    def disable_schedule(self, schedule_id: str) -> Any:
        return self._request("POST", self._schedules(f"{quote(schedule_id, safe='')}/disable"))[2]

    def delete_schedule(self, schedule_id: str) -> Any:
        return self._request("DELETE", self._schedules(quote(schedule_id, safe="")))[2]

    # ---------- vérifications côté serveur ----------
    # Contrat : voir docs/server-checks.md. Le serveur répond toujours 200 avec un
    # champ booléen "exists" ; toute autre réponse signifie que la vérification est
    # indisponible (statut "unknown").

    def _check(self, label: str, path: str) -> CheckResult:
        try:
            _, _, data = self._request("GET", self._oapi(path))
        except ApiError as e:
            return CheckResult(label, "unknown", f"Vérification indisponible ({e})")
        if isinstance(data, dict) and isinstance(data.get("exists"), bool):
            if data["exists"]:
                return CheckResult(label, "ok", "Présent sur le serveur")
            return CheckResult(label, "missing", "Absent du serveur")
        return CheckResult(label, "unknown", "Réponse inattendue du serveur")

    def check_algorithm(self, algorithm_id: str) -> CheckResult:
        return self._check(f"Algorithme {algorithm_id}", f"worker/algorithms/{quote(algorithm_id, safe=':')}")

    def list_algorithm_ids(self) -> set:
        """Identifiants des algorithmes disponibles sur le worker (GET /worker/algorithms)."""
        _, _, data = self._request("GET", self._oapi("worker/algorithms"))
        if isinstance(data, dict):
            data = data.get("algorithms", [])
        ids = set()
        for item in data if isinstance(data, list) else []:
            alg_id = item.get("id") if isinstance(item, dict) else item
            if isinstance(alg_id, str):
                ids.add(alg_id)
        return ids

    def publish_model(self, name: str, model3_xml: str) -> Any:
        """Publie un modèle sur le worker (POST /worker/models)."""
        return self._request("POST", self._oapi("worker/models"), {"name": name, "model3": model3_xml})[2]

    def check_prerequisites(self, algorithm_id: str) -> list:
        """Vérifie l'algorithme (les modèles ``model:<nom>`` sont inclus dans le registre)."""
        return [self.check_algorithm(algorithm_id)]
