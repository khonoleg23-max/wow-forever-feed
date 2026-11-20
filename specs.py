"""Ветки талантов WoW Forever: русские названия (как в клиенте), ветка для прокачки по умолчанию,
советованные таланты и план по уровням для каждой из 27 веток.

Для ветки по умолчанию советы написаны руками (TALENTS в kadgar_quiz.py, «*» в addon_src/notes).
Для остальных — все таланты ветки, кроме PvP/утилитарных (SKIP_TAL), по рядам: ряд r открывается на 10+5r уровне.
"""

import json
from pathlib import Path

SRC = Path(__file__).parent / "addon_src"

# порядок веток как в игре: (ключ в данных Wowhead, название в клиенте, коротко — для кого)
SPECS = {
    "war": [("Arms", "Оружие", "двуручное оружие, «Смертельный удар»"),
            ("Fury", "Неистовство", "два оружия, «Кровожадность», много ярости"),
            ("Protection", "Защита", "щит, танк в подземельях")],
    "pal": [("Holy", "Свет", "лекарь"),
            ("Protection", "Защита", "щит, танк"),
            ("Combat", "Воздаяние", "двуручное оружие, урон")],
    "hun": [("BeastMastery", "Чувство зверя", "сильный питомец"),
            ("Marksmanship", "Стрельба", "урон из лука и ружья"),
            ("Survival", "Выживание", "ловушки, ближний бой, ловкость")],
    "rog": [("Assassination", "Ликвидация", "яды и критические удары"),
            ("Combat", "Бой", "надёжный урон"),
            ("Subtlety", "Скрытность", "засады, контроль, PvP")],
    "pri": [("Discipline", "Послушание", "щиты, мана, поддержка"),
            ("Holy", "Свет", "лекарь"),
            ("Shadow", "Темная магия", "урон, «Облик Тьмы»")],
    "sha": [("ElementalCombat", "Стихии", "урон заклинаниями"),
            ("Enhancement", "Совершенствование", "ближний бой"),
            ("Restoration", "Исцеление", "лекарь")],
    "mag": [("Arcane", "Тайная магия", "мана и тайные заклинания"),
            ("Fire", "Огонь", "большой урон огнём"),
            ("Frost", "Лед", "замедления и контроль")],
    "wlk": [("Curses", "Колдовство", "урон со временем, «высасывание»"),
            ("Summoning", "Демонология", "сильный демон-помощник"),
            ("Destruction", "Разрушение", "прямой урон огнём и тьмой")],
    "dru": [("Balance", "Баланс", "урон заклинаниями издалека"),
            ("FeralCombat", "Сила зверя", "кошка — урон, медведь — танк"),
            ("Restoration", "Исцеление", "лекарь")],
}

# ветка для прокачки по умолчанию (1–3)
DEFAULT = {"war": 1, "pal": 3, "hun": 1, "rog": 2, "pri": 3, "sha": 2, "mag": 3, "wlk": 1, "dru": 2}

# таланты, которые не советуем при прокачке (PvP, редкая польза)
SKIP_TAL = {
    12323, 20504,                       # Неистовство: Пронзительный вой, Улучшенный перехват
    12313, 12962, 12311,                # Защита воина: разоружение, Железная воля, удар щитом
    415370, 19503, 19407,               # Стрельба
    13958, 13975, 30894, 1310728,       # Скрытность
    11255, 29441, 11210,                # Тайная магия
    11094,                              # Огонь
    20711,                              # Свет жреца
    14750,                              # Послушание: Улучшенное сожжение маны
    17123,                              # Исцеление друида
    16184,                              # Исцеление шамана
    17917,                              # Разрушение
    9453, 1328370, 9799,                # Воздаяние
    1328546, 20174,                     # Защита паладина
    24293,                              # Выживание
}

BANDS = [((0, 1), "10–19 ур."), ((2, 3), "20–29 ур."), ((4, 5), "30–39 ур."), ((6, 9), "40+ ур.")]


def _digest():
    return json.loads((SRC / "digest.json").read_text(encoding="utf-8"))


def _star_ids(cls: str) -> set:
    out = set()
    for line in (SRC / "notes" / f"{cls}.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("*"):
            out.add(int(line[1:].split("|")[0]))
    return out


def tree_talents(cls: str, i: int, dig=None) -> list:
    dig = dig or _digest()
    key = SPECS[cls][i - 1][0]
    ts = [t for t in dig[cls]["talents"] if t["tree"] == key]
    return sorted(ts, key=lambda t: (t["row"], t["col"]))


def rec_ids(cls: str, i: int, dig=None) -> list:
    """советованные таланты ветки"""
    if i == DEFAULT[cls]:
        return sorted(_star_ids(cls))
    return [t["id"] for t in tree_talents(cls, i, dig) if t["id"] not in SKIP_TAL]


def plan(cls: str, i: int, talents_default=None, dig=None) -> list:
    """[(с уровня, совет)] для ветки"""
    if i == DEFAULT[cls] and talents_default is not None:
        return list(talents_default[cls])
    ts = [t for t in tree_talents(cls, i, dig) if t["id"] not in SKIP_TAL]
    out = []
    for (a, b), _ in BANDS:
        names = [f"**{t['ru']}**" + (f" {t['max']}/{t['max']}" if t["max"] > 1 else "")
                 for t in ts if a <= t["row"] <= b]
        if names:
            out.append((10 + 5 * a, ", ".join(names) + "."))
    return out


def spec_name(cls: str, i: int) -> str:
    return SPECS[cls][i - 1][1]
