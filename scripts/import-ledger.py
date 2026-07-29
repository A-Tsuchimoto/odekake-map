#!/usr/bin/env python3
"""Excelの台帳から1地域分のスポットを data/spots.json に取り込む。

    python3 scripts/import-ledger.py <台帳.xlsx> --region odawara [--pref 神奈川県]
    python3 scripts/import-ledger.py <台帳.xlsx> --by-area [--replace-cat 飲食店]
    python3 scripts/import-ledger.py --purge-cat 飲食店      # 消すだけ

指定した region のスポットを台帳の中身で丸ごと入れ替える。他の地域は触らない。
region は data/regions.json に先に足しておくこと（起点と距離の輪はそちら）。

--by-area は「エリア」列で地域を振り分ける（地域をまたぐ台帳用）。既定はIDで上書きし、
台帳に載っていないスポットは残す。カテゴリごと差し替えたいときは --replace-cat を足すと、
台帳に出てくる地域の中でそのカテゴリを先に消してから入れる。

取り込んだあとは必ず:
    npm run build:spots && npm run check

台帳ごとに列名やカテゴリ表記が微妙に違うので、その吸収はここでやる。
openpyxl が要る（pip install openpyxl）。アプリ本体には影響しない開発用の道具。
"""
import argparse, json, re, sys, warnings
from pathlib import Path

warnings.filterwarnings("ignore", module="openpyxl")   # 台帳の書式設定に出る警告は無害

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl が要ります: pip install openpyxl")

ROOT = Path(__file__).resolve().parent.parent
SPOTS = ROOT / "data" / "spots.json"
REGIONS = ROOT / "data" / "regions.json"

# 台帳ごとに表記がぶれるので、11分類の正しい名前に寄せる
CANON = {
    "科学館系": "科学館・博物館",
    "科学館・博物館": "科学館・博物館",
    "水族館": "水族館・水辺の生き物",
    "水族館・水辺の生き物": "水族館・水辺の生き物",
    "水族館・海の生き物": "水族館・水辺の生き物",
    "海・港・砂浜": "海・砂浜・岬",
    "海・ビーチ・岬": "海・砂浜・岬",
    "海・砂浜・岬": "海・砂浜・岬",
    "川・湖・ダム": "川・湖・滝・ダム",
    "川・滝・ダム・マングローブ": "川・湖・滝・ダム",
    "川・湖・滝・ダム": "川・湖・滝・ダム",
    "森・里山": "森・里山",
    "山・ハイキング": "山・ハイキング",
    "大型公園": "大型公園",
    "牧場・農業体験": "牧場・農業体験",
    "アスレチック": "アスレチック",
    "遊園地": "遊園地",
    "テーマパーク": "テーマパーク",
    "飲食店": "飲食店",
}

# 横断ファイルの「エリア」列を地域idに読み替える。
# 台帳によって「北海道（札幌）」のようにカッコ書きが付くので、カッコは落として見る
AREA = {"関東": "kanto", "沖縄": "okinawa", "北海道": "hokkaido", "札幌": "hokkaido",
        "小田原": "odawara", "名古屋": "nagoya"}


def region_of(area_name):
    if not area_name:
        return None
    key = re.sub(r"[（(].*?[）)]", "", area_name).strip()
    return AREA.get(key) or AREA.get(area_name)

# 列名のゆれ。左が使いたい意味、右が台帳で見かける名前
ALIAS = {
    "id": ["ID"],
    "cat": ["大カテゴリ"],
    "sub": ["小カテゴリ", "ジャンル"],
    "name": ["施設・スポット", "施設名", "店名"],
    "addr": ["所在地", "所在地・代表住所"],
    "t1": ["電車_最短分", "公共交通_最短分"],
    "t2": ["電車_最長分", "公共交通_最長分"],
    "c1": ["車_最短分"],
    "c2": ["車_最長分"],
    "rain": ["雨天対応"],
    "desc": ["概要", "概要・選定根拠"],
    "age": ["おすすめ年齢"],
    "rate": ["GoogleMaps評価"],
    "note": ["注意・組み合わせ"],
    "url": ["公式URL", "公式・調査ソース"],
    "lat": ["緯度"],
    "lng": ["経度"],
    "season": ["特におすすめな月"],
    "area": ["エリア"],
}
# 区まで残す市（政令指定都市）。ここに無い市の「◯◯区」は地区名なので落とす
SEIREI = {"札幌市", "仙台市", "さいたま市", "千葉市", "横浜市", "川崎市", "相模原市",
          "新潟市", "静岡市", "浜松市", "名古屋市", "京都市", "大阪市", "堺市",
          "神戸市", "岡山市", "広島市", "北九州市", "福岡市", "熊本市"}
