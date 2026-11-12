"""Полный русский перевод статьи и отправка в Discord через вебхук.

Текст статьи не публикуется на сайте (GitHub Pages открыт всем), а уходит сразу
в канал Discord. Длинные статьи делятся на несколько сообщений.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "tr", "ul", "ol", "table"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
EMBED_LIMIT = 3900  # лимит описания embed 4096
COLOR = 0x1E6FD9
BOT_NAME = "Кадгар"
BOT_AVATAR = "https://khonoleg23-max.github.io/wow-forever-feed/sage.png"


class _Blocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self.images: list[str] = []
        self.buf: list[str] = []
        self.kind = "p"
        self.skip = 0

    def flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.blocks.append((self.kind, text))
        self.buf, self.kind = [], "p"

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "img":
            src = dict(attrs).get("src")
            if src and src.startswith("http"):
                self.images.append(src)
        elif tag in BLOCK_TAGS:
            self.flush()
            if tag in HEADING_TAGS:
                self.kind = "h"
            elif tag == "li":
                self.kind = "li"

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK_TAGS:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def html_to_blocks(body: str) -> tuple[list[tuple[str, str]], list[str]]:
    p = _Blocks()
    p.feed(body or "")
    p.close()
    p.flush()
    return p.blocks, p.images


# ---------- перевод ----------


def _translate_free(blocks, google_translate):
    texts = [t for _, t in blocks]
    out: list[str] = []
    batch: list[str] = []

    def run(chunk):
        res = google_translate("\n".join(chunk)).split("\n")
        if len(res) != len(chunk):  # переводчик склеил строки — переводим по одной
            res = [google_translate(t) for t in chunk]
        out.extend(r.strip() for r in res)
        time.sleep(0.3)

    for t in texts:
        if batch and len("\n".join(batch + [t])) > 1500:
            run(batch)
            batch = []
        if len(t) > 1500:  # очень длинный абзац режем по предложениям
            parts, cur = [], ""
            for s in re.split(r"(?<=[.!?])\s+", t):
                if cur and len(cur) + len(s) > 1400:
                    parts.append(cur)
                    cur = ""
                cur = (cur + " " + s).strip()
            parts.append(cur)
            if batch:
                run(batch)
                batch = []
            out.append(" ".join(google_translate(x) for x in parts))
            continue
        batch.append(t)
    if batch:
        run(batch)
    return [(k, tr or t) for (k, t), tr in zip(blocks, out)]


CLAUDE_PROMPT = """Переведи статью о World of Warcraft: Forever на русский язык полностью, без сокращений.
Используй привычный игрокам сленг и названия из русской версии игры (данж, рейд, хотфикс, таланты, профессии).
Сохрани разметку: строки "## " — подзаголовки, строки "• " — пункты списка. Каждый абзац — отдельной строкой.
В ответе только перевод, без вступлений.

{text}"""


def _translate_claude(blocks):
    import anthropic

    src = "\n".join(("## " if k == "h" else "• " if k == "li" else "") + t for k, t in blocks)
    with anthropic.Anthropic().messages.stream(
        model="claude-opus-5-5",
        max_tokens=32000,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": CLAUDE_PROMPT.format(text=src[:60000])}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("refusal")
    out = "".join(b.text for b in msg.content if b.type == "text")
    res = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("## "):
            res.append(("h", line[3:]))
        elif line.startswith("• "):
            res.append(("li", line[2:]))
        else:
            res.append(("p", line))
    return res


def translate_blocks(blocks, google_translate):
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _translate_claude(blocks)
        except Exception as exc:
            print(f"  Claude error, using free translator: {exc}", file=sys.stderr)
    return _translate_free(blocks, google_translate)


# ---------- Discord ----------


def _md(blocks) -> list[str]:
    lines = []
    for k, t in blocks:
        t = t.replace("​", "").replace("*", "\\*").replace("_", "\\_")
        lines.append(f"**{t}**" if k == "h" else f"• {t}" if k == "li" else t)
    return lines


def split_chunks(lines: list[str], limit: int = EMBED_LIMIT) -> list[str]:
    chunks, cur = [], ""
    for line in lines:
        while len(line) > limit:  # на случай гигантского абзаца
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        add = (cur + "\n\n" + line) if cur else line
        if len(add) > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = add
    if cur:
        chunks.append(cur)
    return chunks or [""]


def _send(webhook: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    for _ in range(5):
        req = urllib.request.Request(
            webhook + "?wait=true",
            data=data,
            headers={"Content-Type": "application/json", "User-Agent": "wow-forever-ru-feed/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30):
                return
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = json.loads(e.read() or b"{}").get("retry_after", 2)
                time.sleep(float(wait) + 0.5)
                continue
            raise RuntimeError(f"Discord {e.code}: {e.read()[:300]!r}")
    raise RuntimeError("Discord rate limit")


def post_article(webhook: str, title_ru: str, link: str, image: str | None, blocks_ru) -> int:
    chunks = split_chunks(_md(blocks_ru))
    total = len(chunks)
    for n, chunk in enumerate(chunks, 1):
        embed = {"description": chunk, "color": COLOR}
        if n == 1:
            embed["title"] = title_ru[:256]
            embed["url"] = link
            if image:
                embed["image" if total == 1 else "thumbnail"] = {"url": image}
        if n == total:
            embed["footer"] = {"text": "Кадгар переводит с Wowhead"}
            embed["description"] = chunk + f"\n\n[Оригинал на Wowhead]({link})"
        if total > 1:
            embed.setdefault("author", {"name": f"Часть {n}/{total}"})
        _send(webhook, {"username": BOT_NAME, "avatar_url": BOT_AVATAR, "embeds": [embed], "allowed_mentions": {"parse": []},
                     "flags": 4096})  # SUPPRESS_NOTIFICATIONS: без пушей и звука
        time.sleep(1)
    return total
