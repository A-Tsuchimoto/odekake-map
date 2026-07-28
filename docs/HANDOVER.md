# 引き継ぎメモ

別のスレッド／別の人がこのリポジトリを引き継ぐときに、最初に読むもの。
何をするアプリかは [README](../README.md)、コードを触るときの決まりは
[CLAUDE.md](../CLAUDE.md)、台帳（Excel）の作り方は [docs/LEDGER.md](LEDGER.md)。

最終更新: 2026-07-28

---

## 1. いまの状態

- **公開先**: Cloudflare **Workers**（Pages ではない）。Worker名 `odekake-map`
- **デプロイ**: GitHub連携。push すると Cloudflare 側が `npx wrangler deploy` を実行する
- **作業ブランチ**: `claude/outing-map-cloudflare-2nhqik`（このリポジトリの既定ブランチ）
- **データ**: 5地域・644件（うち飲食店52件）。内訳は README の表

| 地域 | 起点 | 件数 | 座標なし | Google評価 | おすすめ月 |
|---|---|---|---|---|---|
| 関東 kanto | 高田駅 | 235 | 0 | 183 | 61 |
| 沖縄 okinawa | 県庁前駅 | 125 | 0 | 1 | 0 |
| 北海道 hokkaido | 札幌駅 | 128 | 0 | 128 | 0 |
| 小田原 odawara | 小田原駅 | 84 | 0 | 84 | 69 |
| 名古屋 nagoya | 名古屋駅 | 72 | 0 | 72 | 53 |

**飲食店は作り直し中**。2026-07-28に旧112件を全削除し、新しい関東52件だけ入れた。
沖縄・北海道・小田原は新リストができ次第エリアごとに入れ替える（名古屋はまだ無い）。
旧IDは `KNT-FOD-*` 形式、新IDは `KNT-MEN-001` のような形式で、体系が変わっている。

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
npm run dev            # http://localhost:8788（wrangler dev）
npm run check          # データ + wrangler.toml + _headers の検査。CIもこれ
npm run build:spots    # data/*.json → public/spots.js
npm run deploy         # 手元からデプロイしたいとき（普段はpushで足りる）

# 台帳の取り込み（要 pip install openpyxl）
python3 scripts/import-ledger.py 台帳.xlsx --region nagoya          # 1エリア分
python3 scripts/import-ledger.py 台帳.xlsx --by-area                # エリア列で振り分け
python3 scripts/import-ledger.py 台帳.xlsx --by-area --replace-cat 飲食店   # カテゴリごと差し替え
python3 scripts/import-ledger.py --purge-cat 飲食店                  # 全地域から消すだけ
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
- **カテゴリは12分類で固定**。台帳ごとの表記ゆれは取り込み時に寄せる
- **スポットIDは絶対に変えない**。記録がIDで紐づいているため
- **推測でデータを埋めない**。評価も座標も、無いものは空のまま持つ
- **1枚のHTMLを保つ**。ビルド工程を入れない

## 7. 残っている課題

- **飲食店の入れ直し**。関東52件だけ入っている。沖縄・北海道・小田原は削除済みで、
  新しい台帳を待っている状態。入れるときは
  `--by-area --replace-cat 飲食店` でエリアごとに差し替える
- **飲食店のGoogle評価が未取得**（台帳が空欄）。沖縄125件のスポットも同様
- **旧飲食店IDの記録がKVに残る**。`KNT-FOD-*` に記録を付けていた場合、
  新IDとは紐づかないので表示されない（害はないが消えない）
- **オフラインで付けた記録が自動再送されない**。端末に控えるだけなので、
  復帰後に手動で「つなぐ」が要る。直すなら sw.js の Background Sync か `online` イベント
- 記録は毎回まるごとPOST。件数が増えたら差分更新を検討（競合の扱いを先に決めること）
- KVは結果整合性。複数端末で同時に編集する使い方に広げるなら D1 へ
- 記録のCSV書き出し（JSONは実装済み）、写真添付（R2）、再訪記録は未着手
