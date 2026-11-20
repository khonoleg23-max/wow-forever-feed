import json, re
from parse import pages
en = pages('talents.js')['wow.talentCalcClassic.classicplus.data']
ru = pages('talents_ru.js')['wow.talentCalcClassic.classicplus.data']
ab = json.load(open('abil_ru.json', encoding='utf-8'))
CLS = {'war': ('Warrior', 1), 'pal': ('Paladin', 2), 'hun': ('Hunter', 3), 'rog': ('Rogue', 4), 'pri': ('Priest', 5),
       'sha': ('Shaman', 7), 'mag': ('Mage', 8), 'wlk': ('Warlock', 9), 'dru': ('Druid', 11)}
out = {}
for key, (cname, cid) in CLS.items():
    trees = [t for t in en['trees'].values() if t['description'].startswith(cname)]
    tal = []
    for t in trees:
        tid = str(t['id']); tree = t['description'][len(cname):]
        for tk, x in en['talents'][tid].items():
            r = ru['talents'][tid][tk]
            desc = r['descriptions'][str(len(x['ranks']))]
            tal.append({'tree': tree, 'row': x['row'], 'col': x['col'], 'max': len(x['ranks']), 'id': x['ranks'][0],
                        'en': x['name'], 'ru': r['name'], 'desc': desc})
    tal.sort(key=lambda z: (z['tree'], z['row'], z['col']))
    groups = {}
    for a in en['abilities'][str(cid)]:
        info = ab.get(str(a['id']))
        if not info: continue
        g = groups.setdefault(info['name'], {'ru': info['name'], 'lvl': a['level'], 'id': a['id'], 'text': info['text']})
        if a['level'] < g['lvl']: g.update(lvl=a['level'], id=a['id'], text=info['text'])
    abil = sorted(groups.values(), key=lambda z: (z['lvl'], z['ru']))
    out[key] = {'talents': tal, 'abilities': abil}
json.dump(out, open('digest.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
with open('digest.txt', 'w', encoding='utf-8') as f:
    for k, v in out.items():
        f.write(f'### {k} talents {len(v["talents"])} abilities {len(v["abilities"])}\n')
        for t in v['talents']:
            f.write(f'T {t["id"]} {t["tree"]} r{t["row"]}c{t["col"]} x{t["max"]} | {t["ru"]} ({t["en"]}) — {t["desc"][:160]}\n')
        for a in v['abilities']:
            f.write(f'A {a["id"]} L{a["lvl"]} | {a["ru"]} — {a["text"][:130]}\n')
print({k: (len(v['talents']), len(v['abilities'])) for k, v in out.items()})