# 「◯◯市市」と続く市。次の字が市でも伸ばす
DOUBLE_CITY = {"四日市", "廿日市"}
PREF = r"^(東京都|北海道|京都府|大阪府|.{2,3}?県)"


def num(v):
    if v is None or v == "":
        return None
    try:
        f = float(str(v).strip())
    except ValueError:
        return None
    return int(f) if f == int(f) else f


def txt(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def months(text):
    """「4月・10～11月（花・紅葉）」→ [4,10,11]。「11～4月」のような年またぎも拾う"""
    if not text:
        return []
    got = set()
    for a, b in re.findall(r"(\d{1,2})\s*(?:[～〜~ー-]\s*(\d{1,2}))?\s*月", str(text)):
        s = int(a)
        e = int(b) if b else s
        if not (1 <= s <= 12 and 1 <= e <= 12):
            continue
        m = s
        while True:
            got.add(m)
            if m == e:
                break
            m = m % 12 + 1
    return sorted(got)


def area(addr, pref):
    """住所を「都道府県＋市区町村」まで詰める。一覧に出るので番地は落とす。

    素直に書くと地名に引っかかる。「余市町」は余市で、「豊川市市田町」は豊川市市で、
    「市原市」は市で止まってしまう。郡を先に見て、政令市だけ区を残し、
    「〜市市」になる市だけ例外として持つ。"""
    if not addr:
        return pref or ""
    a, head_pref = addr, (pref or "")
    m = re.match(PREF + r"(.+)$", a)
    if m:
        head_pref, a = m.group(1), m.group(2)

    m = re.match(r"^(.{1,8}?郡)(.{1,8}?[町村])", a)
    if m:
        return head_pref + m.group(1) + m.group(2)

    # 東京23区は市を経由しないので、区で切る（八王子市などは下の市町村で拾う）
    if head_pref == "東京都":
        m = re.match(r"^(.{1,6}?区)", a)
        if m:
            return head_pref + m.group(1)

    m = re.match(r"^(.{1,8}?[市町村])", a)
    if not m:
        return head_pref + a
    head, rest = m.group(1), a[len(m.group(1)):]
    if rest[:1] in ("町", "村") or (rest[:1] == "市" and head in DOUBLE_CITY):
        head, rest = head + rest[0], rest[1:]
    if head in SEIREI:
        m2 = re.match(r"^(.{1,6}?区)", rest)
        if m2:
            head += m2.group(1)
    return head_pref + head


def write_spots(spots):
    """1行1スポットで書く（差分が読めるように）"""
    with SPOTS.open("w", encoding="utf-8") as f:
        f.write("[\n")
        f.write(",\n".join(json.dumps(s, ensure_ascii=False) for s in spots))
        f.write("\n]\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", nargs="?", help="--purge-cat だけのときは省ける")
    ap.add_argument("--region", help="data/regions.json にある地域のid。--by-area のときは不要")
    ap.add_argument("--by-area", action="store_true",
                    help="「エリア」列で地域を振り分ける（地域をまたぐ台帳用）。既存は消さずにIDで上書き")
    ap.add_argument("--pref", default="", help="台帳の住所に都道府県が無いときに前へ付ける")
    ap.add_argument("--replace-cat", help="取り込む前に、台帳に出てくる地域のそのカテゴリを消す")
    ap.add_argument("--purge-cat", help="そのカテゴリを全地域から消す")
    ap.add_argument("--sheet", default="全スポット")
    args = ap.parse_args()

    if not args.xlsx:
        if not args.purge_cat:
            sys.exit("台帳のファイルか --purge-cat のどちらかが要る")
        cur = json.loads(SPOTS.read_text(encoding="utf-8"))
        left = [s for s in cur if s["cat"] != args.purge_cat]
        gone = len(cur) - len(left)
        write_spots(left)
        print(f"「{args.purge_cat}」を {gone}件 消した。残り {len(left)}件")
        print("npm run build:spots && npm run check を忘れずに")
        return

    regions = json.loads(REGIONS.read_text(encoding="utf-8"))
    known = {r["id"] for r in regions}
    if args.by_area:
        if args.region:
            sys.exit("--by-area と --region は同時に使えない")
    elif args.region not in known:
        sys.exit(f"data/regions.json に地域 '{args.region}' がない。先に足すこと")

    wb = openpyxl.load_workbook(args.xlsx, data_only=True)
    if args.sheet not in wb.sheetnames:
        sys.exit(f"シート '{args.sheet}' が無い。あるのは {wb.sheetnames}")
    rows = list(wb[args.sheet].iter_rows(values_only=True))
    head = {h: i for i, h in enumerate(rows[0]) if h}

    col = {}
    for key, names in ALIAS.items():
        for n in names:
            if n in head:
                col[key] = head[n]
                break
    need = ["id", "cat", "name"] + (["area"] if args.by_area else [])
    for req in need:
        if req not in col:
            sys.exit(f"必要な列が見つからない: {ALIAS[req]}")
    get = lambda r, k: r[col[k]] if k in col else None

    spots, problems = [], []
    for r in rows[1:]:
        if not get(r, "id"):
            continue
        cat = txt(get(r, "cat"))
        if cat not in CANON:
            problems.append(f"知らないカテゴリ: {cat}（{txt(get(r, 'name'))}）")
            continue
        if args.by_area:
            a = txt(get(r, "area"))
            rid = region_of(a)
            if not rid:
                problems.append(f"知らないエリア: {a}（{txt(get(r, 'name'))}）")
                continue
            if rid not in known:
                problems.append(f"エリア「{a}」に対応する地域 {rid} が regions.json にない")
                continue
        else:
            rid = args.region
        o = {
            "id": txt(get(r, "id")),
            "cat": CANON[cat],
            "sub": txt(get(r, "sub")),
            "name": txt(get(r, "name")),
            "addr": area(txt(get(r, "addr")), args.pref),
            "t1": num(get(r, "t1")), "t2": num(get(r, "t2")),
            "c1": num(get(r, "c1")), "c2": num(get(r, "c2")),
            "rain": txt(get(r, "rain")),
            "desc": txt(get(r, "desc")),
            "age": txt(get(r, "age")),
            "rate": num(get(r, "rate")) or None,   # 0 と未確認は入れない
            "note": txt(get(r, "note")),
            "url": txt(get(r, "url")),
            "lat": num(get(r, "lat")), "lng": num(get(r, "lng")),
            "region": rid,
        }
        season = txt(get(r, "season"))
        if season:
            ms = months(season)
            if ms:
                o["season"], o["months"] = season, ms
            else:
                problems.append(f"月を読み取れない: {o['id']} {season}")
        spots.append({k: v for k, v in o.items() if v is not None})

    if problems:
        print("!! 確認が要るもの:")
        for p in problems:
            print("   ", p)

    cur = json.loads(SPOTS.read_text(encoding="utf-8"))
    ids = {s["id"] for s in spots}
    if args.by_area:
        # 既存はIDで上書き。載っていないものは残す（他のカテゴリを消さないため）
        others = [s for s in cur if s["id"] not in ids]
        updated = len(cur) - len(others)
        moved = [s["id"] for s in spots
                 for o in cur if o["id"] == s["id"] and o["region"] != s["region"]]
        if moved:
            print(f"!! 地域が変わるID: {moved[:5]}（記録は残るが表示先が移る）")
    else:
        others = [s for s in cur if s["region"] != args.region]
        updated = 0
        clash = ids & {s["id"] for s in others}
        if clash:
            sys.exit(f"IDが他の地域とぶつかっている: {sorted(clash)[:5]}")

    if args.purge_cat:
        before = len(others)
        others = [s for s in others if s["cat"] != args.purge_cat]
        print(f"「{args.purge_cat}」を全地域から {before - len(others)}件 消した")
    elif args.replace_cat:
        here = {s["region"] for s in spots}
        before = len(others)
        others = [s for s in others
                  if not (s["cat"] == args.replace_cat and s["region"] in here)]
        print(f"「{args.replace_cat}」を {sorted(here)} から {before - len(others)}件 消して入れ替える")

    # 同じ座標だとピンが重なってタップできない。ずらすのは同じ地域の中だけ。
    # 地域が違えば同時に表示しないので、隣の地域と同じ座標でも困らない。
    seen = {(s["region"], s["lat"], s["lng"]): s["id"] for s in others if s.get("lat")}
    for s in spots:
        if s.get("lat") is None:
            continue
        key = (s["region"], s["lat"], s["lng"])
        if key in seen:
            s["lat"] = round(s["lat"] + 0.00045, 6)   # 約50m北
            print(f"  座標が重複: {s['id']} {s['name']} ← {seen[key]}。50mずらした")
        seen[(s["region"], s["lat"], s["lng"])] = s["id"]

    allspots = others + spots
    write_spots(allspots)

    withm = sum(1 for s in spots if s.get("months"))
    withr = sum(1 for s in spots if s.get("rate"))
    nopos = sum(1 for s in spots if s.get("lat") is None)
    where = "エリア列で振り分け" if args.by_area else args.region
    print(f"{where}: {len(spots)}件を取り込んだ"
          f"（うち上書き {updated}件 / 評価 {withr}件 / おすすめ月 {withm}件 / 座標なし {nopos}件）")
    print(f"住所の例: {sorted({s['addr'] for s in spots})[:6]}")
    print(f"合計 {len(allspots)}件。npm run build:spots && npm run check を忘れずに")


if __name__ == "__main__":
    main()
