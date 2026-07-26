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

for (const key of ["name", "compatibility_date", "pages_build_output_dir"]) {
  const v = valueOf(key);
  if (!v) fail(`${key} がない`);
  else if (!quoted(v.raw)) fail(`${v.line}行目: ${key} は引用符で囲むこと（今: ${v.raw}）`);
}

const outDir = valueOf("pages_build_output_dir");
if (outDir && quoted(outDir.raw)) {
  const d = outDir.raw.slice(1, -1);
  if (!existsSync(join(root, d))) fail(`pages_build_output_dir の "${d}" が無い`);
  if (!existsSync(join(root, d, "index.html"))) fail(`"${d}/index.html" が無い。公開しても何も出ない`);
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

/** functions/ がないと /api/records が404になる */
if (!existsSync(join(root, "functions", "api", "records.js"))) {
  fail("functions/api/records.js が無い。記録の保存先が消える");
}

if (problems.length) {
  console.error(`wrangler.toml に ${problems.length} 件の問題:`);
  for (const p of problems) console.error("  - " + p);
  console.error("\nこのままpushするとCloudflare側のビルドが失敗する。");
  process.exit(1);
}
console.log("OK: wrangler.toml も問題なし");
