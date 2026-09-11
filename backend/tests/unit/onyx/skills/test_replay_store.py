import importlib.util
from pathlib import Path

from onyx.skills.built_in import BUILT_IN_SKILLS

_SCRIPT = (
    BUILT_IN_SKILLS["zhihuiya"].source_dir / "scripts" / "replay_store.py"
)
_SPEC = importlib.util.spec_from_file_location("zhihuiya_replay_store", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
replay_store = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(replay_store)


def test_cache_key_is_stable_and_order_independent() -> None:
    left = replay_store.cache_key("patsnap_search", {"q": "ADC", "limit": 100})
    right = replay_store.cache_key("patsnap_search", {"limit": 100, "q": "ADC"})
    assert left == right
    assert len(left) == 32


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    path = replay_store.write_capture(
        "rpt-1",
        "patent-briefing",
        {"pn": "CN123456A"},
        {"title": "example"},
        base=tmp_path,
    )
    assert path.is_file()
    loaded = replay_store.read_capture(
        "rpt-1", "patent-briefing", {"pn": "CN123456A"}, base=tmp_path
    )
    assert loaded is not None
    assert loaded["body"]["title"] == "example"
    assert loaded["truncated"] is False


def test_truncated_seed_is_tagged() -> None:
    assert replay_store.is_truncated(f"prefix {replay_store.TRUNCATED_TAG}")
    assert replay_store.is_truncated({"truncated": True})
    assert not replay_store.is_truncated({"hits": [1]})
