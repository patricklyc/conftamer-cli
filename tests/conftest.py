from pathlib import Path

import pytest
from contexttrack import normalize_file


@pytest.fixture
def normalized_scrape_capture(tmp_path) -> Path:
    source = (
        Path(__file__).parents[1] / "examples/contexttrack/prometheus/scrape-ok.jsonl"
    )
    output = tmp_path / "scrape.v1.jsonl"
    normalize_file(source, output)
    return output
