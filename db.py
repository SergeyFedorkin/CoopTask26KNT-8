import json
import sqlite3
import time
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY,
    ruz_kind     TEXT,
    ruz_id       INTEGER,
    ruz_label    TEXT,
    summary_time TEXT    NOT NULL DEFAULT '07:30',
    summary_on   INTEGER NOT NULL DEFAULT 1,
    last_summary TEXT,
    remind_hours TEXT    NOT NULL DEFAULT '24,3'
);
CREATE TABLE IF NOT EXISTS homework (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    subject    TEXT    NOT NULL,
    text       TEXT    NOT NULL,
    deadline   INTEGER,
    done       INTEGER NOT NULL DEFAULT 0,
    done_at    INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS hw_user ON homework(user_id, done, deadline);
CREATE TABLE IF NOT EXISTS reminders_sent (
    hw_id INTEGER NOT NULL REFERENCES homework(id) ON DELETE CASCADE,
    hours REAL    NOT NULL,
    PRIMARY KEY (hw_id, hours)
);
CREATE TABLE IF NOT EXISTS lessons (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    weekday INTEGER,
    day     TEXT,
    time_from TEXT NOT NULL,
    time_to   TEXT NOT NULL,
    title   TEXT NOT NULL,
    room    TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ruz_cache (
    source     TEXT    NOT NULL,
    day        TEXT    NOT NULL,
    data       TEXT    NOT NULL,
    fetched_at INTEGER NOT NULL,
    PRIMARY KEY (source, day)
);
CREATE TABLE IF NOT EXISTS subjects (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name    TEXT    NOT NULL,
    UNIQUE (user_id, name)
);
CREATE TABLE IF NOT EXISTS components (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    weight     REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS grades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    value        REAL    NOT NULL,
    created_at   INTEGER NOT NULL
);
"""

USER_FIELDS = {"ruz_kind", "ruz_id", "ruz_label", "summary_time", "summary_on", "last_summary", "remind_hours"}


class Database:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def user(self, uid: int) -> sqlite3.Row:
        self._exec("INSERT OR IGNORE INTO users(id) VALUES (?)", (uid,))
        return self._one("SELECT * FROM users WHERE id = ?", (uid,))

    def update_user(self, uid: int, **fields) -> None:
        assert fields.keys() <= USER_FIELDS, fields.keys() - USER_FIELDS
        cols = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute("INSERT OR IGNORE INTO users(id) VALUES (?)", (uid,))
        self._exec(f"UPDATE users SET {cols} WHERE id = ?", (*fields.values(), uid))

    def users(self) -> list[sqlite3.Row]:
        return self._all("SELECT * FROM users")

    def add_hw(self, uid: int, subject: str, text: str, deadline: int | None) -> int:
        cur = self._exec(
            "INSERT INTO homework(user_id, subject, text, deadline, created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, subject, text, deadline, int(time.time())),
        )
        return cur.lastrowid

    def hw_active(self, uid: int) -> list[sqlite3.Row]:
        # без дедлайна — в конце списка
        return self._all(
            "SELECT * FROM homework WHERE user_id = ? AND done = 0 "
            "ORDER BY deadline IS NULL, deadline, id",
            (uid,),
        )

    def hw_done_list(self, uid: int, limit: int = 15) -> list[sqlite3.Row]:
        return self._all(
            "SELECT * FROM homework WHERE user_id = ? AND done = 1 ORDER BY done_at DESC LIMIT ?",
            (uid, limit),
        )

    def hw_get(self, uid: int, hw_id: int) -> sqlite3.Row | None:
        return self._one("SELECT * FROM homework WHERE id = ? AND user_id = ?", (hw_id, uid))

    def hw_set_done(self, uid: int, hw_id: int, done: bool) -> None:
        self._exec(
            "UPDATE homework SET done = ?, done_at = ? WHERE id = ? AND user_id = ?",
            (int(done), int(time.time()) if done else None, hw_id, uid),
        )

    def hw_delete(self, uid: int, hw_id: int) -> None:
        self._exec("DELETE FROM homework WHERE id = ? AND user_id = ?", (hw_id, uid))

    def hw_subjects(self, uid: int, limit: int = 10) -> list[str]:
        rows = self._all(
            "SELECT subject FROM homework WHERE user_id = ? GROUP BY subject ORDER BY MAX(id) DESC LIMIT ?",
            (uid, limit),
        )
        return [r["subject"] for r in rows]

    def hw_pending_all(self, now_ts: int) -> list[sqlite3.Row]:
        return self._all("SELECT * FROM homework WHERE done = 0 AND deadline > ?", (now_ts,))

    def reminders_sent(self, hw_id: int) -> set[float]:
        return {r["hours"] for r in self._all("SELECT hours FROM reminders_sent WHERE hw_id = ?", (hw_id,))}

    def mark_reminders(self, hw_id: int, hours: list[float]) -> None:
        self.conn.executemany(
            "INSERT OR IGNORE INTO reminders_sent(hw_id, hours) VALUES (?, ?)", [(hw_id, h) for h in hours]
        )
        self.conn.commit()

    def add_lesson(self, uid: int, weekday: int | None, day: str | None,
                   time_from: str, time_to: str, title: str, room: str) -> int:
        cur = self._exec(
            "INSERT INTO lessons(user_id, weekday, day, time_from, time_to, title, room) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, weekday, day, time_from, time_to, title, room),
        )
        return cur.lastrowid

    def lessons_on(self, uid: int, d: date) -> list[sqlite3.Row]:
        return self._all(
            "SELECT * FROM lessons WHERE user_id = ? AND (weekday = ? OR day = ?) ORDER BY time_from",
            (uid, d.weekday(), d.isoformat()),
        )

    def lessons_all(self, uid: int) -> list[sqlite3.Row]:
        return self._all(
            "SELECT * FROM lessons WHERE user_id = ? ORDER BY weekday IS NULL, weekday, day, time_from", (uid,)
        )

    def delete_lesson(self, uid: int, lesson_id: int) -> None:
        self._exec("DELETE FROM lessons WHERE id = ? AND user_id = ?", (lesson_id, uid))

    def cache_get(self, source: str, days: list[str]) -> dict[str, tuple[list[dict], int]]:
        marks = ",".join("?" * len(days))
        rows = self._all(
            f"SELECT day, data, fetched_at FROM ruz_cache WHERE source = ? AND day IN ({marks})", (source, *days)
        )
        return {r["day"]: (json.loads(r["data"]), r["fetched_at"]) for r in rows}

    def cache_put(self, source: str, by_day: dict[str, list[dict]]) -> None:
        ts = int(time.time())
        self.conn.executemany(
            "INSERT OR REPLACE INTO ruz_cache(source, day, data, fetched_at) VALUES (?, ?, ?, ?)",
            [(source, d, json.dumps(items, ensure_ascii=False), ts) for d, items in by_day.items()],
        )
        self.conn.commit()

    def subjects(self, uid: int) -> list[sqlite3.Row]:
        return self._all("SELECT * FROM subjects WHERE user_id = ? ORDER BY name", (uid,))

    def components(self, subject_id: int) -> list[sqlite3.Row]:
        return self._all("SELECT * FROM components WHERE subject_id = ? ORDER BY id", (subject_id,))

    def grades(self, component_id: int) -> list[float]:
        rows = self._all("SELECT value FROM grades WHERE component_id = ? ORDER BY id", (component_id,))
        return [r["value"] for r in rows]

    def set_formula(self, uid: int, name: str, comps: list[tuple[str, float]]) -> None:
        """Создаёт предмет или обновляет формулу, сохраняя оценки у компонентов с тем же именем."""
        self._exec("INSERT OR IGNORE INTO subjects(user_id, name) VALUES (?, ?)", (uid, name))
        sid = self._one("SELECT id FROM subjects WHERE user_id = ? AND name = ?", (uid, name))["id"]
        old = {r["name"].casefold(): r["id"] for r in self.components(sid)}
        keep = set()
        for comp, weight in comps:
            cid = old.get(comp.casefold())
            if cid:
                self.conn.execute("UPDATE components SET name = ?, weight = ? WHERE id = ?", (comp, weight, cid))
                keep.add(cid)
            else:
                self.conn.execute(
                    "INSERT INTO components(subject_id, name, weight) VALUES (?, ?, ?)", (sid, comp, weight)
                )
        for cid in set(old.values()) - keep:
            self.conn.execute("DELETE FROM components WHERE id = ?", (cid,))
        self.conn.commit()

    def add_grades(self, component_id: int, values: list[float]) -> None:
        ts = int(time.time())
        self.conn.executemany(
            "INSERT INTO grades(component_id, value, created_at) VALUES (?, ?, ?)",
            [(component_id, v, ts) for v in values],
        )
        self.conn.commit()

    def pop_grade(self, component_id: int) -> float | None:
        row = self._one("SELECT id, value FROM grades WHERE component_id = ? ORDER BY id DESC LIMIT 1", (component_id,))
        if row is None:
            return None
        self._exec("DELETE FROM grades WHERE id = ?", (row["id"],))
        return row["value"]

    def delete_subject(self, uid: int, subject_id: int) -> None:
        self._exec("DELETE FROM subjects WHERE id = ? AND user_id = ?", (subject_id, uid))
