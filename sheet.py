"""Расписание из Google-таблицы факультета (запасной источник, когда RUZ недоступен вне сети ВШЭ).

Таблица устроена так: строка с названиями групп («26КНТ-8»), справа от группы — «Ауд.» и «Корпус»;
слева колонки «День» и «Время». Лекции на весь поток — объединённые ячейки.
В тексте ячейки бывают пометки дат: «15.09., 29.09.», «с 09.09.», «10.09.-22.10.».
"""
import asyncio
import io
import re
import time
from datetime import date, timedelta

import aiohttp
import openpyxl

from config import settings
from ruz import Lesson, RuzError
from utils import today


class SheetError(RuzError):
    pass


WEEKDAYS = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6}
BUILDINGS = {"Л": "Львовская", "Р": "Родионова", "БП": "Б.Печёрская", "БПок": "Б.Покровская",
             "К": "Костина", "С": "Сормовское ш."}
TIME_RE = re.compile(r"(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})")
DATE = r"\d{1,2}\.\d{1,2}"
# список дат в начале ячейки; разделители терпимые к опечаткам («10.10.. 24.10.»)
PREFIX_RE = re.compile(rf"^((?:с\s*)?{DATE}\.*(?:\s*[,;.]?\s*-?\s*{DATE}\.*)*)\s+(.*)$", re.S)
MODULE_RE = re.compile(rf"\(\s*({DATE})\.?\s*[-–—]\s*({DATE})\.?\s*\)")
TEACHER_RE = re.compile(r"[А-ЯЁ][а-яё-]+\s+[А-ЯЁ]\.(?:\s?[А-ЯЁ]\.)?")
# пометки внутри ячейки: «12.10. отмена занятия», «06.10. в 09:30-10:10», и «в 11:10-11:50 ...» в начале
CANCEL_RE = re.compile(rf"({DATE})\.?\s*[-–—]?\s*отмена\s+заняти\w*", re.I)
TIME_NOTE_RE = re.compile(rf"({DATE})\.?\s*в\s*(\d{{1,2}}:\d{{2}})\s*[-–—]\s*(\d{{1,2}}:\d{{2}})")
MAKEUP_RE = re.compile(r"[-–—]?\s*восстановление\s+заняти\w*", re.I)
MAKEUP_DATE_RE = re.compile(rf"({DATE})\.?\s*[-–—]\s*(лекция|семинар)")
LEADING_TIME_RE = re.compile(r"^\s*в\s*(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})\s*")
SKIP_PHRASES = ("Занятия проводятся по расписанию", "проводятся согласно расписанию")
CACHE_SECONDS = 30 * 60

_cache: dict[str, tuple[float, dict]] = {}
_lock = asyncio.Lock()


def export_url(url: str) -> str:
    """Любая ссылка на Google-таблицу → ссылка на скачивание .xlsx."""
    m = re.search(r"/spreadsheets/(?:u/\d+/)?d/([\w-]+)", url)
    return f"https://docs.google.com/spreadsheets/d/{m[1]}/export?format=xlsx" if m else url


def _norm(s: str) -> str:
    return re.sub(r"[\s\-–—]", "", str(s)).casefold()


def _academic_date(dm: str, ref: date) -> date:
    """«15.09» → дата учебного года, в котором лежит ref (сентябрь–декабрь — один год, январь–август — следующий)."""
    d, m = (int(x) for x in dm.strip(". ").split(".")[:2])
    start_year = ref.year if ref.month >= 8 else ref.year - 1
    return date(start_year if m >= 8 else start_year + 1, m, d)


def _parse_workbook(data: bytes) -> dict:
    """Все листы → {группа: [строки расписания]}. Строка: день недели, время, текст, ауд., корпус, рамки модуля."""
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    groups: dict[str, dict] = {}
    for ws in wb.worksheets:
        merged = {}
        for rng in ws.merged_cells.ranges:
            top = ws.cell(rng.min_row, rng.min_col).value
            for r in range(rng.min_row, rng.max_row + 1):
                for c in range(rng.min_col, rng.max_col + 1):
                    merged[(r, c)] = top

        def val(r: int, c: int):
            return merged.get((r, c), ws.cell(r, c).value)

        day_col = time_col = header_row = None
        module = None
        for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 30)):
            for cell in row:
                v = str(cell.value or "").strip()
                if v == "День":
                    day_col = cell.column
                elif v == "Время":
                    time_col, header_row = cell.column, cell.row
                elif module is None and (m := MODULE_RE.search(v)):
                    module = (m[1], m[2])
        if not (day_col and time_col):
            continue
        # строка с названиями групп: та, где справа от названия стоит «Ауд.»
        for r in range(header_row, header_row + 3):
            for c in range(1, ws.max_column + 1):
                name = ws.cell(r, c).value
                if name and str(ws.cell(r, c + 1).value or "").startswith("Ауд"):
                    rows = []
                    weekday = None
                    for rr in range(r + 1, ws.max_row + 1):
                        wd = str(val(rr, day_col) or "").strip().lower()[:2]
                        weekday = WEEKDAYS.get(wd, weekday)
                        t = TIME_RE.search(str(ws.cell(rr, time_col).value or ""))
                        text = val(rr, c)
                        if weekday is None or not t or not text:
                            continue
                        rows.append((weekday, t[1].zfill(5), t[2].zfill(5), str(text),
                                     str(val(rr, c + 1) or ""), str(val(rr, c + 2) or "").strip()))
                    groups[_norm(name)] = {"name": str(name).strip(), "rows": rows, "module": module}
    return groups


