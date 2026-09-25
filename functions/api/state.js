// GET  /api/state  -> current tracker state
// PUT  /api/state  -> merge the client's state into the stored one, return the result
import { EMPTY, mergeState, validState } from "../../site/js/merge.js";

const KEY = "state";

async function load(env) {
  return (await env.RADAR_KV.get(KEY, "json")) || EMPTY();
}

export async function onRequestGet({ env }) {
  return Response.json(await load(env), { headers: { "cache-control": "no-store" } });
}

export async function onRequestPut({ request, env }) {
  const len = Number(request.headers.get("content-length") || 0);
  if (len > 2_000_000) return Response.json({ error: "too large" }, { status: 413 });
  let incoming;
  try {
    incoming = await request.json();
  } catch {
    return Response.json({ error: "invalid json" }, { status: 400 });
  }
  if (!validState(incoming)) return Response.json({ error: "invalid state" }, { status: 400 });
  const merged = mergeState(await load(env), incoming);
  await env.RADAR_KV.put(KEY, JSON.stringify(merged));
  return Response.json(merged, { headers: { "cache-control": "no-store" } });
}
