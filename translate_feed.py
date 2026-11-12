"""Переводит ленту Wowhead по WoW Forever на русский и делит её на две RSS-ленты:
docs/guides.xml (гайды, новости, хотфиксы) и docs/professions.xml (профессии).

Перевод: Claude API, если задан ANTHROPIC_API_KEY, иначе бесплатный онлайн-переводчик.
Уже переведённые записи хранятся в docs/cache.json, поэтому каждая статья переводится один раз.
"""

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

SOURCE_URL = "https://www.wowhead.com/news/rss/forever"
ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
CACHE_FILE = DOCS / "cache.json"
CACHE_LIMIT = 150
MODEL = "claude-opus-5-5"

PROFESSION_RE = re.compile(
    r"profession|alchem|blacksmith|enchant|engineer|herbalis|mining|skinning|tailor|"
    r"leatherwork|cooking|fishing|first aid|gathering|crafting|recipe|pattern|schematic|auction",
    re.IGNORECASE,
)

NS = {
    "media": "http://search.yahoo.com/mrss/",
    "content": "http://purl.org/rss/1.0/modules/content/",
}

UA = "Mozilla/5.0 (compatible; wow-forever-ru-feed/1.0)"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def strip_html(text: str) -> str:
    text = re.sub(r"<(br|p|li|h\d)[^>]*>", "\n", text or "", flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def parse_source(raw: bytes) -> list[dict]:
    root = ET.fromstring(raw)
    items = []
    for it in root.find("channel").findall("item"):
        media = it.find("media:content", NS)
        body = it.findtext("content:encoded", default="", namespaces=NS)
        desc = it.findtext("description", default="")
        items.append(
            {
                "guid": it.findtext("guid") or it.findtext("link"),
                "title": (it.findtext("title") or "").strip(),
                "link": (it.findtext("link") or "").strip(),
                "pubDate": (it.findtext("pubDate") or "").strip(),
                "image": media.get("url") if media is not None else None,
                "text": strip_html(body or desc),
            }
        )
    return items


# ---------- перевод ----------

PROMPT = """Ты переводишь новости и гайды World of Warcraft: Forever для русскоязычной гильдии.
Используй привычный игрокам сленг и устоявшиеся русские названия (данж, рейд, хотфикс, таланты, профессии, Портняжное дело, Алхимия и т.д.).
Имена собственные, названия заклинаний и предметов оставляй как в русской версии игры, если уверен, иначе оригиналом.

Сделай:
1. Перевод заголовка на русский.
2. Краткий пересказ статьи на русском: 2-5 коротких пунктов с главным (что изменилось, что важно игроку). Не больше 600 символов. Без вступлений.

Ответ строго в формате:
ЗАГОЛОВОК: <перевод заголовка>
ПЕРЕСКАЗ:
<пункты, каждый с новой строки, начиная с "• ">

Заголовок: {title}

Текст статьи:
{text}"""


def translate_claude(item: dict) -> tuple[str, str]:
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[
            {
                "role": "user",
                "content": PROMPT.format(title=item["title"], text=item["text"][:6000]),
            }
        ],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to translate this item")
    out = "".join(b.text for b in response.content if b.type == "text").strip()
    m = re.search(r"ЗАГОЛОВОК:\s*(.+?)\s*\n\s*ПЕРЕСКАЗ:\s*(.+)", out, re.DOTALL)
    if not m:
        raise RuntimeError(f"Unexpected answer format: {out[:200]}")
    return m.group(1).strip(), m.group(2).strip()


def google_translate(text: str) -> str:
    if not text:
        return ""
    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ru&dt=t&q="
        + urllib.parse.quote(text)
    )
    data = json.loads(fetch(url).decode("utf-8"))
    return "".join(part[0] for part in data[0] if part and part[0])


def translate_free(item: dict) -> tuple[str, str]:
    title = google_translate(item["title"])
    teaser = item["text"][:500]
    cut = teaser.rfind(".")
    if cut > 150:
        teaser = teaser[: cut + 1]
    return title, google_translate(teaser)


