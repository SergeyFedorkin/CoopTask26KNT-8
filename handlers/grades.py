from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from db import Database
from keyboards import BTN_GRADES
from grades_logic import parse_formula, subject_report
from utils import fmt_num, match_name, parse_num, q

router = Router()

GRADES_HELP = """📊 <b>Оценки и накоп</b>

1) Задай формулу предмета:
<code>/formula Матан: КР 0.3, экзамен 0.5, ДЗ 0.2</code>
   (веса можно в процентах: <code>КР 30%</code>)
2) Вноси оценки:
<code>/grade матан КР 5.6</code>
<code>/grade матан ДЗ 8 9 7</code> — несколько сразу, внутри компонента берётся среднее
3) /grades — покажу накоп и сколько нужно на оставшихся элементах

/delgrade матан КР — убрать последнюю оценку
/delsubject матан — удалить предмет"""


def _find_subject(db: Database, uid: int, query: str):
    """Возвращает (row, ошибка)."""
    subjects = db.subjects(uid)
    found = match_name(query, [s["name"] for s in subjects])
    if len(found) == 1:
        return next(s for s in subjects if s["name"] == found[0]), None
    if not found:
        names = ", ".join(q(s["name"]) for s in subjects) or "пока нет — создай через /formula"
        return None, f"Не нашёл предмет «{q(query)}». Есть: {names}"
    return None, f"«{q(query)}» подходит под несколько: {', '.join(q(n) for n in found)}. Уточни."


def _split_subject_component(db: Database, uid: int, tokens: list[str]):
    """«Дискретная математика КР» → (предмет, «КР»). Пробуем самый длинный префикс."""
    names = [s["name"] for s in db.subjects(uid)]
    for i in range(len(tokens) - 1, 0, -1):
        if len(match_name(" ".join(tokens[:i]), names)) == 1:
            subject, _ = _find_subject(db, uid, " ".join(tokens[:i]))
            return subject, " ".join(tokens[i:]), None
    _, err = _find_subject(db, uid, tokens[0])
    return None, None, err or "Не понял предмет."


def _find_component(db: Database, subject, query: str):
    comps = db.components(subject["id"])
    found = match_name(query, [c["name"] for c in comps])
    if len(found) == 1:
        return next(c for c in comps if c["name"] == found[0]), None
    names = ", ".join(q(c["name"]) for c in comps)
    if not found:
        return None, f"В «{q(subject['name'])}» нет компонента «{q(query)}». Есть: {names}"
    return None, f"«{q(query)}» неоднозначно: {', '.join(q(n) for n in found)}"


@router.message(Command("grades"))
@router.message(F.text == BTN_GRADES)
async def show_grades(message: Message, db: Database, state: FSMContext):
    await state.clear()
    subjects = db.subjects(message.from_user.id)
    if not subjects:
        return await message.answer(GRADES_HELP)
    reports = [subject_report(db, s) for s in subjects]
    await message.answer("\n\n".join(reports) + "\n\n<i>Итог считаю с арифметическим округлением. Команды — /gradeshelp</i>")


@router.message(Command("gradeshelp"))
async def grades_help(message: Message):
    await message.answer(GRADES_HELP)


@router.message(Command("formula"))
async def set_formula(message: Message, command: CommandObject, db: Database):
    if not command.args:
        return await message.answer(GRADES_HELP)
    try:
        name, comps = parse_formula(command.args)
    except ValueError as e:
        return await message.answer(f"Ошибка: {q(str(e))}\nПример: <code>/formula Матан: КР 0.3, экзамен 0.5, ДЗ 0.2</code>")
    uid = message.from_user.id
    existing = match_name(name, [s["name"] for s in db.subjects(uid)])
    if len(existing) == 1 and existing[0].casefold() == name.casefold():
        name = existing[0]
    db.set_formula(uid, name, comps)
    subject, _ = _find_subject(db, uid, name)
    await message.answer("Формула сохранена 👌\n\n" + subject_report(db, subject))


@router.message(Command("grade"))
async def add_grade(message: Message, command: CommandObject, db: Database):
    usage = "Формат: <code>/grade матан КР 5.6</code> или <code>/grade матан ДЗ 8 9 7</code>"
    tokens = (command.args or "").split()
    values: list[float] = []
    while tokens and parse_num(tokens[-1]) is not None:
        values.insert(0, parse_num(tokens.pop()))
    if not values or len(tokens) < 2:
        return await message.answer(usage)
    if any(not 0 <= v <= 10 for v in values):
        return await message.answer("Оценки по 10-балльной шкале: от 0 до 10.")

    uid = message.from_user.id
    subject, comp_query, err = _split_subject_component(db, uid, tokens)
    if err:
        return await message.answer(err)
    comp, err = _find_component(db, subject, comp_query)
    if err:
        return await message.answer(err)
    db.add_grades(comp["id"], values)
    await message.answer(f"Записал {', '.join(fmt_num(v) for v in values)} → {q(comp['name'])}\n\n"
                         + subject_report(db, subject))


@router.message(Command("delgrade"))
async def del_grade(message: Message, command: CommandObject, db: Database):
    tokens = (command.args or "").split()
    if len(tokens) < 2:
        return await message.answer("Формат: <code>/delgrade матан КР</code>")
    uid = message.from_user.id
    subject, comp_query, err = _split_subject_component(db, uid, tokens)
    if err:
        return await message.answer(err)
    comp, err = _find_component(db, subject, comp_query)
    if err:
        return await message.answer(err)
    removed = db.pop_grade(comp["id"])
    if removed is None:
        return await message.answer("Там и так пусто.")
    await message.answer(f"Убрал {fmt_num(removed)} из «{q(comp['name'])}»\n\n" + subject_report(db, subject))


@router.message(Command("delsubject"))
async def del_subject(message: Message, command: CommandObject, db: Database):
    if not command.args:
        return await message.answer("Формат: <code>/delsubject матан</code>")
    subject, err = _find_subject(db, message.from_user.id, command.args.strip())
    if err:
        return await message.answer(err)
    db.delete_subject(message.from_user.id, subject["id"])
    await message.answer(f"Удалил «{q(subject['name'])}» со всеми оценками.")
