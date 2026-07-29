#!/usr/bin/env python3
"""体験プログラムの調査JSONを data/spots.json に取り込む。

    python3 scripts/import-experience.py 調査.json

IDで突き合わせて、体験まわりの項目だけを既存に反映する。他の項目は触らない。
取り込んだあとは必ず `npm run build:spots && npm run check`。

調査JSONは情報が多いので、アプリで使う分だけに絞って入れる。

    experience_tags   → xtags  そのまま（ポップアップに出す）
                      → xg     絞り込み用にまとめたグループ（下の GROUPS）
    experience_memo   → xmemo  1〜2文の説明
    experience_age    → xage   原文（ポップアップに出す）
    experience_programs → xprog 各プログラムの名前と対象年齢だけ
    primary_source_urls → xurl 先頭の1つ（体験情報の出どころ）

    age（既存のおすすめ年齢） → ages 未就学児／小学生／中学生以上 の配列（絞り込み用）

落とすもの: summary, schedule, fee, reservation, source_url(各プログラム),
evidence_note, research_status, source_checked_at。
細かい条件は変わりやすく、結局は公式を見ることになるので持たない。
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPOTS = ROOT / "data" / "spots.json"

# 調査JSONのタグは230種類あって細かすぎるので、絞り込めるまとまりに寄せる。
# 上から順に見て、最初に当たったグループにする（順番に意味がある）。
GROUPS = [
    ("動物とふれあう", ["動物", "飼育", "給餌", "酪農", "乗馬", "獣医", "ふれあい"]),
    ("農業・収穫", ["農業", "収穫", "里山体験", "農体験", "園芸", "農村"]),
    ("食・料理", ["食", "調理", "料理", "かまぼこ", "きき水"]),
    ("ものづくり・工作", ["ものづくり", "工作", "クラフト", "陶芸", "陶磁器", "ガラス", "工芸",
                    "サンドブラスト", "フュージング", "絵付け", "染色", "どろだんご",
                    "タイル", "モザイク", "ボトルシップ", "刺しゅう", "制作", "衣装", "実演"]),
    ("科学・実験", ["科学", "実験", "プログラミング", "ロボット", "ドローン", "電子",
                "分解", "測量", "地図", "自由研究", "研究", "解剖", "南極", "航空", "宇宙工作"]),
    ("天体・星空", ["天体", "天文", "星空"]),
    ("自然・生きもの観察", ["自然", "生きもの", "植物", "環境", "観察", "地質", "化石", "森林",
                    "標本", "干潟", "水辺", "海の", "河川", "火山", "野外", "動物観察", "フィールドワーク"]),
    ("文化・伝統", ["文化", "伝統", "茶道", "着物", "アイヌ", "能楽", "歴史", "考古", "平和",
                "言語", "文学", "昔の仕事", "遊び", "季節行事"]),
    ("アート・表現", ["アート", "表現", "映画", "対話型", "ワークショップ", "デジタル"]),
    ("仕事・職業体験", ["職業", "仕事", "鉄道", "産業", "技術", "モータースポーツ", "防災", "気象",
                  "下水道", "施設見学", "土木"]),
    ("体を動かす", ["スポーツ", "カヤック", "身体", "指導者付き"]),
    ("ガイド・解説", ["ガイド", "解説", "ツアー", "バックヤード", "学芸員", "レンジャー",
                 "専門家", "専門スタッフ", "スタッフ", "研究者", "案内", "教室", "講座",
                 "プログラム", "イベント", "体験", "学習", "相談", "交流"]),
]

AGES = ["未就学児", "小学生", "中学生以上"]


def group_of(tag):
    for name, keys in GROUPS:
        if any(k in tag for k in keys):
            return name
    return None


def ages_of(*texts):
    """「小学生中心（未就学児も可）」→ ['未就学児','小学生'] のように読み取る。
    数字の範囲（3～15歳）も拾う。何も読めなければ空。"""
    got = set()
    for t in texts:
        if not t:
            continue
        t = str(t)
        if re.search(r"全年齢|どなたでも|年齢制限なし|子ども～大人|子供～大人", t):
            got |= set(AGES)
        if re.search(r"未就学|幼児|園児|乳幼児|赤ちゃん|0歳|1歳|2歳|3歳|4歳|5歳", t):
            got.add("未就学児")
        if re.search(r"小学|児童", t):
            got.add("小学生")
        if re.search(r"中学|高校|中高生|大人|一般|保護者|高学年以上", t):
            got.add("中学生以上")
        for a, b in re.findall(r"(\d{1,2})\s*[～〜~-]\s*(\d{1,2})\s*歳", t):
            lo, hi = int(a), int(b)
            if lo <= 6:
                got.add("未就学児")
            if lo <= 12 and hi >= 7:
                got.add("小学生")
            if hi >= 13:
                got.add("中学生以上")
    return [a for a in AGES if a in got]


def main():
    if len(sys.argv) < 2:
        sys.exit("使い方: python3 scripts/import-experience.py 調査.json")
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    cur = json.loads(SPOTS.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in cur}

    unknown, missing = set(), []
    tagged = aged = 0
    for x in src:
        s = by_id.get(x["id"])
        if not s:
            missing.append(x["id"])
            continue

        # 体験まわりは毎回入れ直す（該当なしに変わった場合に消えるように）
        for k in ("xtags", "xg", "xmemo", "xage", "xprog", "xurl"):
            s.pop(k, None)

        tags = x.get("experience_tags")
        tags = [t.strip() for t in tags if t and t.strip()] if isinstance(tags, list) else []
        if tags:
            groups = []
            for t in tags:
                g = group_of(t)
                if not g:
                    unknown.add(t)
                elif g not in groups:
                    groups.append(g)
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
            urls = x.get("primary_source_urls") or []
            if isinstance(urls, list) and urls:
                s["xurl"] = urls[0]
            tagged += 1

        # おすすめ年齢は全スポットで正規化する（体験の有無によらず絞り込めるように）
        a = ages_of(s.get("age"))
        if a:
            s["ages"] = a
            aged += 1
        else:
            s.pop("ages", None)

    if missing:
        print(f"!! 既存に無いID {len(missing)}件: {missing[:5]}")
    if unknown:
        print(f"!! グループに割り当てられなかったタグ {len(unknown)}件:")
        for t in sorted(unknown):
            print("   ", t)

    with SPOTS.open("w", encoding="utf-8") as f:
        f.write("[\n")
        f.write(",\n".join(json.dumps(s, ensure_ascii=False) for s in cur))
        f.write("\n]\n")

    from collections import Counter
    gc = Counter(g for s in cur for g in s.get("xg", []))
    ac = Counter(a for s in cur for a in s.get("ages", []))
    print(f"体験タグ: {tagged}件 / 年齢を読めた: {aged}件（全{len(cur)}件）")
    print("グループ別:", dict(gc.most_common()))
    print("年齢別:", dict(ac))
    print("npm run build:spots && npm run check を忘れずに")


if __name__ == "__main__":
    main()
