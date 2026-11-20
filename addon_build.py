"""Собирает данные аддона KadgarGuide из тех же таблиц, что и опросник Кадгара (kadgar_quiz.py).

  python addon_build.py            — пишет addon/KadgarGuide/Data.lua
  python addon_build.py --install  — и копирует аддон в папку игры WoW Forever
"""

import re
import shutil
import sys
from pathlib import Path

from kadgar_quiz import CLASSES, DUNGEONS, SKILLS, TALENTS, ZONES

ROOT = Path(__file__).parent / "addon" / "KadgarGuide"
GAME = Path(r"F:\World of Warcraft\_forever_\Interface\AddOns\KadgarGuide")
TOKEN = {"war": "WARRIOR", "pal": "PALADIN", "hun": "HUNTER", "rog": "ROGUE", "pri": "PRIEST",
         "sha": "SHAMAN", "mag": "MAGE", "wlk": "WARLOCK", "dru": "DRUID"}


def q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def plain(name: str) -> str:
    return name.replace(" ✨", "")


def main() -> None:
    out = ["-- Сгенерировано addon_build.py из kadgar_quiz.py — не править руками.",
           "KadgarGuide = KadgarGuide or {}", "local KG = KadgarGuide", ""]
    out.append("KG.token = {" + ", ".join(f"{v} = {q(k)}" for k, v in TOKEN.items()) + "}")
    out.append("KG.className = {" + ", ".join(f"{k} = {q(v[0])}" for k, v in CLASSES.items()) + "}")
    out.append("KG.spec = {" + ", ".join(f"{k} = {q(v[2])}" for k, v in CLASSES.items()) + "}")
    out.append("-- {id, имя, от, до, где}")
    out.append("KG.zones = {")
    out += [f"  {{{i}, {q(n)}, {a}, {b}, {q(w)}}}," for i, n, a, b, w in ZONES]
    out.append("}")
    out.append("KG.dungeons = {")
    out += [f"  {{{i}, {q(plain(n))}, {a}, {b}, {q(w)}, {'true' if '✨' in n else 'false'}}}," for i, n, a, b, w in DUNGEONS]
    out.append("}")
    out.append("-- таланты: {с уровня, совет}; rec — названия талантов из советов (для подсказок)")
    out.append("KG.talents, KG.rec, KG.skills = {}, {}, {}")
    for c in CLASSES:
        out.append(f"KG.talents.{c} = {{")
        out += [f"  {{{a}, {q(t)}}}," for a, t in TALENTS[c]]
        out.append("}")
        rec = {}
        for a, t in TALENTS[c]:
            for bold, paren in re.findall(r"\*\*(.+?)\*\*(?:\s*\(([^)]+)\))?", t):
                for part in re.split(r"\s*\(|\)\s*", bold) + [paren]:
                    part = re.sub(r"\s*\d+/\d+$", "", part).strip()
                    if part and not part[0].isdigit():
                        rec.setdefault(part, a)
        out.append(f"KG.rec.{c} = {{" + ", ".join(f"[{q(k)}] = {v}" for k, v in rec.items()) + "}")
        out.append(f"KG.skills.{c} = {{" + ", ".join(f"{{{a}, {q(n)}}}" for a, n in sorted(SKILLS[c])) + "}")
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "Data.lua").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("Data.lua:", len(out), "строк")
    if "--install" in sys.argv:
        if GAME.exists():
            shutil.rmtree(GAME)
        shutil.copytree(ROOT, GAME)
        print("установлено в", GAME)


if __name__ == "__main__":
    main()
