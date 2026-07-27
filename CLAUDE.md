# CLAUDE.md

おひさまマップ（家族のお出かけ記録）。個人用の1枚もののウェブアプリで、Cloudflare Workers に置く
（静的アセット + `src/index.js`。Pages ではない）。
何をするものか・どう公開するかは README.md に書いてある。ここは作業するときの決まりごとだけ。

## 作りの前提

- **ビルド工程はない**。`public/` の中身がそのまま配られる。バンドラもフレームワークも入れない
- **記録APIは `src/records.js`**。`src/index.js` が `/api/records` だけを拾い、残りは静的アセットに渡す
- `public/index.html` に CSS も JS も全部入っている。ファイルを分けるより、この1枚を保つ方を優先する
- 外部依存は Leaflet(cdnjs)、Googleフォント、CARTOのタイルだけ。増やすときは
  `public/_headers` の CSP と `public/sw.js` のキャッシュ対象も一緒に直す。
  どちらかを忘れると、手元では動いて本番でだけ止まる
- **CSPの `connect-src` には、`script-src`／`img-src` と同じ外部ホストを必ず入れる**。
  サービスワーカーが全リクエストを取り次ぐので、SW内の `fetch()` は `connect-src` で判定される。
  入れ忘れると1回目は動いて、2回目の読み込みから地図が消える。`npm run check` が見ている

## 直したら必ずやること

```bash
npm run check    # spots.json の検査 + spots.js が最新か + wrangler.toml の書式
npm run dev      # http://localhost:8788 で実際に開いて確かめる
```

`wrangler.toml` を直すときは `main` と `[assets]` を消さないこと。
Pages用の `pages_build_output_dir` を書くとデプロイが入口を見つけられずに落ちる。

`data/spots.json` `data/regions.json` を直したときは `npm run build:spots`。
`public/spots.js` を手で編集しない。

## 触るときに気をつけるところ

- **地域（`data/regions.json`）が一番上の区切り**。スポットは必ずどれか1つに属する。
  `center` が起点で、所要時間の基準であり距離の輪の中心。地域を足すときは
  スポット側の `region` と、その地域の起点から測り直した `t1/t2/c1/c2` が要る
- **カテゴリは11分類で統一**。台帳ごとに表記が違っても、取り込むときに寄せる。
  地域ごとに別のカテゴリを作らない（チップが倍に増える）
- **スポットIDは変えない**。記録はIDで突き合わせているので、振り直すと過去の記録が迷子になる
- **`訪問状況` の5値**（候補／行きたい／予定／訪問済み／見送り）はピンの見た目とフィルタに
  直結している。増やすなら `index.html` の `STATUS` と、状況チップの色も直す
- **カテゴリを増やすなら `index.html` の `COLORS` にも足す**。ないと灰色ピンになる。
  `npm run check` がこれを見ている
- **記録は毎回まるごとPOST**している。差分更新に変えるなら競合の扱いを先に決めること
- **KVは結果整合性**。書いた直後に別端末で読むと古い値が返る。複数端末で同時に編集する
  使い方に広げるなら D1 に移す
- **認証はあいことば1つだけ**（`APP_TOKEN` を `X-Token` で突き合わせ）。利用者が本人ひとりなので
  これで足りている。家族それぞれのログインが要るなら Cloudflare Access に替える

## 既知の穴

オフラインで付けた記録は端末に控えるだけで、復帰後に自動で送り直さない。
直すなら sw.js の Background Sync か、`online` イベントでの再送。他のTODOは README.md に。
