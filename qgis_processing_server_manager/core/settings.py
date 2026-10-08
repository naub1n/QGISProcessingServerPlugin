from dataclasses import dataclass

from qgis.core import QgsSettings

PREFIX = "QGISProcessingServerManager/"


@dataclass
class ServerSettings:
    base_url: str = ""
    oapi_prefix: str = "/oapi"
    schedules_prefix: str = "/schedules"
    auth_cfg: str = ""
    # Un en-tête par ligne, "Nom: valeur" (ex. Authorization: Bearer ..., Cookie: ...)
    extra_headers: str = ""
    timeout_s: int = 30

    @classmethod
    def load(cls) -> "ServerSettings":
        s = QgsSettings()
        d = cls()
        return cls(
            base_url=s.value(PREFIX + "base_url", d.base_url, type=str),
            oapi_prefix=s.value(PREFIX + "oapi_prefix", d.oapi_prefix, type=str),
            schedules_prefix=s.value(PREFIX + "schedules_prefix", d.schedules_prefix, type=str),
            auth_cfg=s.value(PREFIX + "auth_cfg", d.auth_cfg, type=str),
            extra_headers=s.value(PREFIX + "extra_headers", d.extra_headers, type=str),
            timeout_s=s.value(PREFIX + "timeout_s", d.timeout_s, type=int),
        )

    def save(self) -> None:
        s = QgsSettings()
        for key in ("base_url", "oapi_prefix", "schedules_prefix", "auth_cfg", "extra_headers", "timeout_s"):
            s.setValue(PREFIX + key, getattr(self, key))

    def parsed_headers(self) -> dict:
        headers = {}
        for line in self.extra_headers.splitlines():
            if ":" in line:
                name, value = line.split(":", 1)
                if name.strip():
                    headers[name.strip()] = value.strip()
        return headers
