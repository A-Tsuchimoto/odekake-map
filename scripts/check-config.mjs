#!/usr/bin/env node
/**
 * wrangler.toml の見張り。Cloudflare のビルドログを読みに行く前に、push の時点で
 * 気づけるようにする。実際にここで転んだのは「KVのIDをクオートせずに貼った」。
 * TOML的に壊れているのでビルドは必ず落ちるが、エラーはCloudflare側にしか出ない。
 *
 * 完全なTOMLパーサではない。この1ファイルで起きうる壊れ方だけを見ている。
 */
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const raw = readFileSync(join(root, "wrangler.toml"), "utf8");

const problems = [];
const fail = (m) => problems.push(m);

/** コメントを落とした行 */
const lines = raw
  .split("\n")
  .map((l, i) => [i + 1, l])
  .filter(([, l]) => l.trim() && !l.trim().startsWith("#"));

const valueOf = (key) => {
  const hit = lines.find(([, l]) => l.trim().startsWith(key + " ") || l.trim().startsWith(key + "="));
  if (!hit) return null;
  const m = hit[1].match(/=\s*(.+?)\s*$/);
  return m ? { line: hit[0], raw: m[1] } : null;
};

const quoted = (v) => /^"[^"]*"$/.test(v);

for (const key of ["name", "main", "compatibility_date", "directory", "binding"]) {
  const v = valueOf(key);
  if (!v) fail(`${key} がない`);
  else if (!quoted(v.raw)) fail(`${v.line}行目: ${key} は引用符で囲むこと（今: ${v.raw}）`);
}

/* Pages用の書き方が残っていると wrangler deploy が入口を見つけられない */
if (/^\s*pages_build_output_dir/m.test(raw.replace(/^\s*#.*$/gm, ""))) {
  fail("pages_build_output_dir が残っている。Workersでは main と [assets] を使う");
}

const entry = valueOf("main");
if (entry && quoted(entry.raw) && !existsSync(join(root, entry.raw.slice(1, -1)))) {
  fail(`main の "${entry.raw.slice(1, -1)}" が無い`);
}

const dir = valueOf("directory");
if (dir && quoted(dir.raw)) {
  const d = dir.raw.slice(1, -1);
  if (!existsSync(join(root, d))) fail(`[assets] の directory "${d}" が無い`);
  else if (!existsSync(join(root, d, "index.html"))) fail(`"${d}/index.html" が無い。公開しても何も出ない`);
}

/** KVバインディング。id は32桁の16進を引用符で囲んだもの */
let kvCount = 0;
for (const [n, line] of lines) {
  if (line.trim() === "[[kv_namespaces]]" || /^\[\[env\.\w+\.kv_namespaces\]\]$/.test(line.trim())) kvCount++;
  const m = line.match(/^\s*id\s*=\s*(.+?)\s*$/);
  if (!m) continue;
  const v = m[1];
  if (!quoted(v)) {
    fail(`${n}行目: KVのIDは引用符で囲むこと → id = "${v.replace(/"/g, "")}"`);
  } else {
    const id = v.slice(1, -1);
    if (/^PUT_YOUR/.test(id)) fail(`${n}行目: KVのIDが未設定のまま。ダッシュボードで作った名前空間のIDを貼ること`);
    else if (!/^[0-9a-f]{32}$/.test(id)) fail(`${n}行目: KVのIDは32桁の英数字のはず（今: ${id}）`);
  }
}
if (!kvCount) fail("[[kv_namespaces]] がない。記録APIがKVを使えない");

/** 記録APIの本体 */
if (!existsSync(join(root, "src", "records.js"))) {
  fail("src/records.js が無い。記録の保存先が消える");
}

/* public/_headers の CSP。
   サービスワーカーが全リクエストを取り次ぐので、SW内の fetch() は connect-src で判定される。
   script-src などに書いた外部ホストを connect-src に入れ忘れると、
   1回目は動いて2回目の読み込みから地図が消える。実際にこれで壊した。 */
const headersPath = join(root, "public", "_headers");
if (!existsSync(headersPath)) {
  fail("public/_headers が無い。CSPとキャッシュ指定が消える");
} else {
  const csp = readFileSync(headersPath, "utf8")
    .split("\n")
    .filter((l) => !l.trim().startsWith("#"))
    .find((l) => /content-security-policy:/i.test(l));
  if (!csp) {
    fail("_headers に Content-Security-Policy がない");
  } else {
    const directive = (name) => {
      const m = csp.match(new RegExp(`(?:^|;)\\s*${name}\\s+([^;]+)`, "i"));
      return m ? m[1].trim().split(/\s+/) : [];
    };
    const hosts = (list) => list.filter((v) => v.startsWith("https://"));
    const connect = directive("connect-src");
    for (const d of ["script-src", "style-src", "img-src", "font-src"]) {
      for (const host of hosts(directive(d))) {
        if (!connect.includes(host)) {
          fail(`CSP: ${d} の ${host} が connect-src にない。サービスワーカー経由で取れなくなる`);
        }
      }
    }
    if (!connect.includes("'self'")) fail("CSP: connect-src に 'self' がない。記録APIを呼べない");
  }
}

if (problems.length) {
  console.error(`設定に ${problems.length} 件の問題:`);
  for (const p of problems) console.error("  - " + p);
  console.error("\nこのままpushすると、デプロイが失敗するか、本番でだけ動かなくなる。");
  process.exit(1);
}
console.log("OK: wrangler.toml と _headers も問題なし");
