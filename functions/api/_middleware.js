// Every /api/* request must carry the shared password (x-radar-token == env.RADAR_TOKEN).
// Cloudflare Access in front of the site is recommended as well, but this check alone
// already stops strangers from reading the tracker or spending Claude credits.

function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function onRequest(context) {
  const { request, env } = context;
  if (!env.RADAR_TOKEN) {
    return Response.json({ error: "RADAR_TOKEN is not configured on the server" }, { status: 503 });
  }
  if (!safeEqual(request.headers.get("x-radar-token") || "", env.RADAR_TOKEN)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  return context.next();
}
