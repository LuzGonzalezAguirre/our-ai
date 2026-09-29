from urllib.parse import quote

import httpx

from app.core.config import settings


class ActionTrackerError(RuntimeError):
    pass


class ActionTrackerConnector:
    def __init__(self) -> None:
        self.base_url = settings.action_tracker_base_url.rstrip("/")
        self.token = settings.action_tracker_token
        self.timeout = settings.action_tracker_timeout_seconds

    @property
    def configured(self) -> bool:
        return bool(
            settings.action_tracker_enabled
            and self.base_url
            and self.token
        )

    async def _get(
        self,
        path: str,
        params: dict | None = None,
    ) -> dict:
        if not self.configured:
            raise ActionTrackerError(
                "La integración con Action Tracker no está configurada."
            )

        headers = {
            "X-AT-Token": self.token,
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                response = await client.get(
                    f"{self.base_url}{path}",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()

        except httpx.ConnectError as exc:
            raise ActionTrackerError(
                "No se pudo conectar con Action Tracker."
            ) from exc
        except httpx.TimeoutException as exc:
            raise ActionTrackerError(
                "Action Tracker tardó demasiado en responder."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise ActionTrackerError(
                "Action Tracker respondió con error "
                f"{exc.response.status_code}: {detail}"
            ) from exc

        try:
            return response.json()
        except ValueError as exc:
            raise ActionTrackerError(
                "Action Tracker respondió con datos no válidos."
            ) from exc

    async def health(self) -> dict:
        return await self._get("/api/ai/health")

    async def list_actions(
        self,
        *,
        open_only: bool = True,
        asignado: str | None = None,
        departamento: str | None = None,
        area: str | None = None,
        categoria: str | None = None,
        estado: str | None = None,
        limit: int = 500,
    ) -> list[dict]:
        params = {
            "open_only": "1" if open_only else "0",
            "limit": limit,
        }

        for key, value in {
            "asignado": asignado,
            "departamento": departamento,
            "area": area,
            "categoria": categoria,
            "estado": estado,
        }.items():
            if value:
                params[key] = value

        data = await self._get(
            "/api/ai/actions",
            params=params,
        )
        return data.get("actions", [])

    async def get_action(self, code: str) -> dict:
        safe_code = quote(code, safe="")
        return await self._get(
            f"/api/ai/actions/{safe_code}"
        )

    async def list_npi_projects(self) -> list[dict]:
        data = await self._get("/api/ai/npi")
        return data.get("projects", [])

    async def get_npi(self, code: str) -> dict:
        safe_code = quote(code, safe="")
        return await self._get(
            f"/api/ai/npi/{safe_code}"
        )

    async def pending_approvals(self) -> list[dict]:
        data = await self._get(
            "/api/ai/pending-approvals"
        )
        return data.get("approvals", [])

    async def events(self, days: int = 90) -> list[dict]:
        data = await self._get(
            "/api/ai/events",
            params={"days": days},
        )
        return data.get("events", [])


action_tracker = ActionTrackerConnector()
