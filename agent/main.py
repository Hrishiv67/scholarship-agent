import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env for local development (GitHub Actions uses env vars directly)
load_dotenv(Path(__file__).parent.parent / ".env")

from . import (
    applicator,
    applications_writer,
    classifier,
    dedup,
    digest,
    logger,
    profile_loader,
    searcher,
)

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"
SEEDS_ONLY = os.environ.get("SEEDS_ONLY", "false").lower() == "true"
RAW_RESULTS_PATH = Path(__file__).parent.parent / "outputs" / "opportunities_raw.json"


def run():
    run_log = logger.RunLog()
    run_log.start()

    print(f"[main] Scholarship Agent starting — DRY_RUN={DRY_RUN} SEEDS_ONLY={SEEDS_ONLY}")

    # ── Phase 0: Load profile & dedup store ──────────────────────────────────
    try:
        profile = profile_loader.load()
        print(f"[main] Profile loaded: {profile.personal.full_name}")
    except Exception as e:
        print(f"[main] FATAL: Could not load profile.json — {e}")
        sys.exit(1)

    dedup_store = dedup.load()
    print(f"[main] Dedup store loaded: {len(dedup_store.entries)} known entries")

    # ── Phase 2: Search for new opportunities ─────────────────────────────────
    raw_results = searcher.search(dry_run=DRY_RUN)
    run_log.raw_results = len(raw_results)
    print(f"[main] Search complete: {len(raw_results)} raw results")

    # Save raw results for debugging
    RAW_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_RESULTS_PATH.write_text(
        json.dumps([vars(r) for r in raw_results], indent=2),
        encoding="utf-8"
    )

    # ── Phase 3: Classify ──────────────────────────────────────────────────────
    opportunities = classifier.classify_all(raw_results, dedup_store, dry_run=DRY_RUN, run_log=run_log)
    run_log.after_dedup = len(opportunities)
    for opp in opportunities:
        run_log.classified[opp.route] = run_log.classified.get(opp.route, 0) + 1
    print(f"[main] Classified {len(opportunities)} opportunities")

    # ── Phase 4: Apply (new finds + unfinished retries) ───────────────────────
    if not SEEDS_ONLY:
        retries = applicator.retries_from_store(dedup_store, opportunities, limit=20)
        opportunities = list(opportunities) + retries
    try:
        apply_limit = int(os.environ.get("APPLY_LIMIT", "0") or "0")
    except ValueError:
        apply_limit = 0
    if apply_limit > 0:
        opportunities = opportunities[:apply_limit]
        print(f"[main] APPLY_LIMIT={apply_limit}")
    results = []
    for opp in opportunities:
        result = applicator.dispatch(opp, profile, dedup_store, run_log, dry_run=DRY_RUN)
        run_log.add_result(result)
        results.append(result)

    # ── Phase 5: Persist data ─────────────────────────────────────────────────
    # A dry run must not persist dedup/applications, or the next real run skips them.
    if not DRY_RUN:
        dedup.save(dedup_store)
        applications_writer.update(results)
    else:
        print("[main] DRY_RUN: skipping dedup/applications persistence")
    run_log.finish()
    run_log.save()

    # ── Phase 6: Send digest ──────────────────────────────────────────────────
    digest.send(run_log, opportunities, profile, dry_run=DRY_RUN)

    # Summary
    print(f"\n[main] === Run Complete ===")
    print(f"[main]   Raw results:   {run_log.raw_results}")
    print(f"[main]   Classified:    {run_log.after_dedup}")
    print(f"[main]   Submitted:     {run_log.outcomes.get('submitted', 0)}")
    print(f"[main]   Yours (elite): {run_log.outcomes.get('yours_manual', 0)}")
    print(f"[main]   Tracked/flag:  {run_log.outcomes.get('tracked', 0)}")
    print(f"[main]   Skipped:       {run_log.outcomes.get('skipped', 0)}")
    print(f"[main]   Errors:        {len(run_log.errors)}")
    print(f"[main] ===================\n")


if __name__ == "__main__":
    run()