async def _load() -> dict:
    url = export_url(settings.sheet_url)
    async with _lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
                async with s.get(url) as r:
                    if r.status != 200:
                        raise SheetError(f"таблица недоступна (HTTP {r.status})")
                    data = await r.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            raise SheetError(f"не скачалась таблица: {e or type(e).__name__}") from e
        try:
            groups = await asyncio.to_thread(_parse_workbook, data)
        except Exception as e:  # битый файл / доступ закрыт и пришла HTML-страница
            raise SheetError("не получилось прочитать таблицу (проверь, что она открыта по ссылке)") from e
        _cache[url] = (time.time(), groups)
        return groups


async def find_group(query: str) -> str | None:
    """Точное название группы из таблицы или None."""
    groups = await _load()
    g = groups.get(_norm(query))
    return g["name"] if g else None


def _applies(prefix: str, day: date, module: tuple[date, date] | None) -> bool:
    if not prefix:
        return module is None or module[0] <= day <= module[1]
    p = prefix.strip()
    if m := re.fullmatch(rf"с\s*({DATE})\.?", p):
        return day >= _academic_date(m[1], day) and (module is None or day <= module[1])
    if m := re.fullmatch(rf"({DATE})\.?\s*-\s*({DATE})\.?", p):
        return _academic_date(m[1], day) <= day <= _academic_date(m[2], day)
    return day in {_academic_date(x, day) for x in re.findall(DATE, p)}


def _lesson(day: date, begin: str, end: str, item: str, room: str, building: str, kind: str = "") -> Lesson:
    body = re.sub(r"\s+", " ", item).strip()
    teacher = TEACHER_RE.findall(body)
    parts = [p.strip() for p in re.split(r"\s+-\s+", body) if p.strip()]
    parts = [p for p in parts if not re.match(r"^\d{2}_\d{2}_", p)]          # коды курсов вида 26_27_М_ОРГ_...
    title = TEACHER_RE.sub("", parts[0]).strip(" -") if parts else body
    for p in parts[1:]:
        word = p.split()[0].lower()
        if kind:
            break
        if word in ("лекция", "семинар"):
            kind = word
        elif word == "практическое":
            kind = "практика"
    where = "online" if building.lower() == "online" else ", ".join(
        x for x in (room.replace(".0", "").strip(" -"), BUILDINGS.get(building, building)) if x)
    return Lesson(day=day.isoformat(), begin=begin, end=end, title=title, kind=kind,
                  room=where, lecturer=teacher[-1] if teacher else "")


async def schedule(group: str, start: date, finish: date) -> list[Lesson]:
    groups = await _load()
    g = groups.get(_norm(group))
    if not g:
        raise SheetError(f"группы {group} нет в таблице")
    ref = today()
    module = tuple(_academic_date(x, ref) for x in g["module"]) if g["module"] else None
    result = []
    day = start
    while day <= finish:
        for weekday, begin, end, text, rooms_raw, building in g["rows"]:
            if weekday != day.weekday() or any(s in text for s in SKIP_PHRASES):
                continue
            if rooms_raw == text:   # лекция на поток в объединённой ячейке захватила и колонку аудитории
                rooms_raw = ""
            if building == text.strip():
                building = ""
            items = [i.strip() for i in re.split(r"\n\s*\n", text) if i.strip()]
            rooms = [x.strip() for x in re.split(r"\n\s*\n+", rooms_raw) if x.strip()] or [""]
            for idx, item in enumerate(items):
                m = PREFIX_RE.match(item)
                prefix, body = (m[1], m[2]) if m else ("", item)
                if not _applies(prefix, day, module):
                    continue
                kind = ""
                if MAKEUP_RE.search(body):
                    # «восстановление занятий\n25.09. - лекция\n02.10. - семинар» — только в эти даты
                    dated = {_academic_date(d, day): k for d, k in MAKEUP_DATE_RE.findall(body)}
                    if dated and day not in dated:
                        continue
                    kind = dated.get(day, "")
                    body = MAKEUP_DATE_RE.sub("", MAKEUP_RE.sub("", body))
                cancelled = {_academic_date(d, day) for d in CANCEL_RE.findall(body)}
                moved = {_academic_date(d, day): (b, e) for d, b, e in TIME_NOTE_RE.findall(body)}
                body = TIME_NOTE_RE.sub("", CANCEL_RE.sub("", body))
                b, e = begin, end
                if lt := LEADING_TIME_RE.match(body):
                    b, e, body = lt[1], lt[2], body[lt.end():]
                if day in cancelled:
                    continue
                b, e = moved.get(day, (b, e))
                room = rooms[idx] if idx < len(rooms) else rooms[0]
                result.append(_lesson(day, b.zfill(5), e.zfill(5), body, room, building, kind))
        day += timedelta(days=1)
    return result
