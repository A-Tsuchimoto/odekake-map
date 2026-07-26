/**
 * Workerの入口。
 *
 * /api/records だけをここで処理し、それ以外は public/ の静的ファイルを返す。
 * 静的ファイルは Workers の静的アセット機能が受け持つので、
 * 該当するファイルがある要求はそもそもこのコードまで来ない。
 * （public/_headers もそのまま効く）
 */
import { handleRecords } from "./records.js";

const notFound = () =>
  new Response(JSON.stringify({ error: "not found" }), {
    status: 404,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/records") return handleRecords(request, env);
    if (url.pathname.startsWith("/api/")) return notFound();
    return env.ASSETS.fetch(request);
  },
};
