from pathlib import Path

import pytest

CAPTURES = Path(__file__).parents[1] / "examples/contexttrack/prometheus"


@pytest.fixture
def normalized_scrape_capture() -> Path:
    return CAPTURES / "TestTargetScraperScrapeOK/normalized.jsonl"


@pytest.fixture
def raw_scrape_capture() -> Path:
    return CAPTURES / "TestTargetScraperScrapeOK/raw.jsonl"
