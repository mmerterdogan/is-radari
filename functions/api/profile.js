// GET /api/profile -> CV + letter instructions (for building a claude.ai prompt when no API key is set)
// and whether the server can write letters itself. Protected by the RADAR_TOKEN middleware,
// so the CV is never public.
import { LETTER_INSTRUCTIONS, PROFILE } from "../../lib/profile.js";

export async function onRequestGet({ env }) {
  return Response.json(
    { profile: PROFILE, instructions: LETTER_INSTRUCTIONS, letter_api: Boolean(env.ANTHROPIC_API_KEY) },
    { headers: { "cache-control": "no-store" } },
  );
}
