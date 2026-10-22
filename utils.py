import re
from datetime import date, datetime, time, timedelta
from html import escape

from config import TZ

WD_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WD_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
WD_PREFIX = ["пон", "вто", "сре", "чет", "пят", "суб", "вос"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]
DEFAULT_DEADLINE_TIME = time(23, 59)


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def from_ts(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, TZ)


def at(day: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day, time(h, m), TZ)


def parse_weekday(token: str) -> int | None:
    token = token.lower().strip(".,")
    if token in WD_SHORT:
        return WD_SHORT.index(token)
    for i, p in enumerate(WD_PREFIX):
        if token.startswith(p):
            return i
    return None


def parse_hhmm(token: str) -> str | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", token.strip())
    if not m:
        return None
    h, mi = int(m[1]), int(m[2])
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def parse_date(token: str, base: date) -> date | None:
    """25.10 / 25.10.26 / 25.10.2026. Без года — ближайшая будущая такая дата."""
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2}|\d{4}))?", token.strip())
    if not m:
        return None
    d, mo = int(m[1]), int(m[2])
    year = int(m[3]) if m[3] else base.year
    if year < 100:
        year += 2000
    try:
        result = date(year, mo, d)
    except ValueError:
        return None
    if not m[3] and result < base:
        result = result.replace(year=year + 1)
    return result


def parse_deadline(text: str, base: datetime | None = None) -> datetime | None:
    """
    Понимает: «завтра», «послезавтра», «сегодня 18:00», «пт», «пятница 10:00»,
    «25.10», «25.10 18:00», «18:00», «+3», «через 3 дня», «через неделю».
    Без времени — 23:59. Только время — сегодня (или завтра, если уже прошло).
    """
    base = base or now()
    s = text.lower().strip()
    s = re.sub(r"\bв\b|\bдо\b|\bк\b", " ", s)
    s = re.sub(r"через\s+неделю", "+7", s)
    s = re.sub(r"через\s+(\d+)\s*(д|дн|день|дня|дней)\b\.?", r"+\1", s)

    day: date | None = None
    hhmm: str | None = None
    for tok in s.split():
        if (t := parse_hhmm(tok)) and hhmm is None:
            hhmm = t
        elif tok == "сегодня" and day is None:
            day = base.date()
        elif tok == "завтра" and day is None:
            day = base.date() + timedelta(days=1)
        elif tok == "послезавтра" and day is None:
            day = base.date() + timedelta(days=2)
        elif (m := re.fullmatch(r"\+(\d{1,3})", tok)) and day is None:
            day = base.date() + timedelta(days=int(m[1]))
        elif (d := parse_date(tok, base.date())) and day is None:
            day = d
        elif (wd := parse_weekday(tok)) is not None and day is None:
            ahead = (wd - base.weekday()) % 7 or 7
            day = base.date() + timedelta(days=ahead)
        else:
            return None

    if day is None and hhmm is None:
        return None
    if day is None:
        result = at(base.date(), hhmm)
        return result if result > base else result + timedelta(days=1)
    if hhmm is None:
        return datetime.combine(day, DEFAULT_DEADLINE_TIME, TZ)
    return at(day, hhmm)


def fmt_day(d: date) -> str:
    return f"{WD_FULL[d.weekday()]}, {d.day} {MONTHS[d.month - 1]}"


def fmt_dt(dt: datetime) -> str:
    return f"{WD_SHORT[dt.weekday()]} {dt.day} {MONTHS[dt.month - 1][:3]}, {dt:%H:%M}"


def fmt_left(dt: datetime, base: datetime | None = None) -> str:
    secs = int((dt - (base or now())).total_seconds())
    overdue = secs < 0
    secs = abs(secs)
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        span = f"{d} д {h} ч" if h else f"{d} д"
    elif h:
        span = f"{h} ч {m} мин" if m else f"{h} ч"
    else:
        span = f"{max(m, 1)} мин"
    return f"просрочено на {span}" if overdue else f"осталось {span}"


def fmt_num(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


def parse_num(token: str) -> float | None:
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None


def q(text: str) -> str:
    """Экранирование пользовательского текста для parse_mode=HTML."""
    return escape(text, quote=False)


def match_name(query: str, names: list[str]) -> list[str]:
    """Нечёткий поиск: точное совпадение → начало слова → подстрока."""
    ql = query.casefold().strip()
    exact = [n for n in names if n.casefold() == ql]
    if exact:
        return exact
    prefix = [n for n in names if n.casefold().startswith(ql)]
    if prefix:
        return prefix
    return [n for n in names if ql in n.casefold()]
