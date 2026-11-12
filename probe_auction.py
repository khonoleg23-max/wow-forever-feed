"""Проверка: отдаёт ли Blizzard API аукцион WoW Forever.

Нужны секреты BLIZZARD_CLIENT_ID и BLIZZARD_CLIENT_SECRET (develop.battle.net).
Скрипт перебирает возможные пространства имён Classic/Forever в регионах EU и US,
печатает найденные серверы и пробует скачать лоты одного аукциона.
Ключи и токен в лог не выводятся.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REGIONS = ["eu", "us"]
NAMESPACES = [
    "dynamic-forever",
    "dynamic-classicforever",
    "dynamic-classic-forever",
    "dynamic-classic",
    "dynamic-classic1x",
    "dynamic-classicann",
]


def http(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, None


def token(region):
    cid, sec = os.environ["BLIZZARD_CLIENT_ID"], os.environ["BLIZZARD_CLIENT_SECRET"]
    auth = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    code, body = http(
        f"https://oauth.battle.net/token",
        {"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
        b"grant_type=client_credentials",
    )
    if code != 200:
        sys.exit(f"OAuth failed: HTTP {code} (проверьте Client ID / Secret)")
    return body["access_token"]


def api(region, path, ns, tok):
    url = f"https://{region}.api.blizzard.com{path}?" + urllib.parse.urlencode(
        {"namespace": f"{ns}-{region}", "locale": "en_US"}
    )
    return http(url, {"Authorization": f"Bearer {tok}"})


def main():
    tok = token("eu")
    for region in REGIONS:
        for ns in NAMESPACES:
            code, idx = api(region, "/data/wow/connected-realm/index", ns, tok)
            print(f"\n[{region}] {ns}: connected-realm index -> HTTP {code}")
            if code != 200:
                continue
            links = idx.get("connected_realms", [])
            print(f"  connected realms: {len(links)}")
            tried = 0
            for link in links[:40]:
                cr_id = link["href"].split("/connected-realm/")[1].split("?")[0]
                c, cr = api(region, f"/data/wow/connected-realm/{cr_id}", ns, tok)
                names = [r["name"] if isinstance(r["name"], str) else r["name"].get("en_US") for r in (cr or {}).get("realms", [])]
                cat = (cr or {}).get("realms", [{}])[0].get("category")
                cat = cat if isinstance(cat, str) else (cat or {}).get("en_US")
                print(f"  realm {cr_id}: {', '.join(names)} [{cat}]")
                if tried < 2:
                    tried += 1
                    c, ah = api(region, f"/data/wow/connected-realm/{cr_id}/auctions/index", ns, tok)
                    houses = (ah or {}).get("auctions", [])
                    print(f"    auctions index -> HTTP {c}, houses: {[h.get('name') for h in houses]}")
                    for h in houses[:1]:
                        c, lots = api(region, f"/data/wow/connected-realm/{cr_id}/auctions/{h['id']}", ns, tok)
                        n = len((lots or {}).get("auctions", []))
                        print(f"    lots for house {h['id']} -> HTTP {c}, auctions: {n}")
                        if n:
                            print("    sample:", json.dumps(lots["auctions"][0])[:300])


if __name__ == "__main__":
    main()
