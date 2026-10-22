"""Оценки: разбор формулы и расчёт накопа."""
import math
import re
from sqlite3 import Row

from db import Database
from utils import fmt_num, q

TARGETS = ((4, "удовл"), (6, "хор"), (8, "отл"), (10, "максимум"))


def round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def ceil2(x: float) -> float:
    return math.ceil(round(x * 100, 6)) / 100


def parse_formula(text: str) -> tuple[str, list[tuple[str, float]]]:
    """«Матан: КР 0.3, экзамен 0.5, ДЗ 0.2» → ("Матан", [("КР", .3), ...]). Веса можно в %."""
    if ":" in text:
        name, rest = text.split(":", 1)
    else:
        name, _, rest = text.strip().partition(" ")
    name = name.strip()
    rest = re.sub(r"(\d),(\d)", r"\1.\2", rest)
    comps = []
    for part in re.split(r"[;,\n]", rest):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(.+?)\s*[-—=:]?\s*(\d+(?:\.\d+)?)\s*(%?)", part)
        if not m:
            raise ValueError(f"не понял «{part}»")
        weight = float(m[2])
        if m[3] or weight > 1:
            weight /= 100
        comps.append((m[1].strip(), weight))
    if not name or not comps:
        raise ValueError("нужно название предмета и хотя бы один компонент")
    if len({c.casefold() for c, _ in comps}) != len(comps):
        raise ValueError("названия компонентов повторяются")
    return name, comps


def subject_report(db: Database, subject: Row) -> str:
    comps = db.components(subject["id"])
    lines = [f"📊 <b>{q(subject['name'])}</b>"]
    known = known_w = 0.0
    missing = []
    for c in comps:
        vals = db.grades(c["id"])
        if vals:
            avg = sum(vals) / len(vals)
            known += avg * c["weight"]
            known_w += c["weight"]
            shown = ", ".join(fmt_num(v) for v in vals) + (f" → <b>{fmt_num(avg)}</b>" if len(vals) > 1 else "")
        else:
            shown = "—"
            missing.append(c["name"])
        lines.append(f"• {q(c['name'])} ({fmt_num(c['weight'] * 100)}%): {shown}")

    total_w = sum(c["weight"] for c in comps)
    if abs(total_w - 1) > 0.001:
        lines.append(f"⚠️ Сумма весов = {fmt_num(total_w)}, а должна быть 1")
    if not missing:
        lines.append(f"<b>Итог: {fmt_num(known)} → {round_half_up(known)}</b>")
        return "\n".join(lines)

    miss_w = total_w - known_w
    lines.append(f"Уже набрано: <b>{fmt_num(known)}</b> (закрыто {fmt_num(known_w * 100)}% веса)")
    lines.append(f"Нужно в среднем за «{q(', '.join(missing))}», чтобы итог округлился до:")
    for target, label in TARGETS:
        need = (target - 0.5 - known) / miss_w
        if need <= 0:
            verdict = "уже в кармане ✅"
        elif need > 10:
            verdict = "недостижимо ❌"
        else:
            verdict = f"≥ {fmt_num(ceil2(need))}"
        lines.append(f"   {target} ({label}) → {verdict}")
    return "\n".join(lines)
