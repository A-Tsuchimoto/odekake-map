# 引き継ぎメモ

別のスレッド／別の人がこのリポジトリを引き継ぐときに、最初に読むもの。
何をするアプリかは [README](../README.md)、コードを触るときの決まりは
[CLAUDE.md](../CLAUDE.md)、台帳（Excel）の作り方は [docs/LEDGER.md](LEDGER.md)、
座標の入れ方と住所からの推定は [docs/COORDS.md](COORDS.md)。

最終更新: 2026-07-29

---

## 1. いまの状態

- **公開先**: Cloudflare **Workers**（Pages ではない）。Worker名 `odekake-map`
- **デプロイ**: GitHub連携。push すると Cloudflare 側が `npx wrangler deploy` を実行する
- **作業ブランチ**: `claude/outing-map-cloudflare-2nhqik`（このリポジトリの既定ブランチ）
- **データ**: 5地域・708件（うち飲食店101件、ホテル・宿15件）。内訳は README の表

| 地域 | 起点 | 件数 | 座標なし | Google評価 | おすすめ月 |
|---|---|---|---|---|---|
| 関東 kanto | 高田駅 | 238 | 0 | 183 | 61 |
| 沖縄 okinawa | 県庁前駅 | 150 | 0 | 1 | 34 |
| 北海道 hokkaido | 札幌駅 | 141 | 0 | 128 | 64 |
| 小田原 odawara | 小田原駅 | 93 | 0 | 84 | 69 |
| 名古屋 nagoya | 名古屋駅 | 86 | 0 | 72 | 53 |

**飲食店は2026-07-28に作り直した**。旧112件（`KNT-FOD-*` 形式、座標なし）を全削除し、
新しい台帳から93件を入れ直した（関東52・北海道12・名古屋12・沖縄9・小田原8）。
新IDは `KNT-MEN-001` `SPK-YKN-001` のような形式で、座標が入っているので地図にも出る。

**体験プログラムのタグを2026-07-29に足した**。調査JSON（685件分）から255件にタグが付き、
12区分（`xg`）と対象年齢3区分（`ages`、全件）で絞り込めるようにした。
内訳は関東93・北海道58・沖縄40・名古屋38・小田原26。取り込みは
`python3 scripts/import-experience.py 調査.json`。区分の一覧と入力の形は docs/LEDGER.md。
**カテゴリや訪問状況と選び方が逆**（押したものだけに絞る／何も押さなければ絞らない）なので、
チップの見た目も別扱いにしてある（`.chips.opt`）。

**ホテル・宿を2026-07-29に足した**。13番目のカテゴリで、沖縄のビーチ付きリゾート15件
（`OKI-HOT-001`〜`015`）。泊まる先として見るためのもので、ビーチの形（直結／敷地内／
送迎）は小カテゴリに書いてある。JSONでもらったので `scripts/import-spots-json.py` で
取り込んだ。Google評価は未取得。他の地域にはまだ無い。

**二郎系ラーメンを2026-07-29に8件足した**（`KNT-MEN-023`〜`025`、`SPK-MEN-006`、
`OKI-MEN-005`、`ODA-MEN-004`、`NGY-MEN-006`〜`007`）。小カテゴリを
「麺類（二郎系・直系）」「麺類（二郎系インスパイア）」で揃えてあるので、
検索の「二郎系」で全部引ける。新しく開いた4店は地図サイトに座標が無かったので、
住所から町丁目の代表点を引いて入れた（`approx: true`）。

**スポットの検索を2026-07-29に足した**。パネル最上段の「さがす」。名前だけでなく
小カテゴリ・住所・概要・注意書き・年齢・おすすめ月・体験のタグとプログラム名まで見る
（`hay()` が作った文字列をスポットの `q` に覚えさせている）。カタカナ／ひらがな、
全角／半角は寄せてから当てる。空白区切りはAND。**今の地域の中だけ**を探し、
0件のときは他の地域の件数を出して飛べるようにした。

