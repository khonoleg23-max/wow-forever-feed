"""Трекер цен аукциона WoW Forever (EU) по данным TheWoWDB.

Каждый запуск снимает самую низкую цену выкупа и количество лотов по списку товаров,
копит историю в prices/history.json и:
  * раз в день (после 15:00 UTC) присылает в Discord сводку изменений за сутки и неделю;
  * сразу присылает тревогу, если цена резко сдвинулась относительно вчерашней.

Сообщения уходят в канал профессий через вебхук DISCORD_WEBHOOK_PROFESSIONS (тихо, без пушей).
TheWoWDB разрешает личное некоммерческое использование; запросы идут с паузой, по одному на товар.
"""

import html
import json
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from discord_full import _send

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "prices"
HISTORY = DATA / "history.json"
STATE = DATA / "state.json"
SEARCH = "https://thewowdb.com/wow-forever/auction-house/?"
REGION = "eu"
KEEP_DAYS = 45
ALERT_PCT = 40  # тревога, если цена ушла больше чем на 40% от вчерашней
ALERT_COOLDOWN_H = 12
DIGEST_HOUR_UTC = 15
UA = "Mozilla/5.0 (compatible; wow-forever-ru-feed/1.0; personal price tracker)"
BOT = {"username": "Кадгар", "avatar_url": "https://wow.zamimg.com/images/wow/icons/large/quest_khadgar.jpg"}

# (английское название для поиска, русское название, группа)
WATCHLIST = [
    ("Peacebloom", "Мироцвет", "🌿 Травы"),
    ("Silverleaf", "Сребролист", "🌿 Травы"),
    ("Earthroot", "Земляной корень", "🌿 Травы"),
    ("Mageroyal", "Магороза", "🌿 Травы"),
    ("Briarthorn", "Острошип", "🌿 Травы"),
    ("Stranglekelp", "Удавник", "🌿 Травы"),
    ("Bruiseweed", "Синячник", "🌿 Травы"),
    ("Kingsblood", "Королевская кровь", "🌿 Травы"),
    ("Liferoot", "Корень жизни", "🌿 Травы"),
    ("Goldthorn", "Златошип", "🌿 Травы"),
    ("Khadgar's Whisker", "Кадгаров ус", "🌿 Травы"),
    ("Sungrass", "Солнечник", "🌿 Травы"),
    ("Firebloom", "Огнецвет", "🌿 Травы"),
    ("Gromsblood", "Кровь Грома", "🌿 Травы"),
    ("Golden Sansam", "Золотой сансам", "🌿 Травы"),
    ("Dreamfoil", "Снолист", "🌿 Травы"),
    ("Mountain Silversage", "Горный серебряный шалфей", "🌿 Травы"),
    ("Plaguebloom", "Чумоцвет", "🌿 Травы"),
    ("Black Lotus", "Чёрный лотос", "🌿 Травы"),
    ("Copper Ore", "Медная руда", "⛏ Руда"),
    ("Tin Ore", "Оловянная руда", "⛏ Руда"),
    ("Iron Ore", "Железная руда", "⛏ Руда"),
    ("Mithril Ore", "Мифриловая руда", "⛏ Руда"),
    ("Thorium Ore", "Ториевая руда", "⛏ Руда"),
    ("Arcane Crystal", "Тайный кристалл", "⛏ Руда"),
    ("Linen Cloth", "Льняная ткань", "🧵 Ткань и кожа"),
    ("Wool Cloth", "Шерстяная ткань", "🧵 Ткань и кожа"),
    ("Silk Cloth", "Шёлк", "🧵 Ткань и кожа"),
    ("Mageweave Cloth", "Магическая ткань", "🧵 Ткань и кожа"),
    ("Runecloth", "Руническая ткань", "🧵 Ткань и кожа"),
    ("Light Leather", "Лёгкая кожа", "🧵 Ткань и кожа"),
    ("Medium Leather", "Средняя кожа", "🧵 Ткань и кожа"),
    ("Heavy Leather", "Толстая кожа", "🧵 Ткань и кожа"),
    ("Thick Leather", "Плотная кожа", "🧵 Ткань и кожа"),
    ("Rugged Leather", "Грубая кожа", "🧵 Ткань и кожа"),
    ("Strange Dust", "Странная пыль", "✨ Наложение чар"),
    ("Soul Dust", "Пыль души", "✨ Наложение чар"),
    ("Vision Dust", "Пыль видений", "✨ Наложение чар"),
    ("Dream Dust", "Пыль грёз", "✨ Наложение чар"),
    ("Illusion Dust", "Пыль иллюзий", "✨ Наложение чар"),
    ("Large Brilliant Shard", "Большой сверкающий осколок", "✨ Наложение чар"),
]

ROW_RE = re.compile(
    r'data-copper="(\d+)".*?data-wgf-item="item=(\d+)"[^>]*>(?:<img[^>]*>)?([^<]+)</a>'
    r'.*?class="qty-cell">([\d,]+)<span class="ah-subtext"> (\d+) listing',
    re.DOTALL,
)


def fetch_item(name: str):
    url = SEARCH + urllib.parse.urlencode({"q": name, "realm": "forever", "region": REGION})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        page = r.read().decode("utf-8", "ignore")
    for copper, item_id, title, qty, listings in ROW_RE.findall(page):
        if html.unescape(title).strip().lower() == name.lower():
            return {"id": int(item_id), "price": int(copper), "qty": int(qty.replace(",", "")), "listings": int(listings)}
    return None


