"""Данные расписания: RUZ (с кэшем в БД) + ручные пары."""
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta

from db import Database
from ruz import Lesson, Ruz, RuzError
from utils import at, now, q, today

CACHE_TTL = 6 * 3600          # как часто перезапрашивать RUZ


async def get_lessons(db: Database, ruz: Ruz, uid: int, start: date, end: date) -> tuple[dict[date, list[Lesson]], str | None]:
    """RUZ (с кэшем в БД) + ручные пары. Возвращает {день: [пары]} и предупреждение, если RUZ лёг."""
    user = db.user(uid)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    result: dict[date, list[Lesson]] = {d: [] for d in days}
    warning = None

    if user["ruz_id"]:
        source = f"{user['ruz_kind']}:{user['ruz_id']}"
        keys = [d.isoformat() for d in days]
        cached = db.cache_get(source, keys)
        fresh = all(k in cached and time.time() - cached[k][1] < CACHE_TTL for k in keys)
        if not fresh:
            # тянем целыми неделями — меньше запросов
            ws = start - timedelta(days=start.weekday())
            we = end + timedelta(days=6 - end.weekday())
            try:
                lessons = await ruz.schedule(user["ruz_kind"], user["ruz_id"], ws, we)
            except RuzError as e:
                warning = ("⚠️ RUZ сейчас недоступен, показываю сохранённое расписание" if cached
                           else f"⚠️ RUZ недоступен: {q(str(e))}")
            else:
                by_day = {(ws + timedelta(days=i)).isoformat(): [] for i in range((we - ws).days + 1)}
                for lesson in lessons:
                    by_day.setdefault(lesson.day, []).append(asdict(lesson))
                db.cache_put(source, by_day)
                cached = db.cache_get(source, keys)
        for k, (items, _) in cached.items():
            result[date.fromisoformat(k)] = [Lesson(**i) for i in items]

    for d in days:
        for r in db.lessons_on(uid, d):
            result[d].append(Lesson(day=d.isoformat(), begin=r["time_from"], end=r["time_to"],
                                    title=r["title"], room=r["room"], manual=True))
        result[d].sort(key=lambda l: l.begin)
    return result, warning


async def next_lesson_start(db: Database, ruz: Ruz, uid: int, subject: str) -> datetime | None:
    """Начало ближайшей пары по предмету в пределах 3 недель."""
    start = today()
    lessons, _ = await get_lessons(db, ruz, uid, start, start + timedelta(days=20))
    sf = subject.casefold()
    cur = now()
    for d in sorted(lessons):
        for lesson in lessons[d]:
            title = lesson.title.casefold()
            if lesson.begin and (title == sf or sf in title):
                dt = at(d, lesson.begin)
                if dt > cur:
                    return dt
    return None


async def subject_candidates(db: Database, ruz: Ruz, uid: int) -> list[str]:
    """Предметы для кнопок: недавние из ДЗ → из расписания на 2 недели → из оценок."""
    names: list[str] = list(db.hw_subjects(uid))
    lessons, _ = await get_lessons(db, ruz, uid, today(), today() + timedelta(days=13))
    names += [lesson.title for d in sorted(lessons) for lesson in lessons[d]]
    names += [r["name"] for r in db.subjects(uid)]
    seen, unique = set(), []
    for n in names:
        if n.casefold() not in seen:
            seen.add(n.casefold())
            unique.append(n)
    return unique[:16]