## 2. Cloudflare 側の設定（コードに書けないもの）

| もの | 値・場所 |
|---|---|
| KVバインディング | `RECORDS`。名前空間IDは `wrangler.toml` に記載済み |
| あいことば | `APP_TOKEN`。Worker > Settings > Variables and Secrets に **Secret** で登録 |
| ビルド設定 | Build command は空、Deploy command は `npx wrangler deploy`、Root は `/` |
| 公開URL | `https://odekake-map.<サブドメイン>.workers.dev` |

- シークレットもバインディングも、**入れただけでは既存のデプロイに効かない**。
  入れたあとに再デプロイ（または空push）が要る
- 動作確認は `/api/records` を直接開く。**401が正常**（あいことば無しのため）。
  500ならKVかシークレットが未反映

## 3. よく使うコマンド

```bash
npm install
npm run dev            # http://localhost:8787（wrangler dev）
npm run check          # データ + wrangler.toml + _headers の検査。CIもこれ
npm run build:spots    # data/*.json → public/spots.js
npm run deploy         # 手元からデプロイしたいとき（普段はpushで足りる）

# 台帳の取り込み（要 pip install openpyxl）
python3 scripts/import-ledger.py 台帳.xlsx --region nagoya          # 1エリア分
python3 scripts/import-ledger.py 台帳.xlsx --by-area                # エリア列で振り分け
python3 scripts/import-ledger.py 台帳.xlsx --by-area --replace-cat 飲食店   # カテゴリごと差し替え
python3 scripts/import-ledger.py --purge-cat 飲食店                  # 全地域から消すだけ
python3 scripts/import-ledger.py 台帳.xlsx --only season             # その列だけ反映

# 体験プログラムの調査JSON（IDで突き合わせ。体験まわりの項目だけ入れ直す）
python3 scripts/import-experience.py 体験調査.json

# スポットの追加分をJSONでもらったとき（IDがあれば上書き、無ければその地域の後ろに足す）
python3 scripts/import-spots-json.py 追加.json
python3 scripts/import-spots-json.py 追加.json --geocode   # 座標が無いものを住所から補う
python3 scripts/geocode-jp.py 沖縄県那覇市壺屋1-6-16        # 住所→緯度経度を見るだけ
                                                          # 手順と精度は docs/COORDS.md
```

`data/spots.json` `data/regions.json` を直したら **必ず** `npm run build:spots`。
`public/spots.js` は生成物なので手で編集しない。

## 4. 動作確認のしかた

この環境からは cdnjs に出られないので、ブラウザ確認は **Playwright で Leaflet を
差し替えて**行っている。毎回このパターンを使うと確実。

```js
import { chromium } from "playwright";
import { readFileSync } from "node:fs";
const leafletJs = readFileSync("node_modules/leaflet/dist/leaflet.js", "utf8");
const leafletCss = readFileSync("node_modules/leaflet/dist/leaflet.css", "utf8");
const b = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",  // 版が合わないので明示
  args: ["--no-sandbox"],
});
const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } });
await ctx.route("https://cdnjs.cloudflare.com/**", r => {
  const u = r.request().url();
  if (u.endsWith(".css")) return r.fulfill({ status: 200, contentType: "text/css", body: leafletCss });
  if (u.endsWith(".js")) return r.fulfill({ status: 200, contentType: "application/javascript", body: leafletJs });
  return r.fulfill({ status: 404, body: "" });
});
await ctx.route("https://fonts.googleapis.com/**", r => r.fulfill({ status: 200, contentType: "text/css", body: "" }));
await ctx.route("https://*.basemaps.cartocdn.com/**", r => r.abort());   // タイルは来ないので黙らせる
```

準備: `npm install --no-save playwright leaflet`。
確認は**データから期待値を計算して突き合わせる**（例: 「7月の絞り込み32件」を
`spots.json` から数えた値と比べる）。目視だけだとずれに気づけない。

スマホは `viewport 390x740 / isMobile: true` で見る。パネルが下のシートになるので、
`#sheetBtn` を押してから一覧を触ること。

