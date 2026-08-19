#!/usr/bin/env python3
"""スポットの追加分をJSONで受け取って data/spots.json に入れる。

    python3 scripts/import-spots-json.py 追加.json
    python3 scripts/import-spots-json.py 追加.json --geocode   # 座標が無いものを住所から補う

台帳（Excel）ではなく、調べたものをそのままJSONでもらったとき用。
IDが既にあれば上書き、無ければその地域のいちばん後ろに足す。
他のスポットは触らない。取り込んだあとは必ず `npm run build:spots && npm run check`。

JSONは data/spots.json と同じキー（id, cat, sub, name, addr, t1, t2, c1, c2,
rain, desc, age, rate, note, url, lat, lng, region, season）で書く。
体験プログラムを一緒に書くときは、調査JSONと同じキーを使う
（experience_tags / experience_memo / experience_age / experience_programs /
primary_source_urls）。読み替えは scripts/import-experience.py と同じ。

上のどれでもないキーは黙って捨てる（調査メモ、座標の出どころ、日程・料金など）。
アプリが使うものだけを持ち、変わりやすいものは一次情報のURLに送る方針。

住所は「都道府県＋市区町村」に詰める（一覧に出るので番地は落とす）。
rate は空・0・null なら持たない（推測で埋めない）。

`--geocode` を付けると、緯度経度の無いスポットだけ、住所（番地を落とす前のもの）から
**町丁目の代表点**を引いて入れる（scripts/geocode-jp.py）。誤差は数十〜200m程度なので
`approx: true` を一緒に付けて、ポップアップに「およその位置」と出す。
建物の正確な座標が分かったら、同じIDで座標入りのJSONを流し直せば上書きされる。
"""
import importlib.util, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPOTS = ROOT / "data" / "spots.json"


def load(name):
    """ファイル名にハイフンが入っていて import できないので、パスから読む"""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ledger = load("import-ledger")        # 住所の詰め方とカテゴリ名を借りる
exp = load("import-experience")       # 体験の区分と年齢の読み取りを借りる
geo = load("geocode-jp")              # --geocode のときだけ使う

# 持つキー。ここに無いものは捨てる
KEYS = ["id", "cat", "sub", "name", "addr", "t1", "t2", "c1", "c2",
        "rain", "desc", "age", "rate", "note", "url", "lat", "lng", "region", "season"]
NUM = {"t1", "t2", "c1", "c2", "lat", "lng", "rate"}
# data/spots.json の中の並び順
ORDER = ["id", "cat", "sub", "name", "addr", "t1", "t2", "c1", "c2", "rain", "desc", "age",
         "rate", "note", "url", "lat", "lng", "approx", "region", "season", "months",
         "xtags", "xg", "xmemo", "xage", "xprog", "xurl", "ages"]


def clean(x, do_geocode=False):
    s = {}
    for k in KEYS:
        v = x.get(k)
        if v is None or v == "":
            continue
        if k in NUM:
            v = float(v)
            if k in ("t1", "t2", "c1", "c2"):
                v = int(v)
            if k == "rate" and not v:      # 0 は「評価なし」として持たない
                continue
        elif isinstance(v, str):
            v = v.strip()
            if not v:
                continue
        if k == "cat":
            if v not in ledger.CANON:
                sys.exit(f"知らないカテゴリ: {v}（{x.get('name')}）。"
                         "index.html の COLORS と import-ledger.py の CANON に足すこと")
            v = ledger.CANON[v]
        if k == "addr":
            v = ledger.area(v, None)       # 元の番地入りは x["addr"] に残っている
        s[k] = v

    # 座標が無いものだけ、住所から町丁目の代表点を引く。ずれるので印を付けておく。
    # 「字◯◯」しか無い住所は数kmずれるので、既定では入れない（--geocode-aza で入る）
    if do_geocode and "lat" not in s and x.get("addr"):
        got = geo.geocode(x["addr"])
        if not got:
            print(f"!! 住所から座標を引けなかった: {s.get('name')}（{x['addr']}）")
        elif geo.level_of(got[2]) == "字" and do_geocode != "aza":
            print(f"!! 粗すぎるので入れなかった: {s.get('name')} → {got[2]}（数百m〜数kmずれる）。"
                  "どうしても入れるなら --geocode-aza")
        else:
            s["lat"], s["lng"], town = got
            s["approx"] = True
            print(f"  座標を補った: {s.get('name')} → {town}の代表点 ({s['lat']}, {s['lng']})")

    if s.get("season"):
        months = ledger.months(s["season"])
        if months:
            s["months"] = months

    # 体験プログラム。読み替えは import-experience.py と同じにする
    tags = x.get("experience_tags")
    tags = [t.strip() for t in tags if t and t.strip()] if isinstance(tags, list) else []
    if tags:
        groups, unknown = [], []
        for t in tags:
            g = exp.group_of(t)
            if not g:
                unknown.append(t)
            elif g not in groups:
                groups.append(g)
        if unknown:
            print(f"!! 区分に割り当てられなかったタグ（{s.get('id')}）: {unknown}")
        s["xtags"] = tags
        if groups:
            s["xg"] = groups
        memo = (x.get("experience_memo") or "").strip()
        if memo and memo != "該当なし":
            s["xmemo"] = memo
        xage = (x.get("experience_age") or "").strip()
        if xage and xage != "該当なし":
            s["xage"] = xage
        progs = []
        for p in (x.get("experience_programs") or [])[:3]:
            n = (p.get("name") or "").strip()
            if not n:
                continue
            item = {"n": n}
            a = (p.get("target_age") or "").strip()
            if a:
                item["a"] = a
            progs.append(item)
        if progs:
            s["xprog"] = progs
        s.update(exp.pick_urls(x, s))

    ages = exp.ages_of(s.get("age"))
    if ages:
        s["ages"] = ages
    # 既存の並びに揃える（差分が読みやすいように）
    return {k: s[k] for k in ORDER if k in s}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_geocode = "aza" if "--geocode-aza" in sys.argv else ("--geocode" in sys.argv)
    if not args:
        sys.exit("使い方: python3 scripts/import-spots-json.py 追加.json [--geocode|--geocode-aza]")
    src = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    if isinstance(src, dict):
        src = [src]
    cur = json.loads(SPOTS.read_text(encoding="utf-8"))
    idx = {s["id"]: i for i, s in enumerate(cur)}

    added, updated = [], []
    for x in src:
        s = clean(x, do_geocode)
        for k in ("id", "cat", "name", "region"):
            if not s.get(k):
                sys.exit(f"{k} がない: {x.get('id') or x.get('name')}")
        if s["id"] in idx:
            cur[idx[s["id"]]] = s
            updated.append(s["id"])
        else:
            # 同じ地域のいちばん後ろに入れる（ファイルが地域ごとにまとまるように）
            last = max((i for i, o in enumerate(cur) if o.get("region") == s["region"]), default=len(cur) - 1)
            cur.insert(last + 1, s)
            idx = {o["id"]: i for i, o in enumerate(cur)}
            added.append(s["id"])

    ledger.write_spots(cur)
    print(f"追加 {len(added)}件 / 上書き {len(updated)}件（全{len(cur)}件）")
    if added:
        print("  追加:", ", ".join(added))
    if updated:
        print("  上書き:", ", ".join(updated))
    print("npm run build:spots && npm run check を忘れずに")


if __name__ == "__main__":
    main()
