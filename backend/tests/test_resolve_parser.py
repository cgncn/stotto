"""Tests for _parse_raw_text — both single-line and multi-line Nesine formats."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api.admin import _parse_raw_text


SINGLE_LINE = """\
1 17.04.2026 20:00 Antalyaspor-Konyaspor
2 17.04.2026 20:00 Fenerbahçe A.Ş.-Çaykur Rizespor A.Ş.
3 18.04.2026 18:45 Galatasaray-Beşiktaş A.Ş.
"""

MULTI_LINE = """\
1
17.04.2026 20:00
Antalyaspor-Konyaspor


2
17.04.2026 20:00
Fenerbahçe A.Ş.-Çaykur Rizespor A.Ş.


3
18.04.2026 18:45
Galatasaray-Beşiktaş A.Ş.
"""

EXPECTED = [
    {"seq": 1, "date": "2026-04-17", "time": "20:00", "teams_str": "Antalyaspor-Konyaspor"},
    {"seq": 2, "date": "2026-04-17", "time": "20:00", "teams_str": "Fenerbahçe A.Ş.-Çaykur Rizespor A.Ş."},
    {"seq": 3, "date": "2026-04-18", "time": "18:45", "teams_str": "Galatasaray-Beşiktaş A.Ş."},
]


def test_single_line_format():
    result = _parse_raw_text(SINGLE_LINE)
    assert result == EXPECTED


def test_multi_line_format():
    result = _parse_raw_text(MULTI_LINE)
    assert result == EXPECTED


def test_multi_line_with_tabs_between():
    """Extra blank lines between entries should be ignored."""
    text = "\n\n1\n17.04.2026 20:00\nAntalyaspor-Konyaspor\n\n\n\n"
    result = _parse_raw_text(text)
    assert len(result) == 1
    assert result[0]["seq"] == 1
    assert result[0]["date"] == "2026-04-17"
    assert result[0]["teams_str"] == "Antalyaspor-Konyaspor"


def test_empty_text_returns_empty():
    assert _parse_raw_text("") == []
    assert _parse_raw_text("   \n\n  ") == []


def test_single_line_missing_teams_skipped():
    """A malformed single-line row is skipped, valid ones returned."""
    text = "1 17.04.2026 20:00 Fenerbahçe-Galatasaray\ngarbage line here\n"
    result = _parse_raw_text(text)
    assert len(result) == 1
    assert result[0]["seq"] == 1


def test_multi_line_single_entry():
    text = "5\n20.04.2026 15:30\nReal Madrid-Barcelona\n"
    result = _parse_raw_text(text)
    assert result == [{"seq": 5, "date": "2026-04-20", "time": "15:30", "teams_str": "Real Madrid-Barcelona"}]
