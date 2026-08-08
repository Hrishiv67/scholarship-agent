import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.dedup import DedupStore, make_key


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


if __name__ == "__main__":
    test_dedup_basic()
    test_dedup_normalize()