## 5. これまでに踏んだ落とし穴

同じところで転ばないように。詳しい理由は CLAUDE.md にも短く書いてある。

| 症状 | 原因 | 対処 |
|---|---|---|
| デプロイが `Missing entry-point to Worker script` で落ちる | Pages用の設定（`pages_build_output_dir`）のまま Workers にデプロイした | `main` + `[assets]` を使う。Pages用の記述を残さない |
| ビルドがTOMLの構文エラー | KVのIDをクオート無しで貼った（数字始まりの32桁） | `id = "..."` と必ず引用符で囲む。`npm run check` が検出する |
| **2回目の読み込みから地図が消える** | CSPの `connect-src` が `'self'` だけ。SW内の `fetch()` が cdnjs とタイルを取れない | `script-src`/`img-src` と同じホストを `connect-src` にも入れる。`npm run check` が検出する |
| 記入するたびにポップアップが閉じる | `render()` が全マーカーを消して入れ直していた | 差分更新にした。一覧のカードも節点を預けて挿し直す |
| 画面が真っ白／`0 / 0 件` | `let` 宣言より前に `render()` が呼ばれた（TDZ） | 変数は使う場所より前で宣言する。構文チェックでは見つからない |
| 拡大するとボタンが効かない | Leafletの `popup.update()` が中身を作り直す | `wirePopup()` でつなぎ直す |
| 地図の描画が重い | 一覧183行のレイアウト、施設名ラベル全件、スライダーごとの再描画 | `content-visibility`、ラベル60件上限、rAFで1フレーム1回 |

## 6. 決めたこと（迷ったら思い出す）

- **地域が最上位**。スポットは必ず1つの地域に属し、所要時間と距離の輪はその起点基準
- **地域は重なってよい**（小田原と関東で14件）。同時に表示しないので困らない。
  ただし**IDが別なら記録も別**。同じ施設を2地域に置くと訪問記録は共有されない
- **カテゴリは13分類で固定**。台帳ごとの表記ゆれは取り込み時に寄せる
- **スポットIDは絶対に変えない**。記録がIDで紐づいているため
- **推測でデータを埋めない**。評価も座標も、無いものは空のまま持つ。
  住所から引いた座標（町丁目の代表点）だけは例外で、`approx: true` を付けて
  「およその位置」と画面に出す
- **変わりやすいものは持たない**。体験の日程・料金・予約方法は取り込まず、
  一次情報のURL（`xurl`）に送る
- **タグの絞り込みは「押したものだけ」**。全部押した状態から始めると、
  タグの無いスポットが消えてしまう
- **1枚のHTMLを保つ**。ビルド工程を入れない

## 7. 残っている課題

- **飲食店のGoogle評価が未取得**（台帳が空欄）。沖縄のスポット125件とホテル15件も同様。
  台帳に入ったら `--by-area --replace-cat 飲食店` で差し替える
- **体験タグの無い430件**（700件中270件に付いている）。調査で「該当なし」だったもので、飲食店もここに入る。
  新しく体験を見つけたら、そのIDだけのJSONを作って取り込み直せばよい
- **旧飲食店IDの記録がKVに残る**。`KNT-FOD-*` に記録を付けていた場合、
  新IDとは紐づかないので表示されない（害はないが消えない）
- **オフラインで付けた記録が自動再送されない**。端末に控えるだけなので、
  復帰後に手動で「つなぐ」が要る。直すなら sw.js の Background Sync か `online` イベント
- 記録は毎回まるごとPOST。件数が増えたら差分更新を検討（競合の扱いを先に決めること）
- KVは結果整合性。複数端末で同時に編集する使い方に広げるなら D1 へ
- **`approx` の4件**（新しい二郎系）。町名の代表点なので数十〜250mずれる。
  正確な座標が分かったら同じIDで流し直す（docs/COORDS.md）
- 記録のCSV書き出し（JSONは実装済み）、写真添付（R2）、再訪記録は未着手
