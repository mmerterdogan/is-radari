// Tracker state shared by all devices.
// state = { entries: { [jobId]: {stage, notes, applied_at, followup_at, letter, updated, deleted?} },
//           manual:  { [id]: {id, title, company, location, url, description, added, updated, deleted?} },
//           companies: { [normalized name]: {name, hidden, updated} } }   (hidden companies; optional in old backups)
// Merge rule: per item, the newer `updated` timestamp wins (tombstones use deleted: true).

export const EMPTY = () => ({ entries: {}, manual: {}, companies: {} });

function mergeMap(a = {}, b = {}) {
  const out = { ...a };
  for (const [k, v] of Object.entries(b)) {
    const cur = out[k];
    if (!cur || String(v?.updated || "") > String(cur?.updated || "")) out[k] = v;
  }
  return out;
}

export function mergeState(a, b) {
  a = a || EMPTY();
  b = b || EMPTY();
  return { entries: mergeMap(a.entries, b.entries), manual: mergeMap(a.manual, b.manual),
    companies: mergeMap(a.companies, b.companies) };
}

// Basic shape/size validation for anything written by a client.
export function validState(s) {
  if (!s || typeof s !== "object") return false;
  if (typeof s.entries !== "object" || typeof s.manual !== "object") return false;
  const n = Object.keys(s.entries).length + Object.keys(s.manual).length;
  return n <= 20000;
}