def money(c: int) -> str:
    g, s, m = c // 10000, c // 100 % 100, c % 100
    parts = []
    if g:
        parts.append(f"{g}з")
    if s:
        parts.append(f"{s}с")
    if m or not parts:
        parts.append(f"{m}м")
    return " ".join(parts[:2])  # точность до двух монет хватает


def price_at(points, hours_ago, now):
    """Медиана цен в окне ±3 часа вокруг нужного момента (сглаживает разовые выбросы)."""
    target = now - hours_ago * 3600
    window = [p for t, p, _ in points if abs(t - target) <= 3 * 3600]
    if not window and points:
        older = [p for t, p, _ in points if t <= target]
        window = older[-1:] if older else []
    return statistics.median(window) if window else None


def pct(new, old):
    return None if not old else round((new - old) * 100 / old)


def arrow(p):
    if p is None:
        return "—"
    if p > 0:
        return f"▲{p}%"
    if p < 0:
        return f"▼{abs(p)}%"
    return "0%"


def load(path, default):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def post(hook, embed):
    embed.setdefault("color", 0xE0A933)
    _send(hook, {**BOT, "embeds": [embed], "allowed_mentions": {"parse": []}, "flags": 4096})
    time.sleep(1)


def main() -> int:
    DATA.mkdir(exist_ok=True)
    history = load(HISTORY, {})
    state = load(STATE, {"last_digest": 0, "alerts": {}})
    now = int(time.time())

    snapshot = {}
    for en, ru, group in WATCHLIST:
        try:
            item = fetch_item(en)
        except Exception as exc:
            print(f"  {en}: error {exc}", file=sys.stderr)
            item = None
        time.sleep(2)  # бережно к сайту
        if not item:
            print(f"  {en}: нет на аукционе")
            continue
        snapshot[en] = item
        h = history.setdefault(en, {"id": item["id"], "points": []})
        h["id"] = item["id"]
        h["points"].append([now, item["price"], item["qty"]])
        h["points"] = [p for p in h["points"] if p[0] >= now - KEEP_DAYS * 86400]
        print(f"  {en}: {money(item['price'])} x{item['qty']}")

    HISTORY.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")), "utf-8")

    hook = os.environ.get("DISCORD_WEBHOOK_PROFESSIONS", "").strip()
    force_digest = os.environ.get("FORCE_DIGEST") == "1"

    # ---- тревоги о резких скачках ----
    alerts = []
    for en, ru, group in WATCHLIST:
        if en not in snapshot:
            continue
        pts = history[en]["points"]
        day = price_at(pts[:-1], 24, now)
        change = pct(snapshot[en]["price"], day)
        last = state["alerts"].get(en, 0)
        if change is not None and abs(change) >= ALERT_PCT and now - last > ALERT_COOLDOWN_H * 3600:
            alerts.append((ru, en, snapshot[en], day, change))
            state["alerts"][en] = now
    if hook and alerts:
        lines = [
            f"{'📈' if c > 0 else '📉'} **{ru}** — {money(s['price'])} (было {money(int(d))}) **{arrow(c)}** · {s['qty']:,} шт.".replace(",", " ")
            for ru, en, s, d, c in alerts
        ]
        post(hook, {"title": "⚠️ Резкое изменение цен на аукционе", "description": "\n".join(lines),
                    "footer": {"text": "WoW Forever EU · данные TheWoWDB"}})

    # ---- ежедневная сводка ----
    hour = datetime.now(timezone.utc).hour
    if hook and (force_digest or (hour >= DIGEST_HOUR_UTC and now - state["last_digest"] > 20 * 3600)):
        groups: dict[str, list[str]] = {}
        for en, ru, group in WATCHLIST:
            if en not in snapshot:
                continue
            s, pts = snapshot[en], history[en]["points"]
            d1 = pct(s["price"], price_at(pts[:-1], 24, now))
            d7 = pct(s["price"], price_at(pts[:-1], 24 * 7, now))
            link = f"https://thewowdb.com/wow-forever/item/{s['id']}/"
            groups.setdefault(group, []).append(
                f"[{ru}]({link}) — **{money(s['price'])}** · сутки {arrow(d1)} · неделя {arrow(d7)} · {s['qty']:,} шт.".replace(",", " ")
            )
        fields = []
        for group, lines in groups.items():
            text, name = "", group
            for line in lines:  # лимит поля embed — 1024 символа
                if len(text) + len(line) + 1 > 1000:
                    fields.append({"name": name, "value": text})
                    text, name = "", "​"  # продолжение группы без нового заголовка
                text += line + "\n"
            fields.append({"name": name, "value": text})
        today = datetime.now(timezone.utc).strftime("%d.%m.%Y")
        post(hook, {"title": f"💰 Цены аукциона на {today}", "fields": fields[:25],
                    "description": "Самая низкая цена выкупа за штуку. Стрелки — изменение к прошлым суткам и неделе.",
                    "footer": {"text": "WoW Forever EU · данные TheWoWDB · Кадгар следит за аукционом"}})
        state["last_digest"] = now

    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
    print(f"snapshot: {len(snapshot)} items, alerts: {len(alerts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
