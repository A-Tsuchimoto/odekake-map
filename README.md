# 高田駅発 家族お出かけマップ

横浜市営地下鉄グリーンライン高田駅を起点に、家族で行ける128スポットを地図で見て、
行ったら記録を残すための個人用ウェブアプリ。利用者は本人ひとり。スマホからの利用が主。

Cloudflare Pages で公開する前提。ビルドは要らないので、リポジトリの中身がそのまま公開物になる。

- 地図は Leaflet + CARTO のタイル。フレームワークなし
- スポット128件は `public/spots.js`（`window.__SPOTS__`）に静的に持つ
- 訪問記録は Pages Functions 経由で Workers KV に保存する
- サービスワーカーで、アプリ本体と地図タイルをキャッシュしてオフラインでも開ける
- ホーム画面に追加すればアプリのように開く（PWA）

## 構成

```
public/                   ← ここがそのまま公開される（pages_build_output_dir）
  index.html              地図本体。CSS・JSすべて内包。依存はLeafletのCDNのみ
  spots.js                スポット128件のデータ。data/spots.json から生成する
  sw.js                   オフライン用キャッシュ
  _headers                セキュリティヘッダとキャッシュ指定
  manifest.webmanifest    ホーム画面追加用
  icon-192.png / icon-512.png
functions/
  api/records.js          GET/POST /api/records。X-Token で認証し、KVに読み書き
data/
  spots.json              スポットの元データ。ここを直して npm run build:spots
scripts/
  build-spots.mjs         spots.json → spots.js の生成と検査
wrangler.toml             Pagesの設定とKVバインディング（設定の正はこれ）
.github/workflows/check.yml    push時に spots データを検査する（デプロイはCloudflare側）
```

## 公開の手順

GitHub連携（Workers & Pages > Create > Pages > Connect to Git）で運用している。
push すると Cloudflare 側が勝手にビルドして出す。CLIは要らない。

設定の正は `wrangler.toml`。ダッシュボードでは同じ項目が灰色になって編集できないので、
バインディングを変えるときはこのファイルを直して push する。
例外は**あいことば（APP_TOKEN）**で、これはファイルに書けないのでダッシュボードで入れる。

初回にやること。

1. **KVを作る** — ダッシュボード左 **Storage & Databases > KV**（Workers KV の画面）で
   **Create instance**。名前は `odekake-map-records`。作った行に出る
   **Namespace ID**（32桁の英数字）をコピーする
2. **IDを貼る** — `wrangler.toml` の `PUT_YOUR_KV_NAMESPACE_ID_HERE` を差し替えて push。
   GitHubのWeb編集でもよい。ここが未設定だとデプロイが失敗する
3. **あいことばを入れる** — Pagesプロジェクト > **Settings > Variables and Secrets > Add**。
   Type は **Secret**、名前は `APP_TOKEN`、値は好きな文字列。Production に入れる
4. **もう一度デプロイする** — シークレットもバインディングも、**入れただけでは効かない**。
   Deployments の最新デプロイの **⋯ > Retry deployment**（または空push）で作り直す

`https://odekake-map.pages.dev` で開く。スマホで開いて「ホーム画面に追加」。

初回だけ、パネルの「あいことば」に APP_TOKEN と同じ文字列を入れて「つなぐ」を押す。
以後その端末には保存され、記録は自動でKVに書かれる。

うまくいかないときは `/api/records` を直接開く。401なら正常（あいことば無しなので）。
500なら KV かシークレットが効いていない＝手順4のやり直し漏れ。

### デプロイが止まるとき

Pagesプロジェクト > **Deployments** > 失敗したデプロイをクリックすると、
どこで止まったかがログで分かる。よくあるのは次の4つ。

| ログに出るもの | 原因 | 直し方 |
|---|---|---|
| `Unable to parse` / TOML の構文エラー | `wrangler.toml` の書き方。IDのクオート忘れが多い | `id = "..."` と**必ず引用符で囲む**。数字始まりの32桁なので裸で書くと壊れる |
| `project name` が合わない旨 | `wrangler.toml` の `name` と、実際のPagesプロジェクト名が違う | プロジェクト名（`*.pages.dev` の左側）に `name =` を合わせる |
| `KV namespace ... not found` | IDが違う／別アカウントの名前空間 | Storage & Databases > KV でIDを取り直して貼る |
| `npm install` あたりで失敗 | ビルドイメージのNodeが古い | `.node-version`（このリポジトリに入っている）が効く。効かなければ Settings > Variables に `NODE_VERSION=22` |

ビルド設定そのものは **Settings > Builds** で、Build command は**空**、Root directory は `/`。
Build output directory は `wrangler.toml` の `pages_build_output_dir` が優先されるので触らなくてよい。

