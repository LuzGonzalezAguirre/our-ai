from time import monotonic
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
        self._cache: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            tuple[float, dict],
        ] = {}

    @property
    def configured(self) -> bool:
        return bool(
            settings.action_tracker_enabled
            and self.base_url
            and self.token
        )

    def _cache_key(
        self,
        path: str,
        params: dict | None,
    ) -> tuple[str, tuple[tuple[str, str], ...]]:
        normalized = tuple(
            sorted(
                (str(key), str(value))
                for key, value in (params or {}).items()
            )
        )
        return path, normalized

    async def _get(
        self,
        path: str,
        params: dict | None = None,
        *,
        cache_seconds: float = 0.0,
    ) -> dict:
        if not self.configured:
            raise ActionTrackerError(
                "La integración con Action Tracker no está configurada."
            )

        cache_key = self._cache_key(
            path,
            params,
        )

        if cache_seconds > 0:
            cached = self._cache.get(cache_key)

            if cached:
                cached_at, data = cached

                if monotonic() - cached_at < cache_seconds:
                    return data

                self._cache.pop(
                    cache_key,
                    None,
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
            data = response.json()
        except ValueError as exc:
            raise ActionTrackerError(
                "Action Tracker respondió con datos no válidos."
            ) from exc

        if cache_seconds > 0:
            self._cache[cache_key] = (
                monotonic(),
                data,
            )

        return data

    async def health(self) -> dict:
        return await self._get(
            "/api/ai/health"
        )

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
            cache_seconds=(
                settings.action_tracker_cache_seconds
            ),
        )
        return data.get("actions", [])

    async def get_action(self, code: str) -> dict:
        safe_code = quote(code, safe="")
        return await self._get(
            f"/api/ai/actions/{safe_code}",
            cache_seconds=(
                settings.action_tracker_cache_seconds
            ),
        )

    async def list_npi_projects(self) -> list[dict]:
        data = await self._get(
            "/api/ai/npi",
            cache_seconds=(
                settings.action_tracker_cache_seconds
            ),
        )
        return data.get("projects", [])

    async def get_npi(self, code: str) -> dict:
        safe_code = quote(code, safe="")
        return await self._get(
            f"/api/ai/npi/{safe_code}",
            cache_seconds=(
                settings.action_tracker_cache_seconds
            ),
        )

    async def pending_approvals(self) -> list[dict]:
        data = await self._get(
            "/api/ai/pending-approvals",
            cache_seconds=(
                settings.action_tracker_cache_seconds
            ),
        )
        return data.get("approvals", [])

    async def events(self, days: int = 90) -> list[dict]:
        data = await self._get(
            "/api/ai/events",
            params={"days": days},
            cache_seconds=(
                settings.action_tracker_cache_seconds
            ),
        )
        return data.get("events", [])


action_tracker = ActionTrackerConnector()
