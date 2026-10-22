import unittest
from datetime import date, datetime

from tests import conftest_env  # noqa: F401
from config import TZ
from utils import fmt_left, fmt_num, match_name, parse_date, parse_deadline, parse_hhmm, parse_num, parse_weekday

# Понедельник, 19 октября 2026, 12:00
BASE = datetime(2026, 10, 19, 12, 0, tzinfo=TZ)


class ParseTokens(unittest.TestCase):
    def test_hhmm(self):
        self.assertEqual(parse_hhmm("9:05"), "09:05")
        self.assertEqual(parse_hhmm("23:59"), "23:59")
        self.assertIsNone(parse_hhmm("24:00"))
        self.assertIsNone(parse_hhmm("12:60"))
        self.assertIsNone(parse_hhmm("abc"))

    def test_weekday(self):
        self.assertEqual(parse_weekday("пн"), 0)
        self.assertEqual(parse_weekday("пятница"), 4)
        self.assertIsNone(parse_weekday("привет"))

    def test_date_without_year_is_future(self):
        self.assertEqual(parse_date("25.10", date(2026, 10, 19)), date(2026, 10, 25))
        self.assertEqual(parse_date("01.09", date(2026, 10, 19)), date(2027, 9, 1))

    def test_date_with_year(self):
        self.assertEqual(parse_date("25.10.26", date(2026, 1, 1)), date(2026, 10, 25))
        self.assertEqual(parse_date("25.10.2027", date(2026, 1, 1)), date(2027, 10, 25))

    def test_date_invalid(self):
        self.assertIsNone(parse_date("31.02", date(2026, 1, 1)))
        self.assertIsNone(parse_date("завтра", date(2026, 1, 1)))

    def test_num(self):
        self.assertEqual(parse_num("5,6"), 5.6)
        self.assertEqual(parse_num("8"), 8.0)
        self.assertIsNone(parse_num("КР"))

    def test_fmt_num(self):
        self.assertEqual(fmt_num(5.0), "5")
        self.assertEqual(fmt_num(5.60), "5.6")
        self.assertEqual(fmt_num(7.125), "7.12")


class Deadline(unittest.TestCase):
    def test_tomorrow_default_time(self):
        self.assertEqual(parse_deadline("завтра", BASE), datetime(2026, 10, 20, 23, 59, tzinfo=TZ))

    def test_day_after_tomorrow_with_time(self):
        self.assertEqual(parse_deadline("послезавтра 18:00", BASE), datetime(2026, 10, 21, 18, 0, tzinfo=TZ))

    def test_weekday_is_next_not_today(self):
        # сегодня понедельник, «пн» = через неделю
        self.assertEqual(parse_deadline("пн", BASE).date(), date(2026, 10, 26))
        self.assertEqual(parse_deadline("пт 10:00", BASE), datetime(2026, 10, 23, 10, 0, tzinfo=TZ))

    def test_plus_days_and_week(self):
        self.assertEqual(parse_deadline("+3", BASE).date(), date(2026, 10, 22))
        self.assertEqual(parse_deadline("через неделю", BASE).date(), date(2026, 10, 26))
        self.assertEqual(parse_deadline("через 2 дня", BASE).date(), date(2026, 10, 21))

    def test_only_time(self):
        self.assertEqual(parse_deadline("18:00", BASE), datetime(2026, 10, 19, 18, 0, tzinfo=TZ))
        # 09:00 уже прошло → завтра
        self.assertEqual(parse_deadline("09:00", BASE), datetime(2026, 10, 20, 9, 0, tzinfo=TZ))

    def test_date_with_time(self):
        self.assertEqual(parse_deadline("25.10 18:00", BASE), datetime(2026, 10, 25, 18, 0, tzinfo=TZ))

    def test_garbage(self):
        self.assertIsNone(parse_deadline("когда-нибудь", BASE))
        self.assertIsNone(parse_deadline("", BASE))


class FmtLeft(unittest.TestCase):
    def test_left(self):
        self.assertEqual(fmt_left(datetime(2026, 10, 19, 15, 30, tzinfo=TZ), BASE), "осталось 3 ч 30 мин")
        self.assertEqual(fmt_left(datetime(2026, 10, 21, 12, 0, tzinfo=TZ), BASE), "осталось 2 д")

    def test_overdue(self):
        self.assertEqual(fmt_left(datetime(2026, 10, 19, 11, 0, tzinfo=TZ), BASE), "просрочено на 1 ч")


class MatchName(unittest.TestCase):
    names = ["Английский язык", "Математический анализ", "Матрицы"]

    def test_exact(self):
        self.assertEqual(match_name("матрицы", self.names), ["Матрицы"])

    def test_prefix_unique(self):
        self.assertEqual(match_name("англ", self.names), ["Английский язык"])

    def test_ambiguous(self):
        self.assertEqual(len(match_name("мат", self.names)), 2)

    def test_none(self):
        self.assertEqual(match_name("физика", self.names), [])


if __name__ == "__main__":
    unittest.main()
