"""Claude API (optional): re-evaluate the rule-based match and draft applications for the best jobs."""
from __future__ import annotations

import json
import logging
from typing import Literal

import anthropic
from pydantic import BaseModel

from .match import CATEGORY_LABEL
from .models import Job

log = logging.getLogger("radar")


class JobAssessment(BaseModel):
    job_id: str
    category: Literal["dogrudan", "uygun", "stretch", "dusuk"]
    score: int                      # 0-100 within the whole pool
    education_label: str            # e.g. "Lisans · Makine Müh.", "Lisans veya YL", "YL şartı"
    experience_label: str           # e.g. "0-2 yıl", "Yeni mezun / junior", "5+ yıl"
    work_mode: Literal["uzaktan", "hibrit", "ofiste", "belirtilmemis"]
    key_requirements: list[str]     # main technical requirements of the ad (short labels)
    matches: list[str]              # requirements the candidate meets
    gaps: list[str]                 # requirements the candidate does not show
    reasons: list[str]              # why this category (Turkish, max 4)


class BatchAssessment(BaseModel):
    assessments: list[JobAssessment]


class Application(BaseModel):
    subject: str
    cover_letter: str
    cv_highlights: list[str]


SCORING_INSTRUCTIONS = """You assess job ads for one specific candidate and answer one question:
"With his BSc in Mechanical Engineering, his ongoing thesis MSc, his technical skills, internships and
projects, can he REALISTICALLY apply to this job?" Build the widest realistic pool - do not answer
"which jobs require a master's degree".

Rules:
- Education is never a hard filter. A job asking for a Bachelor's degree in Mechanical Engineering (or an
  equivalent/related engineering degree) fits him fully. "Bachelor's or Master's" fits. A Master's that is
  "preferred" is a plus for him. "Master's required": he is still an MSc student -> stretch, unless the ad
  accepts current MSc students. A PhD requirement or a degree in an unrelated field (chemistry,
  electrical-only, computer science...) is a clear mismatch.
- Experience: new graduate, 0-1, 0-2 years, junior, entry level, graduate programmes and internships /
  working-student roles fit. 1-3 years is a stretch when the technical overlap is strong. 3-4 years is a
  stretch only with very strong overlap. 5+ years, senior, lead, manager or principal roles are low fit.
- Count internships, the Formula Student team, TEKNOFEST and the capstone/design projects as real
  hands-on experience when judging requirements.
- Do not restrict to "Mechanical Engineer" titles: design, CAE/FEA/simulation, stress, R&D, product
  development, manufacturing/production/process, test/validation/durability, automotive/vehicle, component,
  systems, CAD, additive manufacturing and general graduate engineer roles can all fit.
- Location NEVER changes the category (it is handled separately).
- An ad written in, or requiring, a language he does not speak (he speaks Turkish and English) is low fit.
- Judge only the overlap between the ad's requirements and the profile - never rank companies.

Categories:
- dogrudan (Doğrudan uygun): clear overlap, requirements realistically met.
- uygun (Uygun): reasonable application with some gaps.
- stretch (Potansiyel / Stretch): some requirements above his profile but worth applying.
- dusuk (Düşük uygunluk): clear mismatch on a core requirement.

score: 0-100 overall fit, consistent with the category. Write reasons in Turkish: concrete, short
(max 4, each under 15 words), the decisive reason first. key_requirements / matches / gaps: short labels
(tools, methods, degree, experience, languages). <rule_hints> are extracted by keyword rules - use them,
but correct them when the ad text says otherwise. Return one assessment per job with exactly the given job_id."""

LETTER_INSTRUCTIONS = """You write job applications for the candidate below.
Write in the language of the job ad (Turkish ad -> Turkish, otherwise English).
The cover letter: 180-260 words, specific to this job, no generic filler, no invented facts -
only use experience that is in the CV. Mention 2-3 concrete CV items that match the ad's
requirements. He holds a BSc in Mechanical Engineering and is doing a thesis MSc; if the role is
full-time, address availability honestly and briefly. Plain text, no placeholders except the company name.
subject: an email subject line for the application.
cv_highlights: 3-5 bullet points (in the ad's language) the candidate should emphasise or
reword in their CV for this application."""


def profile_block(cv_text: str, preferences: str) -> str:
    return "\n".join(["<cv>", cv_text, "</cv>", "<preferences>", preferences, "</preferences>"])


def _hints(job: Job) -> str:
    return json.dumps({
        "category": job.category, "education": job.education.get("label"), "experience": job.experience.get("label"),
        "work_mode": job.work_mode, "role_family": job.role_label, "matched_skills": job.matches, "missing_skills": job.gaps,
    }, ensure_ascii=False)


