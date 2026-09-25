import { test } from "node:test";
import assert from "node:assert/strict";
import { EMPTY, mergeState, validState } from "../../site/js/merge.js";

test("newer update wins per entry, both sides kept", () => {
  const phone = { entries: { a: { stage: "basvuruldu", updated: "2026-09-24T10:00:00Z" } }, manual: {} };
  const pc = { entries: { a: { stage: "kaydedildi", updated: "2026-09-24T09:00:00Z" }, b: { stage: "mulakat", updated: "2026-09-20T00:00:00Z" } }, manual: {} };
  const m = mergeState(pc, phone);
  assert.equal(m.entries.a.stage, "basvuruldu");
  assert.equal(m.entries.b.stage, "mulakat");
  assert.deepEqual(mergeState(phone, pc), m);          // order independent
});

test("tombstones propagate deletions of manual jobs", () => {
  const a = { entries: {}, manual: { m1: { id: "m1", title: "X", updated: "2026-09-01T00:00:00Z" } } };
  const b = { entries: {}, manual: { m1: { id: "m1", deleted: true, updated: "2026-09-02T00:00:00Z" } } };
  assert.equal(mergeState(a, b).manual.m1.deleted, true);
});

test("validation", () => {
  assert.ok(validState(EMPTY()));
  assert.ok(!validState(null));
  assert.ok(!validState({ entries: {} }));
  assert.ok(!validState("x"));
});
