# 高田駅発 家族お出かけマップ

横浜市営地下鉄グリーンライン高田駅を起点に、家族で行ける128スポットを地図で見て、
行ったら記録を残すための個人用ウェブアプリ。利用者は本人ひとり。スマホからの利用が主。

Cloudflare Workers（静的アセット + Worker）で公開する前提。
バンドルもビルドも要らず、`public/` の中身がそのまま配られる。

- 地図は Leaflet + CARTO のタイル。フレームワークなし
- スポット128件は `public/spots.js`（`window.__SPOTS__`）に静的に持つ
- 訪問記録は Worker 経由で Workers KV に保存する
- サービスワーカーで、アプリ本体と地図タイルをキャッシュしてオフラインでも開ける
- ホーム画面に追加すればアプリのように開く（PWA）

## 構成

```
public/                   ← 静的アセット。ここがそのまま配られる
  index.html              地図本体。CSS・JSすべて内包。依存はLeafletのCDNのみ
  spots.js                スポット128件のデータ。data/spots.json から生成する
  sw.js                   オフライン用キャッシュ
  _headers                セキュリティヘッダとキャッシュ指定
  manifest.webmanifest    ホーム画面追加用
  icon-192.png / icon-512.png
src/
  index.js                Workerの入口。/api/records 以外は静的アセットに渡す
  records.js              GET/POST /api/records。X-Token で認証し、KVに読み書き
data/
  spots.json              スポットの元データ。ここを直して npm run build:spots
scripts/
  build-spots.mjs         spots.json → spots.js の生成と検査
  check-config.mjs        wrangler.toml の検査
wrangler.toml             Workerの設定とKVバインディング（設定の正はこれ）
.github/workflows/check.yml    push時にデータと設定を検査する（デプロイはCloudflare側）
```

## 公開の手順

GitHub連携で運用している（**Workers & Pages > Create > Workers > Import a repository**）。
push すると Cloudflare 側が `npx wrangler deploy` を走らせて出す。手元のCLIは要らない。

**Pagesではなく Workers として作ること。** Pages用の設定（`pages_build_output_dir`）で
Workers のビルドに流すと `Missing entry-point to Worker script` で必ず落ちる。

設定の正は `wrangler.toml`。バインディングを変えるときはこのファイルを直して push する。
例外は**あいことば（APP_TOKEN）**で、これはファイルに書けないのでダッシュボードで入れる。

初回にやること。

1. **KVを作る** — ダッシュボード左 **Storage & Databases > KV** で **Create instance**。
   名前は `odekake-map-records`。作った行に出る **Namespace ID**（32桁の英数字）をコピー
2. **IDを貼る** — `wrangler.toml` の `id = "..."` を差し替えて push。GitHubのWeb編集でよい。
   **必ず引用符で囲むこと。** 裸で書くとTOMLが壊れてビルドが落ちる
3. **あいことばを入れる** — Worker > **Settings > Variables and Secrets > Add** で
   Type は **Secret**、名前 `APP_TOKEN`、値は好きな文字列
4. **もう一度デプロイする** — シークレットは**入れただけでは既存のデプロイに効かない**。
   Deployments から最新をやり直すか、空pushする

`https://odekake-map.<自分のサブドメイン>.workers.dev` で開く。
スマホで開いて「ホーム画面に追加」。

初回だけ、パネルの「あいことば」に APP_TOKEN と同じ文字列を入れて「つなぐ」を押す。
以後その端末には保存され、記録は自動でKVに書かれる。

うまくいかないときは `/api/records` を直接開く。401なら正常（あいことば無しなので）。
500なら KV かシークレットが効いていない＝手順4のやり直し漏れ。

### デプロイが止まるとき

Worker > **Deployments**（または Builds）で失敗したものを開くとログが読める。
実際に踏んだものを含めて、よくあるのは次の4つ。

| ログに出るもの | 原因 | 直し方 |
|---|---|---|
| `Missing entry-point to Worker script` | Pages用の設定のままWorkersにデプロイした | `wrangler.toml` に `main` と `[assets]` を書く（今はそうなっている） |
| `Unable to parse` / TOMLの構文エラー | KVのIDのクオート忘れ | `id = "..."` と引用符で囲む。数字始まりの32桁なので裸で書くと壊れる |
| Worker名が合わない旨 | `wrangler.toml` の `name` と実際のWorker名が違う | ダッシュボードのWorker名に `name =` を合わせる |
| `npm install` あたりで失敗 | ビルドイメージのNodeが古い | `.node-version`（同梱）が効く。効かなければ変数に `NODE_VERSION=22` |

`npm run check` が push 前に同じ壊れ方を検出する。CIでも毎回走っている。

ビルド設定は **Settings > Build**。Build command は**空**、Deploy command は
`npx wrangler deploy`、Root directory は `/`。

### プレビュー（本番ブランチ以外）

別ブランチを push するとプレビューURLが出る。バインディングは本番と同じものを使うので、
**プレビューから書いた記録も本番のKVに入る**。試し書きするときは注意。

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
