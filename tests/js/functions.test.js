import { test } from "node:test";
import assert from "node:assert/strict";
import { onRequest as auth } from "../../functions/api/_middleware.js";
import { onRequestGet, onRequestPut } from "../../functions/api/state.js";

const kv = () => {
  const m = new Map();
  return { get: async (k, t) => (m.has(k) ? (t === "json" ? JSON.parse(m.get(k)) : m.get(k)) : null), put: async (k, v) => m.set(k, v) };
};
const req = (method, body, token) => new Request("https://x/api/state", {
  method, headers: { "content-type": "application/json", ...(token ? { "x-radar-token": token } : {}) },
  body: body === undefined ? undefined : JSON.stringify(body),
});

test("middleware rejects missing / wrong token and passes the right one", async () => {
  const env = { RADAR_TOKEN: "s3cret" };
  const next = async () => new Response("ok");
  assert.equal((await auth({ request: req("GET"), env, next })).status, 401);
  assert.equal((await auth({ request: req("GET", undefined, "nope"), env, next })).status, 401);
  assert.equal(await (await auth({ request: req("GET", undefined, "s3cret"), env, next })).text(), "ok");
  assert.equal((await auth({ request: req("GET", undefined, "x"), env: {}, next })).status, 503);
});

test("state PUT merges with stored state, GET returns it", async () => {
  const env = { RADAR_KV: kv() };
  await onRequestPut({ request: req("PUT", { entries: { a: { stage: "basvuruldu", updated: "2026-09-24T10:00:00Z" } }, manual: {} }), env });
  const r = await onRequestPut({ request: req("PUT", { entries: { a: { stage: "kaydedildi", updated: "2026-09-01T00:00:00Z" }, b: { stage: "mulakat", updated: "2026-09-24T12:00:00Z" } }, manual: {} }), env });
  const merged = await r.json();
  assert.equal(merged.entries.a.stage, "basvuruldu");
  assert.equal(merged.entries.b.stage, "mulakat");
  assert.deepEqual(await (await onRequestGet({ env })).json(), merged);
  assert.equal((await onRequestPut({ request: req("PUT", "garbage"), env })).status, 400);
});

test("profile endpoint reports whether the server can write letters", async () => {
  const { onRequestGet: profile } = await import("../../functions/api/profile.js");
  const a = await (await profile({ env: {} })).json();
  assert.equal(a.letter_api, false);
  assert.ok(a.profile.includes("<cv>") && a.instructions.length > 50);
  assert.equal((await (await profile({ env: { ANTHROPIC_API_KEY: "k" } })).json()).letter_api, true);
});
