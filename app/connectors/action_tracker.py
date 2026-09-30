import asyncio
import json
import logging
from pathlib import Path
from time import monotonic, time
from urllib.parse import quote

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT_DIR / ".cache"
CACHE_FILE = CACHE_DIR / "action_tracker.json"


class ActionTrackerError(RuntimeError):
    pass


class ActionTrackerConnector:
    def __init__(self) -> None:
        self.base_url = settings.action_tracker_base_url.rstrip("/")
        self.token = settings.action_tracker_token
        self.timeout = settings.action_tracker_timeout_seconds
        self._cache: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            tuple[float, float, dict],
        ] = {}
        self._persisted_keys: set[
            tuple[str, tuple[tuple[str, str], ...]]
        ] = set()
        self._refresh_tasks: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            asyncio.Task,
        ] = {}
        self._persist_lock = asyncio.Lock()

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

    def load_persistent_cache(self) -> int:
        if not CACHE_FILE.exists():
            return 0

        try:
            payload = json.loads(
                CACHE_FILE.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            ValueError,
            TypeError,
        ):
            logger.exception(
                "No se pudo cargar el snapshot local de Action Tracker."
            )
            return 0

        loaded = 0
        now_wall = time()

        for entry in payload.get("entries", []):
            try:
                saved_at = float(entry["saved_at"])
                age = max(
                    now_wall - saved_at,
                    0.0,
                )

                if age > settings.action_tracker_persist_seconds:
                    continue

                path = str(entry["path"])
                params = {
                    str(key): str(value)
                    for key, value in (
                        entry.get("params") or {}
                    ).items()
                }
                data = entry["data"]
                cache_key = self._cache_key(
                    path,
                    params,
                )

                self._cache[cache_key] = (
                    monotonic(),
                    saved_at,
                    data,
                )
                self._persisted_keys.add(
                    cache_key
                )
                loaded += 1

            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

        if loaded:
            logger.info(
                "Action Tracker: %s snapshot(s) local(es) cargado(s).",
                loaded,
            )

        return loaded

    def _snapshot_payload(self) -> dict:
        entries = []

        for (
            path,
            normalized_params,
        ), (
            _cached_at,
            saved_at,
            data,
        ) in self._cache.items():
            entries.append({
                "path": path,
                "params": dict(
                    normalized_params
                ),
                "saved_at": saved_at,
                "data": data,
            })

        return {
            "version": 1,
            "entries": entries,
        }

    def _write_snapshot(
        self,
        payload: dict,
    ) -> None:
        CACHE_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
        temp_file = CACHE_FILE.with_suffix(
            ".tmp"
        )
        temp_file.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        temp_file.replace(
            CACHE_FILE
        )

    async def _persist_cache(self) -> None:
        async with self._persist_lock:
            payload = self._snapshot_payload()

            try:
                await asyncio.to_thread(
                    self._write_snapshot,
                    payload,
                )
            except OSError:
                logger.exception(
                    "No se pudo guardar el snapshot local de Action Tracker."
                )

    async def _request(
        self,
        path: str,
        params: dict | None = None,
    ) -> dict:
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

    async def _refresh_cache(
        self,
        cache_key: tuple[str, tuple[tuple[str, str], ...]],
        path: str,
        params: dict | None,
    ) -> None:
        try:
            data = await self._request(
                path,
                params,
            )
            now_wall = time()
            self._cache[cache_key] = (
                monotonic(),
                now_wall,
                data,
            )
            self._persisted_keys.discard(
                cache_key
            )
            await self._persist_cache()

        except ActionTrackerError:
            logger.exception(
                "No se pudo refrescar el caché de Action Tracker para %s.",
                path,
            )
        finally:
            self._refresh_tasks.pop(
                cache_key,
                None,
            )

    def _schedule_refresh(
        self,
        cache_key: tuple[str, tuple[tuple[str, str], ...]],
        path: str,
        params: dict | None,
    ) -> None:
        current = self._refresh_tasks.get(
            cache_key
        )

        if current and not current.done():
            return

        task = asyncio.create_task(
            self._refresh_cache(
                cache_key,
                path,
                dict(params or {}),
            )
        )
        self._refresh_tasks[cache_key] = task

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
            cached = self._cache.get(
                cache_key
            )

            if cached:
                cached_at, _saved_at, data = cached

                if cache_key in self._persisted_keys:
                    self._schedule_refresh(
                        cache_key,
                        path,
                        params,
                    )
                    return data

                age = monotonic() - cached_at

                if age < cache_seconds:
                    return data

                if age < settings.action_tracker_stale_seconds:
                    self._schedule_refresh(
                        cache_key,
                        path,
                        params,
                    )
                    return data

                self._cache.pop(
                    cache_key,
                    None,
                )

        current_refresh = self._refresh_tasks.get(
            cache_key
        )

        if current_refresh and not current_refresh.done():
            await current_refresh

            cached = self._cache.get(
                cache_key
            )
            if cached:
                return cached[2]

        data = await self._request(
            path,
            params,
        )

        if cache_seconds > 0:
            now_wall = time()
            self._cache[cache_key] = (
                monotonic(),
                now_wall,
                data,
            )
            self._persisted_keys.discard(
                cache_key
            )
            await self._persist_cache()

        return data

    async def warm_cache(self) -> None:
        if not self.configured:
            return

        tasks = [
            self.list_actions(
                open_only=False,
            ),
            self.list_npi_projects(),
            self.pending_approvals(),
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        failures = sum(
            1
            for result in results
            if isinstance(result, Exception)
        )

        if failures:
            logger.warning(
                "Action Tracker warmup terminó con %s fallo(s).",
                failures,
            )
        else:
            logger.info(
                "Action Tracker cache precargado."
            )

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
