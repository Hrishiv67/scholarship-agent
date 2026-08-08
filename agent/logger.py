import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "data" / "run_logs"


@dataclass
class RunResult:
    opportunity_id: str
    title: str
    url: str
    tier: str
    outcome: str  # submitted | essay_saved | semi_queued | skipped | failed
    application_type: str = ""
    award_value: str = ""
    deadline: str = ""
    error: str = ""
    notes: str = ""

    @property
    def id(self):
        return self.opportunity_id


@dataclass
class RunLog:
    started_at: str = ""
    completed_at: str = ""
    queries_run: int = 0
    raw_results: int = 0
    after_dedup: int = 0
    classified: dict = field(default_factory=lambda: {
        "auto_apply": 0, "semi_apply": 0, "essay_pending": 0, "skip": 0
    })
    outcomes: dict = field(default_factory=lambda: {
        "submitted": 0, "essay_saved": 0, "semi_queued": 0, "skipped": 0, "failed": 0
    })
    results: list[RunResult] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def start(self):
        self.started_at = datetime.now(timezone.utc).isoformat()

    def finish(self):
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def add_result(self, result: RunResult):
        self.results.append(result)
        if result.outcome in self.outcomes:
            self.outcomes[result.outcome] += 1

    def add_error(self, opp_id: str, error: str):
        self.errors.append({"opportunity_id": opp_id, "error": error})

    def save(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = self.started_at.replace(":", "-").replace(".", "-")[:19]
        path = LOG_DIR / f"{ts}.json"
        data = {
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "queries_run": self.queries_run,
            "raw_results": self.raw_results,
            "after_dedup": self.after_dedup,
            "classified": self.classified,
            "outcomes": self.outcomes,
            "results": [vars(r) for r in self.results],
            "errors": self.errors,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[logger] Run log saved to {path}")
