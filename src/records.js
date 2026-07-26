/**
 * GET  /api/records  -> { "S001": {...}, ... }
 * POST /api/records  <- 記録オブジェクト全体を丸ごと保存
 *
 * 認証は共有トークン1つだけ。X-Token ヘッダを APP_TOKEN と突き合わせる。
 * 利用者が自分ひとりなので、これで十分としている。
 * 家族それぞれのログインが必要になったら Cloudflare Access に置き換えること。
 */

const json = (body, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });

const KEY = "records";
const MAX_BYTES = 2_000_000; // KV の上限は 25MB。事故防止のための自主制限

/** 長さの違いは隠せないが、当たっている桁数は漏らさない */
function sameToken(a, b) {
  if (typeof a !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function handleRecords(request, env) {
  if (!env.APP_TOKEN) {
    return json({ error: "APP_TOKEN が未設定です" }, 500);
  }
  if (!sameToken(request.headers.get("x-token"), env.APP_TOKEN)) {
    return json({ error: "unauthorized" }, 401);
  }
  if (!env.RECORDS) {
    return json({ error: "KV バインディング RECORDS が未設定です" }, 500);
  }

  if (request.method === "GET") {
    const raw = await env.RECORDS.get(KEY);
    return json(raw ? JSON.parse(raw) : {});
  }

  if (request.method === "POST" || request.method === "PUT") {
    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "JSON として読めません" }, 400);
    }
    if (typeof body !== "object" || body === null || Array.isArray(body)) {
      return json({ error: "オブジェクトを送ってください" }, 400);
    }

    const text = JSON.stringify(body);
    // 日本語は1文字3バイト。文字数で測ると3倍ゆるくなるのでバイト数で見る
    if (new TextEncoder().encode(text).length > MAX_BYTES) {
      return json({ error: "データが大きすぎます" }, 413);
    }

    // 上書きする前に、その日の最初の1回だけ控えを取る
    const day = new Date().toISOString().slice(0, 10);
    const backupKey = `backup:${day}`;
    if (!(await env.RECORDS.get(backupKey))) {
      const prev = await env.RECORDS.get(KEY);
      if (prev) {
        await env.RECORDS.put(backupKey, prev, {
          expirationTtl: 60 * 60 * 24 * 400, // 約13か月
        });
      }
    }

    await env.RECORDS.put(KEY, text);
    return json({ ok: true, count: Object.keys(body).length });
  }

  return new Response(JSON.stringify({ error: "method not allowed" }), {
    status: 405,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      allow: "GET, POST, PUT",
    },
  });
}