def translate(item: dict) -> tuple[str, str, str]:
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            title, summary = translate_claude(item)
            return title, summary, "claude"
        except Exception as exc:  # падаем на бесплатный перевод, чтобы лента не встала
            print(f"  Claude error, using free translator: {exc}", file=sys.stderr)
    title, summary = translate_free(item)
    return title, summary, "free"


# ---------- запись лент ----------


def build_rss(title: str, description: str, self_url: str, entries: list[dict]) -> bytes:
    ET.register_namespace("media", NS["media"])
    rss = ET.Element("rss", version="2.0")
    ch = ET.SubElement(rss, "channel")
    ET.SubElement(ch, "title").text = title
    ET.SubElement(ch, "link").text = "https://www.wowhead.com/forever"
    ET.SubElement(ch, "description").text = description
    ET.SubElement(ch, "language").text = "ru"
    ET.SubElement(ch, "lastBuildDate").text = format_datetime(datetime.now(timezone.utc))
    for e in entries:
        it = ET.SubElement(ch, "item")
        ET.SubElement(it, "title").text = e["title_ru"]
        ET.SubElement(it, "link").text = e["link"]
        ET.SubElement(it, "guid", isPermaLink="false").text = e["guid"]
        ET.SubElement(it, "pubDate").text = e["pubDate"]
        body = html.escape(e["summary_ru"]).replace("\n", "<br>")
        body += f'<br><br><a href="{html.escape(e["link"])}">Читать полностью на Wowhead (англ.)</a>'
        ET.SubElement(it, "description").text = body
        if e.get("image"):
            ET.SubElement(
                it, f"{{{NS['media']}}}content", url=e["image"], medium="image"
            )
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def main() -> int:
    DOCS.mkdir(exist_ok=True)
    cache = json.loads(CACHE_FILE.read_text("utf-8")) if CACHE_FILE.exists() else {}

    items = parse_source(fetch(SOURCE_URL))
    print(f"Source items: {len(items)}")

    new = 0
    for item in items:
        if item["guid"] in cache:
            continue
        print(f"  translating: {item['title']}")
        title_ru, summary_ru, engine = translate(item)
        cache[item["guid"]] = {
            "guid": item["guid"],
            "title_en": item["title"],
            "title_ru": title_ru,
            "summary_ru": summary_ru,
            "link": item["link"],
            "pubDate": item["pubDate"],
            "image": item["image"],
            "professions": bool(PROFESSION_RE.search(item["title"])),
            "engine": engine,
            "added": int(time.time()),
        }
        new += 1

    # порядок как в исходной ленте (сначала свежие)
    order = [i["guid"] for i in items]
    entries = [cache[g] for g in order if g in cache]

    guides = [e for e in entries if not e["professions"]]
    profs = [e for e in entries if e["professions"]]

    (DOCS / "guides.xml").write_bytes(
        build_rss(
            "WoW Forever — гайды и новости (RU)",
            "Перевод ленты Wowhead по WoW Forever: гайды, хотфиксы, новости.",
            "guides.xml",
            guides,
        )
    )
    (DOCS / "professions.xml").write_bytes(
        build_rss(
            "WoW Forever — профессии (RU)",
            "Перевод ленты Wowhead по WoW Forever: только профессии.",
            "professions.xml",
            profs,
        )
    )

    # держим кэш компактным: свежие по времени добавления
    if len(cache) > CACHE_LIMIT:
        keep = sorted(cache.values(), key=lambda e: e["added"], reverse=True)[:CACHE_LIMIT]
        keep_ids = {e["guid"] for e in keep} | set(order)
        cache = {k: v for k, v in cache.items() if k in keep_ids}

    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), "utf-8")
    (DOCS / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>WoW Forever RU feeds</title>'
        '<p><a href="guides.xml">guides.xml</a> · <a href="professions.xml">professions.xml</a></p>',
        "utf-8",
    )
    print(f"New translated: {new}; guides: {len(guides)}, professions: {len(profs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