def _job_block(job: Job) -> str:
    facts = ", ".join(f"{k}: {v}" for k, v in job.extra.items() if k not in ("query", "query_location") and v)
    return (f"<job id=\"{job.id}\">\nTitle: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n"
            f"Source: {job.source}{' | ' + facts if facts else ''}\n"
            f"<rule_hints>{_hints(job)}</rule_hints>\n"
            f"Description:\n{(job.description or '(no description available)')[:3500]}\n</job>")


class Scorer:
    def __init__(self, cfg: dict, cv_text: str, preferences: str):
        self.cfg = cfg
        self.client = anthropic.Anthropic()
        self.model = cfg.get("model", "claude-opus-5")
        profile = profile_block(cv_text, preferences)
        # Stable prefix (instructions + CV) so repeated calls can reuse the prompt cache
        self.scoring_system = [{"type": "text", "text": f"{SCORING_INSTRUCTIONS}\n\n{profile}",
                                "cache_control": {"type": "ephemeral"}}]
        self.letter_system = [{"type": "text", "text": f"{LETTER_INSTRUCTIONS}\n\n{profile}",
                               "cache_control": {"type": "ephemeral"}}]
        self.usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "calls": 0}

    def _track(self, resp) -> None:
        u = resp.usage
        self.usage["input"] += u.input_tokens
        self.usage["output"] += u.output_tokens
        self.usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        self.usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        self.usage["calls"] += 1

    def cost_usd(self) -> float:
        pi, po = float(self.cfg.get("price_input", 5)), float(self.cfg.get("price_output", 25))
        u = self.usage
        return (u["input"] * pi + u["cache_write"] * pi * 1.25 + u["cache_read"] * pi * 0.1 + u["output"] * po) / 1e6

    def _parse(self, system, content: str, schema, effort: str):
        """One structured-output call. Returns the parsed object or None (logged)."""
        try:
            resp = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                output_config={"effort": effort},
                messages=[{"role": "user", "content": content}],
                output_format=schema,
            )
        except anthropic.AuthenticationError:
            log.error("Claude API: invalid ANTHROPIC_API_KEY")
            raise
        except anthropic.RateLimitError as exc:
            log.warning("Claude API rate limited: %s", exc.message)
            return None
        except anthropic.APIStatusError as exc:
            log.warning("Claude API error %s: %s", exc.status_code, exc.message)
            return None
        except anthropic.APIConnectionError as exc:
            log.warning("Claude API connection error: %s", exc)
            return None
        self._track(resp)
        if resp.stop_reason == "refusal":
            log.warning("Claude declined this request (refusal) - skipped")
            return None
        if resp.stop_reason == "max_tokens":
            log.warning("Claude response hit max_tokens - skipped")
            return None
        return resp.parsed_output

    def score(self, jobs: list[Job]) -> None:
        """Refine the rule-based assessment in place. Fields Claude leaves empty keep the rule values."""
        size = int(self.cfg.get("batch_size", 8))
        effort = self.cfg.get("effort", "low")
        by_id = {j.id: j for j in jobs}
        for i in range(0, len(jobs), size):
            batch = jobs[i:i + size]
            content = "Assess these jobs:\n\n" + "\n\n".join(_job_block(j) for j in batch)
            result = self._parse(self.scoring_system, content, BatchAssessment, effort)
            if result is None:
                continue
            for a in result.assessments:
                job = by_id.get(a.job_id)
                if job is None or a.category not in CATEGORY_LABEL:
                    continue
                job.category = a.category
                job.score = max(0, min(100, a.score))
                job.scored_by = "claude"
                if a.education_label:
                    job.education = {**job.education, "label": a.education_label}
                if a.experience_label:
                    job.experience = {**job.experience, "label": a.experience_label}
                if a.work_mode != "belirtilmemis" or not job.work_mode:
                    job.work_mode = a.work_mode
                if a.key_requirements:
                    have = {m.lower() for m in a.matches}
                    job.requirements = [{"label": r, "have": r.lower() in have} for r in a.key_requirements[:10]]
                if a.matches:
                    job.matches = a.matches[:8]
                if a.gaps:
                    job.gaps = a.gaps[:8]
                if a.reasons:
                    job.category_reasons = a.reasons[:4]
            log.info("Claude refined %d/%d", min(i + size, len(jobs)), len(jobs))

    def write_letter(self, job: Job) -> None:
        content = "Write the application for this job:\n\n" + _job_block(job)
        app = self._parse(self.letter_system, content, Application, self.cfg.get("letter_effort", "medium"))
        if app is not None:
            job.letter = {"subject": app.subject, "cover_letter": app.cover_letter,
                          "cv_highlights": app.cv_highlights[:5]}
