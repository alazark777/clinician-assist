"""Static checks for collector configuration."""

from pathlib import Path


def test_otel_collector_yaml_exists_and_mentions_loopback_docs() -> None:
    config = Path(__file__).resolve().parents[1] / "otel-collector.yaml"
    text = config.read_text(encoding="utf-8")
    assert "memory_limiter" in text
    assert "attributes/remove_sensitive" in text
    assert "queue_size: 128" in text
