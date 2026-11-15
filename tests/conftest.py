from pathlib import Path

import pytest

CAPTURES = Path(__file__).parents[1] / "examples/contexttrack/prometheus"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--perf",
        action="store_true",
        help="run the randomized query timing tests",
    )


@pytest.fixture
def normalized_scrape_capture() -> Path:
    return CAPTURES / "TestTargetScraperScrapeOK/normalized.jsonl"


@pytest.fixture
def raw_scrape_capture() -> Path:
    return CAPTURES / "TestTargetScraperScrapeOK/raw.jsonl"