### プレビュー（本番ブランチ以外）

別ブランチを push するとプレビューURLが出る。プレビューにKVを効かせたいときは、
KVをもう1つ作って `wrangler.toml` の `[env.preview]` のコメントを外す。
本番の記録を触らせないよう、名前空間は必ず分けること。

### 手元で動かす

```bash
npm install
cp .dev.vars.example .dev.vars   # APP_TOKEN=すきなあいことば に書き換える
npm run dev                      # http://localhost:8788
```

ローカルのKVは `.wrangler/` の中に作られる。本番のデータには触らない。

## スポットを増やす・直す

`data/spots.json` を直してから、必ず生成し直す。

```bash
npm run build:spots   # public/spots.js を作り直す
npm run check         # 中身の検査だけ（CIが回しているのもこれ）
```

検査で弾いているのは、公開してから気づくと面倒なものだけ。
IDの重複、緯度経度の抜けや関東圏外、`index.html` の `COLORS` にないカテゴリ（灰色ピンになる）、
座標が完全に同じ2件（ピンが重なってタップできない）。

スポット1件の形。空の項目はキーごと省いてある。

| キー | 意味 |
|---|---|
| `id` | S001 / W001 のような一意のID。記録との突き合わせに使う。**変えないこと** |
| `cat` / `sub` | 大カテゴリ（11種）／小カテゴリ |
| `name` / `addr` | 施設名／所在地 |
| `t1` `t2` / `c1` `c2` | 高田駅からの電車・車の所要時間（最短・最長、分） |
| `rain` | 雨天対応 ◎＝ほぼ屋内 ○＝屋内中心 △＝天候で楽しみが減る ×＝屋外中心 |
| `desc` / `note` / `age` / `rate` | 概要／注意事項／おすすめ年齢／Google Maps評価 |
| `lat` / `lng` | 代表地点の緯度経度（世界測地系） |

座標は施設位置か、公園・山・海岸などは主要入口や中心部の代表地点。範囲全体ではない。

記録1件の形（KV。スポットIDをキーにしたオブジェクト）。

```json
{ "S001": { "ID": "S001", "訪問状況": "訪問済み", "訪問日": "2026-07-26",
            "満足度": "5", "家族メモ": "ロケットの模型に釘付けだった" } }
```

`訪問状況` は 候補 / 行きたい / 予定 / 訪問済み / 見送り のいずれか。この5つは
ピンの見た目とフィルタに直結しているので、増やすなら `STATUS` の定義も直すこと。

## 壊してはいけないところ

- **スポットIDと記録の対応**。IDを振り直すと過去の記録が全部迷子になる
- **あいことば1つで全部が守られている**。`APP_TOKEN` が漏れると誰でも記録を書き換えられる。
  家族それぞれのログインが要るようになったら Cloudflare Access に替えること
- **`public/_headers` の CSP**。読み込み先を増やしたらここにも足す。
  足し忘れると手元では動いて本番でだけ黙って止まる
- **保存の粒度**。記録は毎回オブジェクト全体を丸ごとPOSTしている。件数が数百のうちは
  これで問題ないが、差分更新に変えるなら競合の扱いを決めてから
- **KVの結果整合性**。書いた直後に別端末から読むと古い値が返ることがある。
  複数端末で同時に編集する使い方に広げるなら、KVではなくD1に移すこと
- **オフライン時の書き込み**。今はネットワークが切れると端末側に控えるだけで、
  復帰後の自動再送はしていない。「つなぐ」を押すと取得はするが、控えは反映されない。
  ここは既知の穴（下のTODO参照）

## 座標が重なっている2組

同じ建物・同じ敷地にあるため、両方タップできるよう約50mずらしてある。
元データの座標は同一なので、データを作り直すときは同じ処理が要る。

- 気象科学館 (S015) と 港区立みなと科学館 (S004) — 同一建物
- よみうりランド (A002) と ポケパーク カントー (T014) — 同一敷地

## TODO

- [ ] オフラインで付けた記録を、復帰時に自動で送り直す（今は手動で「つなぐ」）
- [ ] 記録のCSV書き出し（元のExcel台帳に戻すため。JSON書き出しは実装済み）
- [ ] 写真の添付。KVには置かず R2 を使うこと
- [ ] 「今週末どこ行く」提案。天気APIと雨天対応の列を突き合わせると効きそう
- [ ] 訪問済みスポットの再訪記録（今は1スポット1記録しか持てない）

## 出どころ

元は `高田駅_家族お出かけスポット統合_座標追加.xlsx` という手作りの台帳。
所要時間は休日昼間の概算で、渋滞や乗換で変動する。Google Maps評価は2026-07-26時点の参考値。
