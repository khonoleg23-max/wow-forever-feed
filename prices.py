"""Трекер цен аукциона WoW Forever (EU) по данным TheWoWDB.

Каждый запуск снимает самую низкую цену выкупа и количество лотов по списку товаров,
копит историю в prices/history.json и:
  * раз в день (после 15:00 UTC) присылает в Discord сводку изменений за сутки и неделю;
  * сразу присылает тревогу, если цена резко сдвинулась относительно вчерашней.

Сообщения уходят в канал профессий через вебхук DISCORD_WEBHOOK_PROFESSIONS (тихо, без пушей).
Отчёты по профессиям (выгода крафта + цены материалов) уходят в ветки канала: список веток
и профессий для ежедневной рассылки — в prices/config.json, рецепты — prices/recipes.json.
TheWoWDB разрешает личное некоммерческое использование; аукцион снимается по категориям с паузами.
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
DIGEST_HOUR_UTC = 13  # сводка с планового прогона в 13:17 UTC (16:17 МСК, 18:17 по UTC+5)
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

# ---- профессии: рецепты WoW Forever с Wowhead (prices/recipes.json) ----
RECIPES_FILE = DATA / "recipes.json"
CONFIG = DATA / "config.json"
PROFESSIONS = {
    "alchemy": "⚗️ Алхимия",
    "blacksmithing": "🔨 Кузнечное дело",
    "enchanting": "✨ Наложение чар",
    "engineering": "⚙️ Инженерное дело",
    "leatherworking": "🐾 Кожевничество",
    "tailoring": "🧵 Портняжное дело",
    "mining": "⛏ Горное дело",
    "cooking": "🍳 Кулинария",
    "firstaid": "🩹 Первая помощь",
}
# ---- оформление в стиле WoW ----
ICON = "https://wow.zamimg.com/images/wow/icons/large/{}.jpg"
PROF_ICON = {
    "alchemy": "trade_alchemy", "blacksmithing": "trade_blacksmithing", "enchanting": "trade_engraving",
    "engineering": "trade_engineering", "leatherworking": "inv_misc_armorkit_17", "tailoring": "trade_tailoring",
    "mining": "trade_mining", "cooking": "inv_misc_food_15", "firstaid": "spell_holy_sealofsacrifice",
}
PROF_QUOTE = {
    "alchemy": "Зелье, сваренное вовремя, спасло больше героев, чем любой меч.",
    "blacksmithing": "Хороший клинок рождается в огне, а хорошая сделка — на аукционе.",
    "enchanting": "Магия любит точность. Как и золото.",
    "engineering": "Если что-то взорвалось — значит, работает. Почти.",
    "leatherworking": "Шкура зверя — лучший доспех для того, кто умеет её выделать.",
    "tailoring": "Даже архимаг начинал с простой льняной мантии.",
    "mining": "Глубины Азерота щедры к тем, кто не боится кирки.",
    "cooking": "Даже архимагу нужно хорошо поесть перед походом в Огненные Недра.",
    "firstaid": "Бинт в нужную минуту стоит дороже эпического лута.",
}
# цвета качества предметов WoW
Q_EPIC, Q_RARE, Q_LEGENDARY, Q_GOLD = 0xA335EE, 0x0070DD, 0xFF8000, 0xFFD100
AUTHOR = {"name": "Кадгар, хранитель знаний Кирин-Тора",
          "icon_url": "https://wow.zamimg.com/images/wow/icons/large/quest_khadgar.jpg"}
FOOTER_ICON = ICON.format("inv_misc_coin_01")


def wow_embed(embed: dict, color: int, icon: str | None = None) -> dict:
    embed.setdefault("author", AUTHOR)
    embed["color"] = color
    if icon:
        embed["thumbnail"] = {"url": ICON.format(icon)}
    embed["footer"] = {"text": embed.get("footer", {}).get("text", ""), "icon_url": FOOTER_ICON}
    embed["timestamp"] = datetime.now(timezone.utc).isoformat()
    return embed


# товары у торговца (item id -> медь), примерно; берётся меньшая из цены торговца и аукциона
VENDOR = {
    3371: 4, 3372: 16, 8925: 20,                               # склянки
    2320: 10, 2321: 100, 4291: 500, 8343: 2000, 14341: 5000,   # нитки
    2678: 10, 2692: 40, 3713: 160, 159: 25,                    # специи, вода
    2880: 100, 3466: 2000,                                     # флюс
    4289: 50, 2324: 25, 2604: 50, 6260: 50, 2325: 1000, 4340: 350,
    4341: 500, 4342: 2500, 6261: 1000, 10290: 2500,            # соль, отбеливатель, краски
    4399: 200, 4400: 2000, 6217: 124, 4470: 38, 11291: 4500,   # ложа, стержни, древесина
}
AH_CUT = 0.05  # аукцион забирает 5% с продажи
# категории аукциона TheWoWDB: расходуемое, сумки, реагенты, боеприпасы, хозяйственные товары,
# колчаны, разное — каждый запуск; оружие и броня (~70 страниц) — только в запуск со сводкой
AH_CLASSES = [0, 1, 5, 6, 7, 11, 15]
GEAR_CLASSES = [2, 4]
PAGE_SIZE = 50
MAX_PAGES = 70


ROW_RE = re.compile(
    r'data-copper="(\d+)".*?data-wgf-item="item=(\d+)"[^>]*>(?:<img[^>]*>)?([^<]+)</a>'
    r'.*?class="qty-cell">([\d,]+)(?:<span class="ah-subtext"> ([\d,]+) listing)?',
    re.DOTALL,
)


def fetch_page(cls: int, page: int) -> tuple[list, int]:
    q = {"class": cls, "realm": "forever", "region": REGION}
    if page > 1:
        q["page"] = page
    req = urllib.request.Request(SEARCH + urllib.parse.urlencode(q), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8", "ignore")
    start = text.find('<table class="ah-table"')
    table = text[start:text.find("</table>", start)] if start >= 0 else ""
    rows = []
    for tr in re.findall(r"<tr>.*?</tr>", table, re.DOTALL):  # только основная таблица, построчно
        m = ROW_RE.search(tr)
        if m:
            c, i, t, q_, l = m.groups()
            rows.append({"id": int(i), "name": html.unescape(t).strip(), "price": int(c),
                         "qty": int(q_.replace(",", "")), "listings": int((l or "1").replace(",", ""))})
    return rows, table.count("<tr>") - 1  # строк в таблице без заголовка


def snapshot_ah(classes) -> dict[int, dict]:
    """Аукцион по категориям (по 50 товаров на странице), с паузами между запросами."""
    snap: dict[int, dict] = {}
    for cls in classes:
        seen_first = set()
        for page in range(1, MAX_PAGES + 1):
            rows = None
            for attempt in range(2):
                try:
                    rows, n_rows = fetch_page(cls, page)
                    break
                except Exception as exc:
                    print(f"  class {cls} page {page}: error {exc}", file=sys.stderr)
                    time.sleep(30)
            time.sleep(3)  # бережно к сайту
            if not rows or rows[0]["id"] in seen_first:
                break  # ошибка или страницы закончились (сайт повторяет последнюю)
            seen_first.add(rows[0]["id"])
            for row in rows:
                old = snap.get(row["id"])
                if not old or row["price"] < old["price"]:
                    snap[row["id"]] = row
            if n_rows < PAGE_SIZE:
                break
        print(f"  class {cls}: {page} pages, items so far {len(snap)}")
    return snap


def load_recipes():
    data = json.loads(RECIPES_FILE.read_text("utf-8"))
    return data["recipes"], {int(k): v for k, v in data["names"].items()}


def item_link(item_id: int, name: str) -> str:
    return f"[{name}](https://thewowdb.com/wow-forever/item/{item_id}/)"


def unit_cost(item_id: int, snap) -> int | None:
    prices = [p for p in (VENDOR.get(item_id), snap.get(item_id, {}).get("price")) if p]
    return min(prices) if prices else None


def profession_report(prof: str, recipes, names, snap) -> list[dict]:
    """Два эмбеда: выгода крафта и цены материалов этой профессии."""
    title = PROFESSIONS[prof]
    rows, no_sale, no_mats = [], 0, 0
    mat_use: dict[int, int] = {}
    for skill, product, count, reagents in recipes.get(prof, []):
        for rid, _ in reagents:
            mat_use[rid] = mat_use.get(rid, 0) + 1
        sale = snap.get(product)
        if not sale:
            no_sale += 1
            continue
        costs = [unit_cost(rid, snap) for rid, _ in reagents]
        if None in costs:
            no_mats += 1
            continue
        cost = sum(c * n for c, (_, n) in zip(costs, reagents)) / max(1, count)
        profit = sale["price"] * (1 - AH_CUT) - cost
        margin = round(profit * 100 / cost) if cost else 0
        ru = names.get(product, [sale["name"]] * 2)[1]
        mark, sign = ("✅", "+") if profit > 0 else ("❌", "−")
        rows.append((profit, f"{mark} **{item_link(product, ru)}** · навык {skill}"
                             + (f" · ⚠️ всего {sale['qty']} шт." if sale["qty"] <= 3 else "")
                             + f"\n\u2003продажа {money(sale['price'])} · реагенты {money(int(cost))} → "
                             f"**{sign}{money(int(abs(profit)))}** ({'+' if margin > 0 else ''}{margin}%)"))
    rows.sort(key=lambda r: r[0], reverse=True)
    good = [line for p, line in rows if p > 0]
    bad = [line for p, line in rows if p <= 0]
    lines = good[:15] + bad[:3]
    desc = f"*«{PROF_QUOTE[prof]}»*\n\n"
    for line in lines:
        if len(desc) + len(line) + 1 > 3700:
            break
        desc += line + "\n"
    if not lines:
        desc += "Сейчас на аукционе нет готовых предметов этой профессии с известными ценами реагентов.\n"
    desc += (f"\n📜 Выгодно: **{len(good)}** · в минус: **{len(bad)}** · нет на аукционе: {no_sale}"
             + (f" · нет цены реагентов: {no_mats}" if no_mats else ""))
    craft = wow_embed({"title": f"{title} — свиток выгодных рецептов", "description": desc,
                       "footer": {"text": "Аукционный дом · цена − 5% комиссии − реагенты · рецепты WoW Forever"}},
                      Q_EPIC, PROF_ICON[prof])

    mats = sorted(mat_use, key=lambda i: -mat_use[i])
    mlines = []
    for rid in mats:
        price = unit_cost(rid, snap)
        if price is None:
            continue
        ru = names.get(rid, ["?", "?"])[1]
        if rid in snap:
            s = snap[rid]
            vend = " · 🏪 у торговца дешевле" if VENDOR.get(rid, 1e12) < s["price"] else ""
            mlines.append(f"📦 {item_link(rid, ru)} — **{money(price)}**{vend} · {s['qty']:,} шт.".replace(",", " "))
        else:
            mlines.append(f"🏪 {ru} — **{money(price)}** у торговца")
        if len(mlines) >= 30:
            break
    mdesc = ""
    for line in mlines:
        if len(mdesc) + len(line) + 1 > 3800:
            break
        mdesc += line + "\n"
    mats_embed = wow_embed({"title": f"{title} — реагенты на аукционе",
                            "description": mdesc or "Реагентов на аукционе нет.",
                            "footer": {"text": "Аукционный дом · самые ходовые реагенты · цена за штуку"}},
                           Q_RARE)
    return [craft, mats_embed]


# иконки монет — эмодзи сервера WoW Forever (вебхуки сервера могут их использовать)
COIN_GOLD = "<:gold:1570696828679094365>"
COIN_SILVER = "<:silver:1570697224638169192>"
COIN_COPPER = "<:copper:1570697350047858779>"


def money(c: int) -> str:
    """Деньги как в игре: золото, серебро, медь — иконками монет WoW."""
    g, sv, m = c // 10000, c // 100 % 100, c % 100
    parts = []
    if g:
        parts.append(f"{g:,}{COIN_GOLD}".replace(",", " "))
    if sv:
        parts.append(f"{sv}{COIN_SILVER}")
    if m or not parts:
        parts.append(f"{m}{COIN_COPPER}")
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


def post(hook, embed, thread: str | None = None) -> bool:
    """Отправка одного embed; ошибка Discord не роняет весь прогон (история цен всё равно сохранится)."""
    embed.setdefault("color", 0xE0A933)
    try:
        _send(hook, {**BOT, "embeds": [embed], "allowed_mentions": {"parse": []}, "flags": 4096},
              f"&thread_id={thread}" if thread else "")
    except Exception as e:  # noqa: BLE001
        body = e.read().decode("utf-8", "replace")[:500] if hasattr(e, "read") else ""
        print(f"!! Discord не принял сообщение «{embed.get('title', '')}»: {e} {body}")
        return False
    finally:
        time.sleep(1)
    return True


def chunk_fields(fields: list[dict], budget: int = 4500) -> list[list[dict]]:
    """Делит поля на части: в одном embed Discord — не больше 25 полей и 6000 символов всего."""
    parts, cur, size = [], [], 0
    for f in fields:
        n = len(f["name"]) + len(f["value"])
        if cur and (size + n > budget or len(cur) >= 25):
            parts.append(cur)
            cur, size = [], 0
        cur.append(f)
        size += n
    if cur:
        parts.append(cur)
    return parts


def main() -> int:
    DATA.mkdir(exist_ok=True)
    history = load(HISTORY, {})
    state = load(STATE, {"last_digest": 0, "alerts": {}})
    now = int(time.time())

    hour = datetime.now(timezone.utc).hour
    force_digest = os.environ.get("FORCE_DIGEST") == "1"
    asked = os.environ.get("PROFESSION", "").strip()
    today_utc = datetime.now(timezone.utc).date()
    last_day = datetime.fromtimestamp(state.get("last_auto_digest", 0), timezone.utc).date()
    auto_due = hour >= DIGEST_HOUR_UTC and last_day < today_utc  # раз в календарный день, ручные запуски не сдвигают
    digest_due = force_digest or auto_due
    gear = digest_due or asked in ("all", "blacksmithing", "leatherworking", "tailoring", "engineering")
    ah = snapshot_ah(AH_CLASSES + (GEAR_CLASSES if gear else []))
    by_name: dict[str, dict] = {}
    for row in ah.values():
        key = row["name"].lower()
        if key not in by_name or row["price"] < by_name[key]["price"]:
            by_name[key] = row
    snapshot = {}
    for en, ru, group in WATCHLIST:
        item = by_name.get(en.lower())
        if not item:
            print(f"  {en}: нет на аукционе")
            continue
        snapshot[en] = item
        h = history.setdefault(en, {"id": item["id"], "points": []})
        h["id"] = item["id"]
        h["points"].append([now, item["price"], item["qty"]])
        h["points"] = [p for p in h["points"] if p[0] >= now - KEEP_DAYS * 86400]

    HISTORY.write_text(json.dumps(history, ensure_ascii=False, separators=(",", ":")), "utf-8")

    hook = os.environ.get("DISCORD_WEBHOOK_PROFESSIONS", "").strip()

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
        post(hook, wow_embed({"title": "⚠️ Гоблины аукциона взбудоражены!",
                              "description": "*«Цены скачут, как гном на ракетном ранце.»*\n\n" + "\n".join(lines),
                              "footer": {"text": "Аукционный дом · WoW Forever EU · данные TheWoWDB"}},
                             Q_LEGENDARY, "inv_misc_bomb_02"))

    # ---- ежедневная сводка ----
    digest_sent = False
    if hook and digest_due:
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
        parts = chunk_fields(fields)
        for i, part in enumerate(parts):
            emb = {"title": f"💰 Вести с аукциона — {today}" + (f" ({i + 1}/{len(parts)})" if len(parts) > 1 else ""),
                   "fields": part, "footer": {"text": "Аукционный дом · WoW Forever EU · выгода крафта — в ветках профессий"}}
            if i == 0:
                emb["description"] = ("*«Золото не пахнет, но всегда знает, куда течь.»*\n"
                                      "Самая низкая цена выкупа за штуку · стрелки — к прошлым суткам и неделе.")
            post(hook, wow_embed(emb, Q_GOLD, "inv_misc_coin_01" if i == 0 else None))
        state["last_digest"] = now
        if auto_due:
            state["last_auto_digest"] = now
        digest_sent = True

    # ---- отчёты по профессиям: каждая в своей ветке канала ----
    config = load(CONFIG, {"daily": list(PROFESSIONS), "threads": {}})
    if asked == "all":
        todo = list(PROFESSIONS)
    elif asked in PROFESSIONS:
        todo = [asked]
    elif digest_sent:
        todo = [p for p in config.get("daily", []) if p in PROFESSIONS]
    else:
        todo = []
    if hook and todo:
        recipes, names = load_recipes()
        for prof in todo:
            thread = config.get("threads", {}).get(prof)
            for embed in profession_report(prof, recipes, names, ah):
                post(hook, embed, thread)

    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), "utf-8")
    print(f"snapshot: {len(snapshot)} items, alerts: {len(alerts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
