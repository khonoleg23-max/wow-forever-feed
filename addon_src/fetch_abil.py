import json, re, html, urllib.request, concurrent.futures as cf, os
from parse import pages
d = pages('talents.js')['wow.talentCalcClassic.classicplus.data']
ids = sorted({a['id'] for v in d['abilities'].values() for a in v})
cache = json.load(open('abil_ru.json', encoding='utf-8')) if os.path.exists('abil_ru.json') else {}
todo = [i for i in ids if str(i) not in cache]
def get(i):
    u = f'https://nether.wowhead.com/forever/ru/tooltip/spell/{i}'
    try:
        j = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'}), timeout=20).read().decode())
    except Exception as e:
        return i, None
    tip = j.get('tooltip', '')
    rank = re.search(r'Уровень (\d+)|Ранг (\d+)', tip)
    body = tip.split('</table><table>')[-1] if '</table><table>' in tip else tip
    text = html.unescape(re.sub(r'<[^>]+>', ' ', body))
    return i, {'name': j.get('name'), 'text': re.sub(r'\s+', ' ', text).strip()[:400]}
with cf.ThreadPoolExecutor(6) as ex:
    for i, r in ex.map(get, todo):
        if r: cache[str(i)] = r
json.dump(cache, open('abil_ru.json', 'w', encoding='utf-8'), ensure_ascii=False)
print(len(ids), 'ids,', len(cache), 'cached')
