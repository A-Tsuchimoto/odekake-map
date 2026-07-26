#!/usr/bin/env node
/**
 * data/spots.json -> public/spots.js を作り直す。
 *
 *   node scripts/build-spots.mjs           作り直す
 *   node scripts/build-spots.mjs --check   作り直さずに、中身の妥当性と
 *                                          spots.js が最新かどうかだけ見る（CI用）
 *
 * ここで弾いているのは、デプロイしてから気づくと面倒なものだけ。
 * IDの重複、緯度経度の抜け・関東圏外、index.html に色の定義がないカテゴリ、
 * 同じ座標に2件（ピンが重なってタップできなくなる）。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(root, "data", "spots.json");
const OUT = join(root, "public", "spots.js");
const HTML = join(root, "public", "index.html");

const RAIN = ["◎", "○", "△", "×"];
/** 高田駅からの現実的な行動範囲。ざっくり関東 */
const BOUNDS = { lat: [34.5, 37.2], lng: [138.2, 141.0] };

const check = process.argv.includes("--check");
const problems = [];
const fail = (m) => problems.push(m);

const spots = JSON.parse(readFileSync(SRC, "utf8"));
if (!Array.isArray(spots)) {
  console.error("data/spots.json は配列であること");
  process.exit(1);
}

/** index.html の COLORS に載っているカテゴリだけが正。載っていないと灰色ピンになる */
function knownCategories() {
  const m = readFileSync(HTML, "utf8").match(/const COLORS\s*=\s*\{([\s\S]*?)\};/);
  if (!m) return null;
  return new Set([...m[1].matchAll(/"([^"]+)"\s*:/g)].map((x) => x[1]));
}
const cats = knownCategories();
if (!cats) fail("index.html の COLORS を読めなかった。カテゴリ名の確認を飛ばした");

const seenId = new Set();
const seenPos = new Map();

for (const s of spots) {
  const at = s.id || s.name || "(名前なし)";
  if (!s.id) fail(`${at}: id がない`);
  else if (seenId.has(s.id)) fail(`${s.id}: id が重複している`);
  else seenId.add(s.id);

  if (!s.name) fail(`${at}: name がない`);
  if (!s.cat) fail(`${at}: cat がない`);
  else if (cats && !cats.has(s.cat)) fail(`${at}: カテゴリ「${s.cat}」は index.html の COLORS にない`);

  if (typeof s.lat !== "number" || typeof s.lng !== "number") {
    fail(`${at}: lat/lng が数値でない`);
  } else {
    if (s.lat < BOUNDS.lat[0] || s.lat > BOUNDS.lat[1] || s.lng < BOUNDS.lng[0] || s.lng > BOUNDS.lng[1]) {
      fail(`${at}: 座標が想定範囲外 (${s.lat}, ${s.lng})`);
    }
    const key = `${s.lat},${s.lng}`;
    if (seenPos.has(key)) fail(`${at}: ${seenPos.get(key)} と座標が同じ。50mほどずらすこと`);
    else seenPos.set(key, at);
  }

  if (s.rain && !RAIN.includes(s.rain)) fail(`${at}: rain は ${RAIN.join("/")} のどれか（今: ${s.rain}）`);
  for (const k of ["t1", "t2", "c1", "c2"]) {
    if (s[k] != null && typeof s[k] !== "number") fail(`${at}: ${k} は数値で`);
  }
  if (s.t1 != null && s.t2 != null && s.t1 > s.t2) fail(`${at}: t1 が t2 より大きい`);
  if (s.c1 != null && s.c2 != null && s.c1 > s.c2) fail(`${at}: c1 が c2 より大きい`);
}

const js = `window.__SPOTS__=${JSON.stringify(spots)};\n`;

if (problems.length) {
  console.error(`spots データに ${problems.length} 件の問題:`);
  for (const p of problems) console.error("  - " + p);
  process.exit(1);
}

if (check) {
  const current = readFileSync(OUT, "utf8");
  if (current.trim() !== js.trim()) {
    console.error("public/spots.js が data/spots.json と食い違っている。npm run build:spots を実行すること");
    process.exit(1);
  }
  console.log(`OK: スポット ${spots.length} 件、spots.js も最新`);
} else {
  writeFileSync(OUT, js);
  console.log(`public/spots.js を書き出した（スポット ${spots.length} 件）`);
}
