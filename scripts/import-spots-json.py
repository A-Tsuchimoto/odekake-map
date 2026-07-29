#!/usr/bin/env python3
"""スポットの追加分をJSONで受け取って data/spots.json に入れる。

    python3 scripts/import-spots-json.py 追加.json

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

# 持つキー。ここに無いものは捨てる
KEYS = ["id", "cat", "sub", "name", "addr", "t1", "t2", "c1", "c2",
        "rain", "desc", "age", "rate", "note", "url", "lat", "lng", "region", "season"]
NUM = {"t1", "t2", "c1", "c2", "lat", "lng", "rate"}


def clean(x):
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
            v = ledger.area(v, None)
        s[k] = v

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
    return s


def main():
    if len(sys.argv) < 2:
        sys.exit("使い方: python3 scripts/import-spots-json.py 追加.json")
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if isinstance(src, dict):
        src = [src]
    cur = json.loads(SPOTS.read_text(encoding="utf-8"))
    idx = {s["id"]: i for i, s in enumerate(cur)}

    added, updated = [], []
    for x in src:
        s = clean(x)
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
