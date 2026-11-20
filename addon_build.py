"""Собирает данные аддона KadgarGuide из таблиц опросника (kadgar_quiz.py) и заметок addon_src/notes/*.txt.

Заметки привязаны к ID заклинаний (данные Wowhead WoW Forever, addon_src/digest.json), поэтому аддон
находит их в любом языке клиента: русское название берётся из самой игры (C_Spell.GetSpellName).
Формат строки заметки: [*|+]ID|текст   (* — советую взять талант, + — ключевое умение тренера)

  python addon_build.py            — пишет addon/KadgarGuide/Data.lua и Notes.lua
  python addon_build.py --install  — и копирует аддон в папку игры WoW Forever
"""

import json
import shutil
import sys
from pathlib import Path

from kadgar_quiz import CLASSES, DUNGEONS, SKILLS, TALENTS, ZONES
from specs import DEFAULT, SPECS, plan, rec_ids, tree_talents

HERE = Path(__file__).parent
SRC = HERE / "addon_src"
ROOT = HERE / "addon" / "KadgarGuide"
GAME = Path(r"F:\World of Warcraft\_forever_\Interface\AddOns\KadgarGuide")
TOKEN = {"war": "WARRIOR", "pal": "PALADIN", "hun": "HUNTER", "rog": "ROGUE", "pri": "PRIEST",
         "sha": "SHAMAN", "mag": "MAGE", "wlk": "WARLOCK", "dru": "DRUID"}


def q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def plain(name: str) -> str:
    return name.replace(" ✨", "")


def read_notes(name: str):
    """[(id, text, flag)] из addon_src/notes/<name>.txt"""
    out = []
    for line in (SRC / "notes" / f"{name}.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        flag = line[0] if line[0] in "*+" else ""
        sid, text = line.lstrip("*+").split("|", 1)
        out.append((int(sid), text.strip(), flag))
    return out


def data_lua() -> list:
    out = ["-- Сгенерировано addon_build.py из kadgar_quiz.py — не править руками.",
           "KadgarGuide = KadgarGuide or {}", "local KG = KadgarGuide", ""]
    out.append("KG.token = {" + ", ".join(f"{v} = {q(k)}" for k, v in TOKEN.items()) + "}")
    out.append("KG.className = {" + ", ".join(f"{k} = {q(v[0])}" for k, v in CLASSES.items()) + "}")
    out.append("-- {id, имя, от, до, где}")
    out.append("KG.zones = {")
    out += [f"  {{{i}, {q(n)}, {a}, {b}, {q(w)}}}," for i, n, a, b, w in ZONES]
    out.append("}")
    out.append("KG.dungeons = {")
    out += [f"  {{{i}, {q(plain(n))}, {a}, {b}, {q(w)}, {'true' if '✨' in n else 'false'}}}," for i, n, a, b, w in DUNGEONS]
    out.append("}")
    out.append("-- ветки талантов: {name, about, talents = {{с уровня, совет}}, rec = {[ID] = true}}; tree[ID] = номер ветки")
    out.append("-- skills: {уровень, умение}")
    out.append("KG.specs, KG.defSpec, KG.tree, KG.skills = {}, {}, {}, {}")
    dig = json.loads((SRC / "digest.json").read_text(encoding="utf-8"))
    for c in CLASSES:
        out.append(f"KG.defSpec.{c} = {DEFAULT[c]}")
        out.append(f"KG.specs.{c} = {{")
        for i, (_, name, about) in enumerate(SPECS[c], 1):
            out.append(f"  {{ name = {q(name)}, about = {q(about)}, talents = {{")
            out += [f"    {{{a}, {q(t)}}}," for a, t in plan(c, i, TALENTS, dig)]
            out.append("  }, rec = {" + ", ".join(f"[{x}] = true" for x in rec_ids(c, i, dig)) + "} },")
        out.append("}")
        tree = {t["id"]: i for i in range(1, 4) for t in tree_talents(c, i, dig)}
        out.append("for id, n in pairs({" + ", ".join(f"[{k}] = {v}" for k, v in tree.items()) + "}) do KG.tree[id] = n end")
        out.append(f"KG.skills.{c} = {{" + ", ".join(f"{{{a}, {q(n)}}}" for a, n in SKILLS[c]) + "}")
    return out


def notes_lua() -> list:
    dig = json.loads((SRC / "digest.json").read_text(encoding="utf-8"))
    out = ["-- Сгенерировано addon_build.py из addon_src/notes — не править руками.",
           "-- notes[ID] = пояснение; names[ID] = русское название (запасное, если клиент не отдаст своё);",
           "-- recLegacy[ID] = очко Наследия советую в прокачке (таланты — в Data.lua, по веткам).",
           "KadgarGuide = KadgarGuide or {}", "local KG = KadgarGuide",
           "KG.notes, KG.names = {}, {}", "local N, R = KG.notes, KG.names"]
    total = 0
    for c in list(CLASSES) + ["legacy"]:
        names = {}
        if c != "legacy":
            names = {t["id"]: t["ru"] for t in dig[c]["talents"]}
            names.update({a["id"]: a["ru"] for a in dig[c]["abilities"]})
        else:
            from addon_src_legacy import LEGACY_RU  # noqa: WPS433
            names = LEGACY_RU
        out.append(f"-- {c}")
        for sid, text, flag in read_notes(c):
            out.append(f"N[{sid}] = {q(text)}" + (f"; R[{sid}] = {q(names[sid])}" if sid in names else ""))
            total += 1
        if c == "legacy":
            out.append("KG.recLegacy = {" + ", ".join(f"[{i}] = true" for i, _, f in read_notes(c) if f == "*") + "}")
    print("пояснений:", total)
    return out


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "Data.lua").write_text("\n".join(data_lua()) + "\n", encoding="utf-8")
    (ROOT / "Notes.lua").write_text("\n".join(notes_lua()) + "\n", encoding="utf-8")
    if "--install" in sys.argv:
        if GAME.exists():
            shutil.rmtree(GAME)
        shutil.copytree(ROOT, GAME)
        print("установлено в", GAME)


if __name__ == "__main__":
    main()
