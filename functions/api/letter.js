// POST /api/letter  {job: {id, title, company, location, description, url}, force?: bool}
// -> {subject, cover_letter, cv_highlights}. Results are cached in KV per job id.
import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import { z } from "zod";
import { LETTER_EFFORT, LETTER_INSTRUCTIONS, MODEL, PROFILE } from "../../lib/profile.js";

const Application = z.object({
  subject: z.string(),
  cover_letter: z.string(),
  cv_highlights: z.array(z.string()),
});

function jobBlock(job) {
  return [
    `<job id="${job.id}">`,
    `Title: ${job.title || ""}`,
    `Company: ${job.company || ""}`,
    `Location: ${job.location || ""}`,
    `Description:\n${String(job.description || "(no description available)").slice(0, 8000)}`,
    `</job>`,
  ].join("\n");
}

export async function onRequestPost({ request, env }) {
  if (!env.ANTHROPIC_API_KEY) {
    return Response.json({ error: "ANTHROPIC_API_KEY is not configured on the server" }, { status: 503 });
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "invalid json" }, { status: 400 });
  }
  const job = body?.job;
  if (!job?.id || !job?.title) return Response.json({ error: "job.id and job.title are required" }, { status: 400 });

  const cacheKey = `letter:${job.id}`;
  if (!body.force) {
    const cached = await env.RADAR_KV.get(cacheKey, "json");
    if (cached) return Response.json({ ...cached, cached: true });
  }

  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY });
  let response;
  try {
    response = await client.messages.parse({
      model: env.LETTER_MODEL || MODEL,
      max_tokens: 16000,
      system: [{ type: "text", text: `${LETTER_INSTRUCTIONS}\n\n${PROFILE}`, cache_control: { type: "ephemeral" } }],
      messages: [{ role: "user", content: `Write the application for this job:\n\n${jobBlock(job)}` }],
      output_config: { effort: LETTER_EFFORT, format: zodOutputFormat(Application) },
    });
  } catch (err) {
    if (err instanceof Anthropic.RateLimitError) {
      return Response.json({ error: "Claude API is rate limited, try again in a minute" }, { status: 429 });
    }
    if (err instanceof Anthropic.APIError) {
      return Response.json({ error: `Claude API error ${err.status ?? ""}: ${err.message}` }, { status: 502 });
    }
    throw err;
  }
  if (response.stop_reason === "refusal") {
    return Response.json({ error: "Claude declined to write this letter" }, { status: 422 });
  }
  const app = response.parsed_output;
  if (!app) return Response.json({ error: "could not parse Claude's answer" }, { status: 502 });

  const result = {
    subject: app.subject,
    cover_letter: app.cover_letter,
    cv_highlights: app.cv_highlights.slice(0, 5),
    created: new Date().toISOString(),
  };
  await env.RADAR_KV.put(cacheKey, JSON.stringify(result), { expirationTtl: 60 * 60 * 24 * 120 });
  return Response.json(result);
}
