"""Persistent state in data/: every job ever seen (for dedupe) and run history."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Job


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs_path = self.root / "jobs.json"
        self.runs_path = self.root / "runs.json"
        self.seen_path = self.root / "seen_keys.json"  # ids/keys of filtered-out or expired jobs
        self.jobs: dict[str, Job] = {}
        self.dedupe: set[str] = set()
        if self.jobs_path.exists():
            for d in json.loads(self.jobs_path.read_text(encoding="utf-8")):
                j = Job.from_dict(d)
                self.jobs[j.id] = j
                self.dedupe.add(j.dedupe_key)
        self.runs: list[dict] = json.loads(self.runs_path.read_text(encoding="utf-8")) if self.runs_path.exists() else []
        self.load_seen_keys()

    def is_new(self, job: Job) -> bool:
        return job.id not in self.jobs and job.id not in self.dedupe and job.dedupe_key not in self.dedupe

    def add(self, job: Job) -> None:
        self.jobs[job.id] = job
        self.dedupe.add(job.dedupe_key)

    def prune(self, keep_days: int) -> None:
        """Drop old jobs from the site list; their ids/keys stay in the dedupe set."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).isoformat()
        for k in [k for k, j in self.jobs.items() if j.first_seen and j.first_seen < cutoff]:
            self.dedupe.add(k)
            del self.jobs[k]

    def load_seen_keys(self) -> None:
        if self.seen_path.exists():
            self.dedupe.update(json.loads(self.seen_path.read_text()))

    def save(self) -> None:
        data = sorted((j.to_dict() for j in self.jobs.values()), key=lambda d: d["first_seen"], reverse=True)
        self.jobs_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        self.runs_path.write_text(json.dumps(self.runs[-90:], ensure_ascii=False, indent=1), encoding="utf-8")
        live = {j.dedupe_key for j in self.jobs.values()} | set(self.jobs)
        self.seen_path.write_text(json.dumps(sorted(k for k in self.dedupe if k not in live)))
