"""Напоминания Кадгара: недельный сброс (EU) и Ярмарка Новолуния.

Запускается каждый час (reminders.yml) и шлёт сообщение один раз для каждого события,
отметки хранятся в reminders/state.json. Вебхук: DISCORD_WEBHOOK_NEWS
(если его нет — DISCORD_WEBHOOK_GUIDES).

Ярмарка в WoW Forever идёт по классическому расписанию: шатры ставят в первую пятницу
месяца, открывается в следующий понедельник и работает до воскресенья. Первая ярмарка —
ноябрь 2026 в Элвиннском лесу, дальше Элвинн и Мулгор чередуются каждый месяц.
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from discord_full import _send

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "reminders" / "state.json"
ICON = "https://wow.zamimg.com/images/wow/icons/large/{}.jpg"
BOT = {"username": "Кадгар", "avatar_url": ICON.format("quest_khadgar")}
AUTHOR = {"name": "Кадгар, хранитель знаний Кирин-Тора", "icon_url": ICON.format("quest_khadgar")}
RESET_HOUR_UTC = 4  # EU: еженедельный сброс в среду в 04:00 UTC


def faire_dates(year: int, month: int):
    first = date(year, month, 1)
    friday = first + timedelta(days=(4 - first.weekday()) % 7)
    monday = friday + timedelta(days=3)
    return friday, monday, monday + timedelta(days=6)


def faire_place(year: int, month: int) -> str:
    months = (year - 2026) * 12 + (month - 11)
    return "Элвиннском лесу, у Златоземья" if months % 2 == 0 else "Мулгоре, у Громового Утёса"


def embed(title, text, icon, color):
    return {"author": AUTHOR, "title": title, "description": text, "color": color,
            "thumbnail": {"url": ICON.format(icon)},
            "footer": {"text": "Напоминание Кадгара · WoW Forever EU", "icon_url": ICON.format("inv_misc_pocketwatch_01")},
            "timestamp": datetime.now(timezone.utc).isoformat()}


def due_events(now: datetime):
    today, wd, h = now.date(), now.weekday(), now.hour
    week = today.isocalendar()
    if wd == 1 and h >= 17:  # вторник вечером
        yield f"reset-soon-{week[0]}-{week[1]}", embed(
            "⏳ Завтра недельный сброс",
            "*«Время — самый редкий реагент. Не тратьте его зря.»*\n\n"
            "Успейте закрыть рейды и еженедельные задания: в среду в 07:00 по Москве всё обнулится.",
            "spell_holy_borrowedtime", 0xFF8000)
    if wd == 2 and h >= RESET_HOUR_UTC:  # среда утром
        yield f"reset-{week[0]}-{week[1]}", embed(
            "🔄 Недельный сброс",
            "*«Новая неделя — новые подвиги. Азерот ждёт, герои!»*\n\n"
            "🏰 Рейды и подземелья снова открыты\n"
            "📜 Еженедельные задания обновились — на максимальном уровне награда до 100 🟡\n"
            "🗡 Собирайте отряд на доске объявлений",
            "inv_misc_key_14", 0xFFD100)
    friday, monday, sunday = faire_dates(today.year, today.month)
    place = faire_place(today.year, today.month)
    if today == friday and h >= 8:
        yield f"faire-setup-{today}", embed(
            "🎪 Ярмарка Новолуния ставит шатры",
            f"*«Подходите, подходите! Чудеса со всех концов света!»*\n\n"
            f"Шатры уже видны в {place}. Ярмарка откроется в понедельник, "
            f"{monday:%d.%m}, и продлится до воскресенья, {sunday:%d.%m}.\n"
            "Готовьте карты Новолуния и предметы для обмена на билеты.",
            "inv_misc_ticket_darkmoon_01", 0xA335EE)
    if today == monday and h >= 8:
        yield f"faire-open-{today}", embed(
            "🎪 Ярмарка Новолуния открыта!",
            f"*«Судьба в руках Сейджа — выберите своё благословение!»*\n\n"
            f"Ярмарка работает в {place} до воскресенья, {sunday:%d.%m}.\n"
            "🔮 Баф Сейджа (+10% урона на 2 часа) действует в открытом мире, но не в рейдах\n"
            "🎟 Билеты, мини-игры и репутация с Ярмаркой Новолуния",
            "inv_misc_ticket_darkmoon_01", 0xA335EE)
    if today == sunday and h >= 8:
        yield f"faire-last-{today}", embed(
            "🎪 Последний день Ярмарки Новолуния",
            f"Сегодня ярмарка в {place} закрывается. Успейте сдать билеты и получить баф Сейджа!",
            "inv_misc_ticket_darkmoon_01", 0xA335EE)


def main() -> int:
    hook = (os.environ.get("DISCORD_WEBHOOK_NEWS") or os.environ.get("DISCORD_WEBHOOK_GUIDES") or "").strip()
    state = json.loads(STATE.read_text("utf-8")) if STATE.exists() else {}
    now = datetime.now(timezone.utc)
    if os.environ.get("TEST_REMINDER"):  # ручная проверка: прислать пример
        events = [(f"test-{now.isoformat()}", embed("🔄 Проверка напоминаний", "Кадгар на связи. Напоминания работают.",
                                                    "inv_misc_pocketwatch_01", 0xFFD100))]
    else:
        events = list(due_events(now))
    for key, emb in events:
        if key in state:
            continue
        if hook:
            _send(hook, {**BOT, "embeds": [emb], "allowed_mentions": {"parse": []}, "flags": 4096})
        print("sent", key)
        state[key] = int(now.timestamp())
    cutoff = now.timestamp() - 90 * 86400
    state = {k: v for k, v in state.items() if v >= cutoff and not k.startswith("test-")}
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
