#!/usr/bin/env node
/**
 * data/regions.json + data/spots.json -> public/spots.js を作り直す。
 *
 *   node scripts/build-spots.mjs           作り直す
 *   node scripts/build-spots.mjs --check   作り直さずに、中身の妥当性と
 *                                          spots.js が最新かどうかだけ見る（CI用）
 *
 * ここで弾いているのは、デプロイしてから気づくと面倒なものだけ。
 * IDの重複、緯度経度の抜け、所属地域の間違い（起点から離れすぎ）、
 * index.html に色の定義がないカテゴリ、同じ座標に2件（ピンが重なってタップできない）。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(root, "data", "spots.json");
const REGION_SRC = join(root, "data", "regions.json");
const OUT = join(root, "public", "spots.js");
const HTML = join(root, "public", "index.html");

const RAIN = ["◎", "○", "△", "×"];
/** 起点から日帰りで動く範囲。これを超える場合はたいてい region の付け間違い */
const MAX_KM = 250;

/** 緯度経度のざっくり距離(km)。地域の取り違えが分かれば十分なので簡易式で足りる */
function distKm(lat, lng, c) {
  const dx = (lng - c.lng) * Math.cos((lat * Math.PI) / 180) * 111.32;
  const dy = (lat - c.lat) * 111.32;
  return Math.hypot(dx, dy);
}

const check = process.argv.includes("--check");
const problems = [];
const fail = (m) => problems.push(m);

const spots = JSON.parse(readFileSync(SRC, "utf8"));
if (!Array.isArray(spots)) {
  console.error("data/spots.json は配列であること");
  process.exit(1);
}
const regions = JSON.parse(readFileSync(REGION_SRC, "utf8"));
if (!Array.isArray(regions) || !regions.length) {
  console.error("data/regions.json は1件以上の配列であること");
  process.exit(1);
}

/** 地域そのものの検査。中心がずれると所要時間も距離の輪も全部ずれる */
const byRegion = new Map();
for (const r of regions) {
  const at = r.id || r.name || "(idなし)";
  if (!r.id) fail(`${at}: id がない`);
  else if (byRegion.has(r.id)) fail(`${r.id}: id が重複している`);
  else byRegion.set(r.id, r);
  if (!r.name) fail(`${at}: name がない`);
  const c = r.center;
  if (!c || typeof c.lat !== "number" || typeof c.lng !== "number") {
    fail(`${at}: center の lat/lng が数値でない。ここが起点になる`);
  } else if (!c.name) {
    fail(`${at}: center.name がない（「◯◯からの距離の輪」に出す名前）`);
  }
  if (!Array.isArray(r.rings) || !r.rings.length || r.rings.some((n) => typeof n !== "number" || n <= 0)) {
    fail(`${at}: rings は正の数の配列であること`);
  } else if (r.rings.some((n, i) => i && n <= r.rings[i - 1])) {
    fail(`${at}: rings は小さい順に並べること`);
  }
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
  if (!s.region) fail(`${at}: region がない。どの地域のスポットか決めること`);
  else if (!byRegion.has(s.region)) fail(`${at}: region「${s.region}」が data/regions.json にない`);
  if (!s.cat) fail(`${at}: cat がない`);
  else if (cats && !cats.has(s.cat)) fail(`${at}: カテゴリ「${s.cat}」は index.html の COLORS にない`);

  if (typeof s.lat !== "number" || typeof s.lng !== "number") {
    fail(`${at}: lat/lng が数値でない`);
  } else {
    const r = byRegion.get(s.region);
    if (r && r.center) {
      const d = distKm(s.lat, s.lng, r.center);
      if (d > MAX_KM) {
        fail(`${at}: ${r.name}の起点から ${Math.round(d)}km。region の付け間違いか座標の誤り`);
      }
    }
    const key = `${s.lat},${s.lng}`;
    if (seenPos.has(key)) fail(`${at}: ${seenPos.get(key)} と座標が同じ。50mほどずらすこと`);
    else seenPos.set(key, at);
  }

  if (s.rain && !RAIN.includes(s.rain)) fail(`${at}: rain は ${RAIN.join("/")} のどれか（今: ${s.rain}）`);

  /* おすすめの月。season が台帳の原文、months が絞り込み用に読み取った月 */
  if (s.months !== undefined) {
    if (!Array.isArray(s.months) || !s.months.length) {
      fail(`${at}: months は1件以上の配列にするか、キーごと省くこと`);
    } else if (s.months.some((m) => !Number.isInteger(m) || m < 1 || m > 12)) {
      fail(`${at}: months は 1〜12 の整数（今: ${JSON.stringify(s.months)}）`);
    } else if (new Set(s.months).size !== s.months.length) {
      fail(`${at}: months に同じ月が2回入っている`);
    }
    if (!s.season) fail(`${at}: months があるのに season（台帳の原文）がない`);
  }
  if (s.season && typeof s.season !== "string") fail(`${at}: season は文字列で`);
  for (const k of ["t1", "t2", "c1", "c2"]) {
    if (s[k] != null && typeof s[k] !== "number") fail(`${at}: ${k} は数値で`);
  }
  if (s.t1 != null && s.t2 != null && s.t1 > s.t2) fail(`${at}: t1 が t2 より大きい`);
  if (s.c1 != null && s.c2 != null && s.c1 > s.c2) fail(`${at}: c1 が c2 より大きい`);
}

const js =
  `window.__REGIONS__=${JSON.stringify(regions)};\n` + `window.__SPOTS__=${JSON.stringify(spots)};\n`;

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
  console.log(`OK: ${regions.length} 地域 / スポット ${spots.length} 件、spots.js も最新`);
} else {
  writeFileSync(OUT, js);
  const per = regions.map((r) => `${r.name} ${spots.filter((s) => s.region === r.id).length}`).join(" / ");
  console.log(`public/spots.js を書き出した（スポット ${spots.length} 件: ${per}）`);
}
