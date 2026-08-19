#!/usr/bin/env python3
"""住所から緯度経度を引く（町丁目の代表点）。

    python3 scripts/geocode-jp.py 沖縄県那覇市壺屋1-6-16
    → 26.213914, 127.692361   壺屋一丁目（町丁目の代表点・誤差100m前後）

Google Maps などの地図APIには出られないので、GitHub にある
Geolonia の住所データ（国土交通省「位置参照情報」由来、CC BY 4.0）を使う。
持っているのは**町丁目の代表点**なので、番地までは当たらない。

    「◯◯二丁目」まである住所（市街地）  … 実測との差は数十〜250m。ピンとして使える
    「字◯◯」しかない住所（郡部の村など） … 450m〜4.8km ずれた。**使わない方がよい**

    https://github.com/geolonia/japanese-addresses

**建物の正確な座標が分かるなら、そちらを優先すること。**
ここで引いた座標を data/spots.json に入れるときは `approx: true` を付けて、
「およその位置」だと分かるようにする（import-spots-json.py --geocode がやる）。

市区町村ごとのJSONは .cache/geolonia/ に取っておく（2回目からは通信しない）。
"""
import json, re, sys, unicodedata, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "geolonia"
BASE = "https://raw.githubusercontent.com/geolonia/japanese-addresses/master/api/ja"
PREF = r"(東京都|北海道|京都府|大阪府|.{2,3}?県)"
# 政令市の区は市とセットで1つの単位。郡は町村まで
CITY = r"(.+?[市区町村])"
KANJI = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def kanji_num(s):
    """一 → 1、十二 → 12、二十 → 20。丁目の数字までしか出てこない"""
    if not s:
        return None
    if s == "十":
        return 10
    if "十" in s:
        a, _, b = s.partition("十")
        return (KANJI.get(a, 1) if a else 1) * 10 + (KANJI.get(b, 0) if b else 0)
    n = 0
    for c in s:
        if c not in KANJI:
            return None
        n = n * 10 + KANJI[c]
    return n


def loose(town):
    """町名を突き合わせ用にほどく。「北六条西八丁目」→「北6条西8」、
    「長者町六丁目」→「長者町6」。漢数字と丁目を落として、住所側の書き方に寄せる"""
    t = re.sub(r"([一二三四五六七八九十〇]+)丁目", lambda m: str(kanji_num(m.group(1)) or ""), town)
    t = re.sub(r"([一二三四五六七八九十〇]+)(条|線|区|号)",
               lambda m: str(kanji_num(m.group(1)) or m.group(1)) + m.group(2), t)
    return t


def fetch(pref, city):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{pref}_{city}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    url = f"{BASE}/{urllib.parse.quote(pref)}/{urllib.parse.quote(city)}.json"
    with urllib.request.urlopen(url, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def split_addr(addr):
    """住所を 都道府県／市区町村／それ以降 に割る。郡は町村までを市区町村に含める"""
    a = unicodedata.normalize("NFKC", addr).replace(" ", "").replace("　", "")
    m = re.match(PREF, a)
    if not m:
        return None
    pref, rest = m.group(1), a[m.end():]
    m = re.match(r"(.{1,8}?郡)(.{1,8}?[町村])(.*)$", rest)
    if m:
        return pref, m.group(1) + m.group(2), m.group(3)   # データ側は「国頭郡恩納村」と郡付き
    m = re.match(CITY + r"(.*)$", rest)
    if not m:
        return None
    city, tail = m.group(1), m.group(2)
    # 政令市は区まで
    m2 = re.match(r"(.{1,6}?区)(.*)$", tail)
    if city.endswith("市") and m2:
        city, tail = city + m2.group(1), m2.group(2)
    return pref, city, tail


def level_of(town):
    """当たった町名の細かさ。丁目・条まであるものは街区くらいの広さで実用になるが、
    郡部の「字◯◯」は集落まるごとなので、代表点は数百m〜数km ずれる"""
    return "丁目" if re.search(r"(丁目|条|線)", town) else "字"


def geocode(addr):
    """(lat, lng, 当たった町名) を返す。当たらなければ None"""
    parts = split_addr(addr)
    if not parts:
        return None
    pref, city, tail = parts
    try:
        towns = fetch(pref, city)
    except Exception as e:
        print(f"!! {pref}{city} の住所データを取れなかった: {e}", file=sys.stderr)
        return None
    """住所側とデータ側で「字」の有無が揃わない（データは「字谷茶」、住所は「谷茶」など）ので
       どちらも落として突き合わせる"""
    aza = lambda s: re.sub(r"^(大字|字)", "", s)
    best = None
    for t in towns:
        for name in {t["town"], loose(t["town"])}:
            for nm, tl in ((name, tail), (aza(name), aza(tail))):
                if not nm or not tl.startswith(nm):
                    continue
                # 丁目・条の数字で終わる町名だけ、次が数字なら別の町（西8 と 西80）
                if nm[-1:].isdigit() and tl[len(nm):len(nm) + 1].isdigit():
                    continue
                if not best or len(nm) > best[0]:
                    best = (len(nm), t)
    if not best:
        return None
    t = best[1]
    return t["lat"], t["lng"], t["town"]


def main():
    if len(sys.argv) < 2:
        sys.exit("使い方: python3 scripts/geocode-jp.py 住所 [住所...]")
    ng = 0
    for addr in sys.argv[1:]:
        got = geocode(addr)
        if got:
            lat, lng, town = got
            rough = "  ← 字なので数百m〜数kmずれる。使わない方がよい" if level_of(town) == "字" else ""
            print(f"{lat}, {lng}\t{town}の代表点\t{addr}{rough}")
        else:
            ng += 1
            print(f"—\t引けなかった\t{addr}")
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()
