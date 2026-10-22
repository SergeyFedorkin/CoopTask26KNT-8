"""Клиент расписания ВШЭ (RUZ): https://ruz.hse.ru/api/..."""
import asyncio
from dataclasses import dataclass
from datetime import date

import aiohttp

BASE_URL = "https://ruz.hse.ru/api"


@dataclass
class Lesson:
    day: str          # YYYY-MM-DD
    begin: str        # HH:MM
    end: str          # HH:MM
    title: str
    kind: str = ""    # лекция / семинар / ...
    room: str = ""
    lecturer: str = ""
    url: str = ""     # ссылка на онлайн-пару
    manual: bool = False


class RuzError(Exception):
    pass


def _parse_lesson(item: dict) -> Lesson:
    return Lesson(
        day=str(item.get("date", "")).replace(".", "-"),
        begin=item.get("beginLesson") or "",
        end=item.get("endLesson") or "",
        title=(item.get("discipline") or "Без названия").strip(),
        kind=(item.get("kindOfWork") or "").strip(),
        room=(item.get("auditorium") or "").strip(),
        lecturer=(item.get("lecturer_title") or item.get("lecturer") or "").strip(),
        url=item.get("url1") or "",
    )


class Ruz:
    def __init__(self, proxy: str | None = None, verify_ssl: bool = True):
        self.proxy = proxy
        self.ssl = verify_ssl
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20),
            headers={"User-Agent": "Mozilla/5.0 (diary-bot)", "Accept": "application/json"},
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    async def _get(self, path: str, params: dict) -> list:
        try:
            async with self._session.get(BASE_URL + path, params=params, proxy=self.proxy, ssl=self.ssl) as r:
                if r.status != 200:
                    raise RuzError(f"HTTP {r.status}")
                data = await r.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            raise RuzError(str(e) or type(e).__name__) from e
        if not isinstance(data, list):
            raise RuzError("неожиданный ответ сервера")
        return data

    async def search(self, term: str) -> list[dict]:
        """Поиск группы по названию или студента по email (@edu.hse.ru)."""
        kind = "student" if "@" in term else "group"
        items = await self._get("/search", {"term": term, "type": kind})
        return [
            {"kind": kind, "id": int(i["id"]), "label": i.get("label") or str(i["id"]),
             "description": i.get("description") or ""}
            for i in items if i.get("id") is not None
        ][:8]

    async def schedule(self, kind: str, entity_id: int, start: date, finish: date) -> list[Lesson]:
        items = await self._get(
            f"/schedule/{kind}/{entity_id}",
            {"start": start.strftime("%Y.%m.%d"), "finish": finish.strftime("%Y.%m.%d"), "lng": 1},
        )
        return [_parse_lesson(i) for i in items]
