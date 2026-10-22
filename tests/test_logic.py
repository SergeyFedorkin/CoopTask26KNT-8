import unittest

from tests import conftest_env  # noqa: F401
from grades_logic import ceil2, parse_formula, round_half_up
from homework_logic import fmt_hours, parse_hours, plural


class Plural(unittest.TestCase):
    def test_forms(self):
        f = lambda n: plural(n, "день", "дня", "дней")
        self.assertEqual([f(1), f(2), f(5)], ["день", "дня", "дней"])
        self.assertEqual([f(11), f(12), f(21), f(22), f(25)], ["дней", "дней", "день", "дня", "дней"])


class Hours(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_hours("24 3"), [24, 3])
        self.assertEqual(parse_hours("3, 24, 3ч, 0.5"), [24, 3, 0.5])

    def test_parse_ignores_garbage_and_range(self):
        self.assertEqual(parse_hours("abc 0 -5 99999 12"), [12])

    def test_fmt(self):
        self.assertEqual(fmt_hours(24), "за сутки")
        self.assertEqual(fmt_hours(48), "за 2 дня")
        self.assertEqual(fmt_hours(120), "за 5 дней")
        self.assertEqual(fmt_hours(3), "за 3 ч")
        self.assertEqual(fmt_hours(0.5), "за 30 мин")


class Formula(unittest.TestCase):
    def test_basic(self):
        name, comps = parse_formula("Матан: КР 0.3, экзамен 0.5, ДЗ 0.2")
        self.assertEqual(name, "Матан")
        self.assertEqual([c for c, _ in comps], ["КР", "экзамен", "ДЗ"])
        self.assertAlmostEqual(sum(w for _, w in comps), 1.0)

    def test_percent_and_comma(self):
        _, comps = parse_formula("Физика: КР 30%, экзамен 0,7")
        self.assertEqual(comps, [("КР", 0.3), ("экзамен", 0.7)])

    def test_errors(self):
        with self.assertRaises(ValueError):
            parse_formula("Матан: КР")
        with self.assertRaises(ValueError):
            parse_formula("Матан: КР 0.5, кр 0.5")


class Rounding(unittest.TestCase):
    def test_half_up(self):
        self.assertEqual(round_half_up(5.5), 6)   # не банковское округление
        self.assertEqual(round_half_up(4.5), 5)
        self.assertEqual(round_half_up(4.49), 4)

    def test_ceil2(self):
        self.assertEqual(ceil2(5.001), 5.01)
        self.assertEqual(ceil2(5.0), 5.0)


if __name__ == "__main__":
    unittest.main()
