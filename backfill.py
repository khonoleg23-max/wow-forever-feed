"""Разовая загрузка архива: все статьи Wowhead по WoW Forever со старта беты (17.09.2026),
которых нет в обычной ленте. Статьи группируются по дням в дайджесты, чтобы не заспамить
канал сотнями постов. Результат: docs/archive.json, его подхватывает translate_feed.py.

Запуск: python backfill.py
"""

import html
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from translate_feed import CACHE_FILE, DOCS, PROFESSION_RE, fetch, google_translate

START = "2026/09/17"
LIST_URL = "https://www.wowhead.com/forever/news?page={}"
TZ = timezone(timedelta(hours=-6))  # Wowhead показывает время по US Central
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
MAX_BODY = 3500  # лимит описания embed в Discord 4096


def collect() -> list[dict]:
    posts, page = [], 1
    while page < 80:
        raw = fetch(LIST_URL.format(page)).decode("utf-8")
        m = re.search(r'id="data\.news\.newsData">(.*?)</script>', raw, re.DOTALL)
        batch = json.loads(m.group(1))["newsPosts"]
        if not batch:
            break
        posts += batch
        if min(p["postedFull"] for p in batch) < START:
            break
        page += 1
        time.sleep(1)
    print(f"pages: {page}, posts: {len(posts)}")
    return [p for p in posts if p["postedFull"] >= START]


def main() -> int:
    cache = json.loads(CACHE_FILE.read_text("utf-8")) if CACHE_FILE.exists() else {}
    known = {g.rsplit("=", 1)[-1] for g in cache}

    posts = [p for p in collect() if str(p["id"]) not in known]
    print(f"archive posts to add: {len(posts)}")

    groups: dict[tuple[str, bool], list[dict]] = defaultdict(list)
    for p in posts:
        dt = datetime.strptime(p["postedFull"], "%Y/%m/%d at %I:%M %p").replace(tzinfo=TZ)
        p["dt"] = dt
        groups[(dt.date().isoformat(), bool(PROFESSION_RE.search(p["title"])))].append(p)

    entries = []
    for (day, profs), items in sorted(groups.items()):
        items.sort(key=lambda p: p["dt"])
        lines = []
        for p in items:
            title_ru = google_translate(p["title"]) or p["title"]
            link = "https://www.wowhead.com" + p["postUrl"]
            lines.append(f'• <a href="{html.escape(link)}">{html.escape(title_ru)}</a>')
            time.sleep(0.3)
        d = items[0]["dt"]
        label = f"{d.day} {MONTHS[d.month - 1]}"
        # длинные дни делим на части, чтобы влезть в embed
        chunks, cur = [], []
        for line in lines:
            if cur and len("<br>".join(cur + [line])) > MAX_BODY:
                chunks.append(cur)
                cur = []
            cur.append(line)
        chunks.append(cur)
        for n, chunk in enumerate(chunks, 1):
            part = f" (часть {n})" if len(chunks) > 1 else ""
            kind = "профессии" if profs else "гайды и новости"
            entries.append(
                {
                    "guid": f"archive-{day}-{'prof' if profs else 'guides'}-{n}",
                    "title_ru": f"📚 Архив WoW Forever · {label}{part} — {kind}",
                    "body_html": "<br>".join(chunk),
                    "link": "https://www.wowhead.com/forever/news",
                    "pubDate": format_datetime(items[-1]["dt"] + timedelta(seconds=n)),
                    "image": items[0].get("thumbnailUrl"),
                    "professions": profs,
                    "count": len(chunk),
                }
            )
        print(f"  {day} {'prof' if profs else 'guides'}: {len(items)} статей")

    (DOCS / "archive.json").write_text(json.dumps(entries, ensure_ascii=False, indent=1), "utf-8")
    print(f"digests: {len(entries)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
