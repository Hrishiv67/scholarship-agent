import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.dedup import DedupStore, make_key
from agent.classifier import _derive_route


def test_dedup_basic():
    store = DedupStore()
    url = "https://example.com/apply?utm_source=google"
    title = "Test Scholarship"

    assert not store.seen(url, title)
    store.mark(url, title, "submitted", "OPP-TEST-001")
    assert store.seen(url, title)

    # Same URL with different UTM params — should still be seen
    url2 = "https://example.com/apply?utm_campaign=email"
    assert store.seen(url2, title)

    # Different title — should NOT be seen
    assert not store.seen(url, "Different Scholarship")

    print("PASS: Dedup basic test passed")


def test_dedup_normalize():
    url_a = "https://WWW.Example.com/apply/"
    url_b = "https://example.com/apply"
    title = "Scholarship"
    assert make_key(url_a, title) == make_key(url_b, title)
    print("PASS: URL normalization test passed")


def test_is_done_retries_tracked():
    store = DedupStore()
    url = "https://example.com/apply"
    title = "Retry Me"
    store.mark(url, title, "tracked", "OPP-TEST-002", notes="CAPTCHA detected")
    assert store.seen(url, title)
    assert not store.is_done(url, title)
    assert len(store.pending()) == 1

    store.mark(url, title, "submitted", "OPP-TEST-002")
    assert store.is_done(url, title)
    assert store.pending() == []
    print("PASS: unfinished applications are retried until submitted")


def test_elite_is_auto_submitted():
    route, _ = _derive_route("elite", False, True)
    assert route == "auto_submit"
    route, _ = _derive_route("elite", True, True)
    assert route == "skip"
    print("PASS: elite programs are auto-submitted unless they cost money")


if __name__ == "__main__":
    test_dedup_basic()
    test_dedup_normalize()
    test_is_done_retries_tracked()
    test_elite_is_auto_submitted()
