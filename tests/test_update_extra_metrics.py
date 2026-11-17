import base64
import os
import sys
import tempfile
import urllib.error
import unittest.mock as mock
import pytest

# Ensure scripts directory is in sys.path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
)

import update_extra_metrics
from update_extra_metrics import (
    safe_float,
    safe_int,
    get_auth_candidates,
    fetch_json,
    make_bar,
    format_seconds,
    format_waka_date,
    resolve_time_text,
    format_block,
    generate_language_section,
    generate_timeframe_snapshot,
    generate_productivity_ai_section,
    generate_heatmap_section,
    update_readme_section,
    main,
)


def test_safe_helpers():
    assert safe_float(12.34) == 12.34
    assert safe_float("45.67") == 45.67
    assert safe_float(None, 5.0) == 5.0
    assert safe_float("invalid", 1.0) == 1.0
    assert safe_float(float("nan"), 0.0) == 0.0
    assert safe_float(float("inf"), 0.0) == 0.0

    assert safe_int(42) == 42
    assert safe_int("100") == 100
    assert safe_int(None, 7) == 7
    assert safe_int("not_a_num", 3) == 3
    assert safe_int("3599.9") == 3600
    assert safe_int(3599.9) == 3600
    assert safe_int("3600.0") == 3600
    assert safe_int("-5.2") == -5
    assert safe_int(float("nan"), 0) == 0
    assert safe_int(float("inf"), 0) == 0


def test_make_bar_boundaries():
    # 0 percent
    assert make_bar(0.0, 24) == "░" * 24
    # Negative percent clamped to 0
    assert make_bar(-10.0, 24) == "░" * 24
    # 100 percent
    assert make_bar(100.0, 24) == "█" * 24
    # Over 100 clamped to 24
    assert make_bar(150.0, 24) == "█" * 24
    # 50 percent
    assert make_bar(50.0, 24) == ("█" * 12) + ("░" * 12)
    # Check 33.12% -> 8 filled
    assert make_bar(33.12, 24) == ("█" * 8) + ("░" * 16)
    # Custom length
    assert make_bar(50.0, 10) == "█████░░░░░"
    assert make_bar(50.0, 0) == ""
    assert make_bar(50.0, -5) == ""
    # None, nan, inf, string handling
    assert make_bar(None, 24) == "░" * 24
    assert make_bar(float("nan"), 24) == "░" * 24
    assert make_bar(float("inf"), 24) == "░" * 24
    assert make_bar("50.0", 24) == ("█" * 12) + ("░" * 12)


def test_format_block_empty():
    assert format_block([]) == ""
    assert format_block([], max_rows=5) == ""
    assert format_block(None) == ""
    assert format_block([None, "string", 123]) == ""


def test_format_block_formatting():
    items = [
        {"name": "TypeScript", "text": "25 hrs 47 mins", "percent": 33.12},
        {"name": "Other", "text": "19 hrs 44 mins", "percent": 25.37},
    ]
    res = format_block(items, max_rows=2, pad_name=18, pad_time=20)
    lines = res.split("\n")
    assert len(lines) == 2
    assert "TypeScript" in lines[0]
    assert "25 hrs 47 mins" in lines[0]
    assert "33.12 %" in lines[0]
    assert "████████░░░░░░░░░░░░░░░░" in lines[0]


def test_format_block_with_none_and_missing_keys():
    items = [
        {"name": None, "text": None, "percent": None},
        {"name": "Python", "text": "1 hr", "percent": "25.0"},
    ]
    res = format_block(items, max_rows=2)
    lines = res.split("\n")
    assert len(lines) == 2
    assert "Unknown" in lines[0]
    assert "00.00 %" in lines[0]
    assert "Python" in lines[1]
    assert "25.00 %" in lines[1]


def test_format_seconds():
    assert format_seconds(0) == "0 mins"
    assert format_seconds(-100) == "0 mins"
    assert format_seconds(None) == "0 mins"
    assert format_seconds("invalid") == "0 mins"
    assert format_seconds(60) == "1 min"
    assert format_seconds(120) == "2 mins"
    assert format_seconds(3600) == "1 hr"
    assert format_seconds(3660) == "1 hr 1 min"
    assert format_seconds(3720) == "1 hr 2 mins"
    assert format_seconds(7200) == "2 hrs"
    assert format_seconds(7260) == "2 hrs 1 min"
    assert format_seconds(204420) == "56 hrs 47 mins"


def test_format_waka_date():
    assert format_waka_date(None) == ""
    assert format_waka_date("") == ""
    # ISO formats
    assert format_waka_date("2026-11-06T14:24:39Z") == "06 November 2026"
    assert format_waka_date("2026-11-06T14:24:39+00:00") == "06 November 2026"
    assert format_waka_date("2026-11-06") == "06 November 2026"
    assert format_waka_date("2026/11/06") == "06 November 2026"
    assert format_waka_date("2024-05-10") == "10 May 2024"
    assert format_waka_date("06 Nov 2026") == "06 November 2026"
    # Unix timestamps (seconds and milliseconds)
    assert format_waka_date(1731542400) == "14 November 2024"
    assert format_waka_date("1731542400") == "14 November 2024"
    assert format_waka_date(1731542400000) == "14 November 2024"
    assert format_waka_date("1731542400000") == "14 November 2024"
    # Formatted string preserved
    assert format_waka_date("06 November 2026") == "06 November 2026"
    # Invalid date string returned as-is
    assert format_waka_date("not-a-date") == "not-a-date"


def test_resolve_time_text():
    assert resolve_time_text(None) == ""
    assert resolve_time_text("not_a_dict") == ""
    assert resolve_time_text({"text": "10 hrs"}) == "10 hrs"
    # If text is empty or None, calculate from total_seconds
    assert resolve_time_text({"text": None, "total_seconds": 3600}) == "1 hr"
    assert resolve_time_text({"text": "", "total_seconds": 7200}) == "2 hrs"
    # If text and total_seconds are None, check hours/minutes
    assert resolve_time_text({"hours": 5, "minutes": 30}) == "5 hrs 30 mins"
    assert resolve_time_text({"hours": 1}) == "1 hr"
    assert resolve_time_text({"minutes": 15}) == "15 mins"
    assert resolve_time_text({}) == ""


def test_format_block_with_total_seconds():
    items = [
        {"name": "Zed", "total_seconds": 204420, "percent": 72.96},
        {"name": "Antigravity", "total_seconds": 75780, "percent": 27.04},
    ]
    res = format_block(items, max_rows=2)
    lines = res.split("\n")
    assert len(lines) == 2
    assert "Zed" in lines[0]
    assert "56 hrs 47 mins" in lines[0]
    assert "72.96 %" in lines[0]
    assert "Antigravity" in lines[1]
    assert "21 hrs 3 mins" in lines[1]
    assert "27.04 %" in lines[1]


def test_generate_timeframe_snapshot_empty():
    assert generate_timeframe_snapshot({}) == "No activity tracked"
    assert generate_timeframe_snapshot({"data": {}}) == "No activity tracked"
    assert generate_timeframe_snapshot({"data": None}) == "No activity tracked"
    assert generate_timeframe_snapshot(None) == "No activity tracked"


def test_generate_timeframe_snapshot_full():
    stats = {
        "data": {
            "start": "2026-11-06T00:00:00Z",
            "end": "2026-11-13T23:59:59Z",
            "human_readable_total": "58 hrs 5 mins",
            "languages": [
                {"name": "TypeScript", "text": "25 hrs 47 mins", "percent": 33.12},
                {"name": "Go", "text": "8 hrs 5 mins", "percent": 10.40},
            ],
            "editors": [
                {"name": "Zed", "text": "56 hrs 47 mins", "percent": 72.96},
                {"name": "Antigravity", "text": "21 hrs 3 mins", "percent": 27.04},
            ],
            "operating_systems": [
                {"name": "WSL", "text": "48 hrs 32 mins", "percent": 62.44},
                {"name": "Linux", "text": "29 hrs 10 mins", "percent": 37.38},
            ],
            "ai_additions": 1000,
            "human_additions": 2000,
            "ai_models": [
                {"name": "GPT", "lines": 600, "percent": 60.0},
                {"name": "Gemini", "lines": 400, "percent": 40.0},
            ],
        }
    }
    output = generate_timeframe_snapshot(stats, show_ai=True)

    assert "From: 06 November 2026 - To: 13 November 2026" in output
    assert "Total Time: 58 hrs 5 mins" in output
    assert "💻 Languages:" in output
    assert "TypeScript" in output
    assert "25 hrs 47 mins" in output
    assert "33.12 %" in output
    assert "🛠️ Tools & Editors:" in output
    assert "Zed" in output
    assert "56 hrs 47 mins" in output
    assert "72.96 %" in output
    assert "🖥️ Operating Systems:" in output
    assert "WSL" in output
    assert "48 hrs 32 mins" in output
    assert "62.44 %" in output
    assert "🤖 AI Coding Metrics:" in output
    assert "AI Additions:       1,000 lines (33.33 %)" in output
    assert "Human Additions:    2,000 lines (66.67 %)" in output
    assert "Top AI Models:" in output
    assert "GPT" in output
    assert "Gemini" in output


def test_generate_timeframe_snapshot_show_ai_flag():
    stats = {
        "data": {
            "start": "2026-11-06T00:00:00Z",
            "end": "2026-11-13T23:59:59Z",
            "human_readable_total": "58 hrs 5 mins",
            "languages": [
                {"name": "TypeScript", "text": "25 hrs 47 mins", "percent": 33.12},
            ],
            "editors": [
                {"name": "Zed", "text": "56 hrs 47 mins", "percent": 100.0},
            ],
            "operating_systems": [
                {"name": "Linux", "text": "56 hrs 47 mins", "percent": 100.0},
            ],
            "ai_additions": 1000,
            "human_additions": 2000,
            "ai_models": [{"name": "GPT", "lines": 1000}],
        }
    }
    output_without_ai = generate_timeframe_snapshot(stats, show_ai=False)
    assert "💻 Languages:" in output_without_ai
    assert "🛠️ Tools & Editors:" in output_without_ai
    assert "🖥️ Operating Systems:" in output_without_ai
    assert "🤖 AI Coding Metrics:" not in output_without_ai
    assert "Top AI Models:" not in output_without_ai


def test_generate_timeframe_snapshot_no_ai_when_absent():
    stats = {
        "data": {
            "start": "2026-11-06T00:00:00Z",
            "end": "2026-11-13T23:59:59Z",
            "human_readable_total": "10 hrs",
            "languages": [
                {"name": "Python", "text": "10 hrs", "percent": 100.0},
            ],
            "editors": [
                {"name": "VS Code", "text": "10 hrs", "percent": 100.0},
            ],
            "operating_systems": [
                {"name": "Linux", "text": "10 hrs", "percent": 100.0},
            ],
            "ai_additions": 0,
            "human_additions": 0,
            "ai_models": [],
        }
    }
    output = generate_timeframe_snapshot(stats, show_ai=True)
    assert "From: 06 November 2026 - To: 13 November 2026" in output
    assert "Total Time: 10 hrs" in output
    assert "🤖 AI Coding Metrics:" not in output


def test_generate_timeframe_snapshot_missing_subsections():
    stats = {
        "data": {
            "start": None,
            "end": None,
            "human_readable_total": None,
            "total_seconds": 3600,
            "languages": [],
            "editors": None,
            "operating_systems": [],
        }
    }
    output = generate_timeframe_snapshot(stats)
    assert "From: N/A - To: N/A" in output
    assert "Total Time: 1 hr" in output
    assert "No languages tracked" in output
    assert "No tools or editors tracked" in output
    assert "No operating systems tracked" in output
    assert "🤖 AI Coding Metrics:" not in output


def test_generate_timeframe_snapshot_max_rows():
    stats = {
        "data": {
            "start": "2026-11-01",
            "end": "2026-11-07",
            "human_readable_total": "10 hrs",
            "languages": [
                {"name": f"Lang{i}", "text": f"{i} hrs", "percent": 10.0}
                for i in range(10)
            ],
            "editors": [
                {"name": f"Editor{i}", "text": f"{i} hrs", "percent": 10.0}
                for i in range(10)
            ],
            "operating_systems": [
                {"name": f"OS{i}", "text": f"{i} hrs", "percent": 10.0}
                for i in range(10)
            ],
        }
    }
    output = generate_timeframe_snapshot(stats, max_rows=3)
    assert "Lang0" in output
    assert "Lang2" in output
    assert "Lang3" not in output
    assert "Editor0" in output
    assert "Editor2" in output
    assert "Editor3" not in output
    assert "OS0" in output
    assert "OS2" in output
    assert "OS3" not in output


def test_generate_timeframe_snapshot_edge_cases():
    # Only AI additions (no AI models)
    stats_ai_only = {
        "data": {
            "start": "2026-11-01",
            "end": "2026-11-07",
            "human_readable_total": "5 hrs",
            "languages": [{"name": "Python", "text": "5 hrs", "percent": 100.0}],
            "ai_additions": 500,
            "human_additions": 500,
            "ai_models": [],
        }
    }
    out1 = generate_timeframe_snapshot(stats_ai_only)
    assert "🤖 AI Coding Metrics:" in out1
    assert "AI Additions:       500 lines (50.00 %)" in out1
    assert "Top AI Models:" not in out1

    # Only AI models (no AI additions)
    stats_models_only = {
        "data": {
            "start": "2026-11-01",
            "end": "2026-11-07",
            "human_readable_total": "5 hrs",
            "languages": [{"name": "Python", "text": "5 hrs", "percent": 100.0}],
            "ai_additions": 0,
            "human_additions": 0,
            "ai_models": [{"name": "Claude", "lines": 300}],
        }
    }
    out2 = generate_timeframe_snapshot(stats_models_only)
    assert "🤖 AI Coding Metrics:" in out2
    assert "AI Additions:       300 lines (100.00 %)" in out2
    assert "Top AI Models:" in out2
    assert "Claude" in out2

    # Range nested in dict
    stats_nested_range = {
        "data": {
            "range": {"start": "2026-11-01T00:00:00Z", "end": "2026-11-07T23:59:59Z"},
            "total_seconds_including_other_language": 7200,
            "languages": [{"name": "Go", "total_seconds": 7200, "percent": 100.0}],
            "ai_models": [{"name": "GPT-4", "percent": 100.0}],
        }
    }
    out_nested = generate_timeframe_snapshot(stats_nested_range)
    assert "From: 01 November 2026 - To: 07 November 2026" in out_nested
    assert "Total Time: 2 hrs" in out_nested
    assert "Go" in out_nested
    assert "GPT-4" in out_nested

    # Malformed / nan / negative values in items
    stats_malformed = {
        "data": {
            "start": "2026-11-01",
            "end": "2026-11-07",
            "human_readable_total": "5 hrs",
            "languages": [
                {"name": None, "text": None, "percent": float("nan")},
                {"name": "Rust", "text": "1 hr", "percent": -10.0},
            ],
            "editors": [{"name": "Zed", "text": "5 hrs", "percent": 150.0}],
        }
    }
    out3 = generate_timeframe_snapshot(stats_malformed)
    assert "Unknown" in out3
    assert "00.00 %" in out3
    assert "Rust" in out3
    assert "Zed" in out3


def test_generate_language_section():
    # Empty stats
    assert generate_language_section({}) == "No activity tracked"
    assert generate_language_section({"data": {}}) == "No activity tracked"
    assert generate_language_section({"data": {"languages": []}}) == (
        "No activity tracked"
    )
    assert generate_language_section({"data": None}) == "No activity tracked"
    assert generate_language_section(None) == "No activity tracked"

    # Valid stats with > 6 languages
    stats = {
        "data": {
            "languages": [
                {"name": f"Lang{i}", "text": f"{i} hrs", "percent": 10.0}
                for i in range(10)
            ]
        }
    }
    res = generate_language_section(stats, max_rows=6)
    lines = res.split("\n")
    assert len(lines) == 6
    assert "Lang0" in lines[0]
    assert "Lang5" in lines[5]


def test_generate_productivity_ai_section_full():
    stats_all = {
        "data": {
            "human_readable_daily_average": "2 hrs 48 mins",
            "human_readable_total": "2,449 hrs 57 mins",
            "best_day": {"date": "2026-11-07", "text": "14 hrs 28 mins"},
            "operating_systems": [
                {"name": "WSL", "percent": 62.44},
                {"name": "Linux", "percent": 37.38},
                {"name": "Windows", "percent": 0.18},
            ],
            "ai_additions": 276895,
            "human_additions": 540819,
            "ai_models": [
                {"name": "GPT", "lines": 66526},
                {"name": "OMP", "lines": 61961},
                {"name": "Gemini", "lines": 33952},
                {"name": "Spark", "lines": 24974},
                {"name": "Jev", "lines": 6951},
                {"name": "Claude", "lines": 4184},
            ],
            "projects": [{"name": "super-secret-client-repo", "percent": 50.0}],
        }
    }
    stats_week = {
        "data": {
            "human_readable_daily_average": "8 hrs 17 mins",
            "editors": [
                {"name": "Zed", "percent": 72.96},
                {"name": "Antigravity", "percent": 27.04},
            ],
            "projects": [{"name": "private-internal-tool", "percent": 80.0}],
        }
    }
    summaries = {"data": [{"grand_total": {"total_seconds": 3600}} for _ in range(7)]}

    output = generate_productivity_ai_section(stats_all, stats_week, summaries)

    assert "Consistency:        7 / 7 active days this week" in output
    assert (
        "Daily Average:      8 hrs 17 mins / day (7 Days) • 2 hrs 48 mins / day"
        " (All Time)" in output
    )
    assert "Best Day:           14 hrs 28 mins (2026-11-07)" in output
    assert "Total Coded:        2,449 hrs 57 mins" in output
    assert "Recent Editors:     Zed (72.96%), Antigravity (27.04%)" in output
    assert "Primary Platforms:  WSL (62.44%), Linux (37.38%)" in output
    assert "AI Additions:       276,895 lines (33.86 %)" in output
    assert "Human Additions:    540,819 lines (66.14 %)" in output
    assert "Top AI Models:" in output
    assert "GPT" in output
    assert "Spark" in output

    # Ensure private projects are completely hidden
    assert "super-secret" not in output
    assert "private-internal" not in output


def test_generate_productivity_ai_section_empty_and_edge_cases():
    stats_all = {}
    stats_week = {}
    summaries = {}

    output = generate_productivity_ai_section(stats_all, stats_week, summaries)
    assert "Consistency:        0 / 7 active days this week" in output
    assert "Daily Average:      N/A / day (7 Days) • N/A / day (All Time)" in output
    assert "Best Day:           N/A (N/A)" in output
    assert "Total Coded:        N/A" in output
    assert "Recent Editors:     N/A" in output
    assert "Primary Platforms:  N/A" in output
    assert "AI Additions:       0 lines (00.00 %)" in output
    assert "Human Additions:    0 lines (00.00 %)" in output
    assert "No AI model statistics recorded yet" in output


def test_generate_productivity_ai_section_with_none_values():
    stats_all = {
        "data": {
            "human_readable_daily_average": None,
            "daily_average": 7200,
            "human_readable_total": None,
            "human_readable_total_including_other_language": "50 hrs",
            "best_day": {"date": "2026-11-05", "total_seconds": 36000},
            "operating_systems": [
                {"name": "Linux", "percent": None},
                {"name": "Mac", "percent": 90.0},
            ],
            "ai_additions": None,
            "human_additions": None,
            "ai_models": [
                {"name": "GPT", "lines": None},
                {"name": "Gemini", "lines": 100},
            ],
        }
    }
    stats_week = {
        "data": {
            "human_readable_daily_average": None,
            "daily_average": 3600,
            "editors": [
                {"name": "Zed", "percent": None},
                {"name": "Neovim", "percent": 50.0},
            ],
        }
    }
    summaries = {
        "data": [
            {"range": {"date": "2026-11-14"}, "grand_total": None},
            {
                "range": None,
                "grand_total": {"text": "2 hrs", "total_seconds": 7200},
            },
        ]
    }

    output = generate_productivity_ai_section(stats_all, stats_week, summaries)
    assert "Consistency:        1 / 2 active days this week" in output
    assert "Daily Average:      1 hr / day (7 Days) • 2 hrs / day (All Time)" in output
    assert "Best Day:           10 hrs (2026-11-05)" in output
    assert "Total Coded:        50 hrs" in output
    assert "Recent Editors:     Neovim (50.00%)" in output
    assert "Primary Platforms:  Mac (90.00%)" in output
    assert "Gemini" in output


def test_generate_productivity_ai_section_14_days_consistency():
    # 14 days of summaries should only evaluate the most recent 7 days
    summaries = {"data": [{"grand_total": {"total_seconds": 3600}} for _ in range(14)]}
    output = generate_productivity_ai_section({}, {}, summaries)
    assert "Consistency:        7 / 7 active days this week" in output


def test_generate_heatmap_section():
    # Empty
    assert generate_heatmap_section({}) == "No recent activity tracked"
    assert generate_heatmap_section({"data": []}) == "No recent activity tracked"
    assert generate_heatmap_section({"data": None}) == "No recent activity tracked"
    assert (
        generate_heatmap_section({"data": [None, "invalid"]})
        == "No recent activity tracked"
    )

    # 7 days
    summaries = {
        "data": [
            {
                "range": {"date": "2026-11-08"},
                "grand_total": {"text": "14 hrs 44 mins", "total_seconds": 53040},
            },
            {
                "range": {"date": "2026-11-09"},
                "grand_total": {"text": "8 hrs 8 mins", "total_seconds": 29280},
            },
            {
                "range": {"date": "2026-11-10"},
                "grand_total": {"text": "9 hrs 25 mins", "total_seconds": 33900},
            },
            {
                "range": {"date": "2026-11-11"},
                "grand_total": {"text": "11 hrs 52 mins", "total_seconds": 42720},
            },
            {
                "range": {"date": "2026-11-12"},
                "grand_total": {"text": "6 hrs 38 mins", "total_seconds": 23880},
            },
            {
                "range": {"date": "2026-11-13"},
                "grand_total": {"text": "12 hrs 34 mins", "total_seconds": 45240},
            },
            {
                "range": {"date": "2026-11-14"},
                "grand_total": {"text": "6 hrs 42 mins", "total_seconds": 24120},
            },
        ]
    }
    output = generate_heatmap_section(summaries)
    lines = output.split("\n")
    assert len(lines) == 7
    assert "08 Nov (Sun)" in lines[0]
    assert "14 hrs 44 mins" in lines[0]
    assert "████████████████████████" in lines[0]
    assert "14 Nov (Sat)" in lines[6]

    # > 7 days (should take last 7)
    extra_summaries = {
        "data": [
            {
                "range": {"date": "2026-11-01"},
                "grand_total": {"text": "1 hr", "total_seconds": 3600},
            },
            {
                "range": {"date": "2026-11-02"},
                "grand_total": {"text": "1 hr", "total_seconds": 3600},
            },
        ]
        + summaries["data"]
    }
    out_extra = generate_heatmap_section(extra_summaries)
    assert len(out_extra.split("\n")) == 7
    assert "01 Nov" not in out_extra


def test_generate_heatmap_section_with_none_values():
    summaries = {
        "data": [
            {"range": {"date": "2026-11-13"}, "grand_total": None},
            {
                "range": None,
                "grand_total": {"text": "10 hrs", "total_seconds": 36000},
            },
            {
                "range": {"date": "2026-11-12"},
                "grand_total": {"total_seconds": 18000},
            },
        ]
    }
    output = generate_heatmap_section(summaries)
    lines = output.split("\n")
    assert len(lines) == 3
    assert "10 hrs" in lines[0]
    assert "12 Nov (Thu)" in lines[1]
    assert "5 hrs" in lines[1]
    assert "13 Nov (Fri)" in lines[2]
    assert "0 mins" in lines[2]


def test_generate_heatmap_section_unsorted_dates():
    # If API returns unsorted dates, heatmap sorts chronologically
    summaries = {
        "data": [
            {
                "range": {"date": "2026-11-14"},
                "grand_total": {"text": "2 hrs", "total_seconds": 7200},
            },
            {
                "range": {"date": "2026-11-08"},
                "grand_total": {"text": "1 hr", "total_seconds": 3600},
            },
        ]
    }
    output = generate_heatmap_section(summaries)
    lines = output.split("\n")
    assert "08 Nov (Sun)" in lines[0]
    assert "14 Nov (Sat)" in lines[1]


def test_update_readme_section():
    content = """# Header

<!--START_SECTION:testsec-->
Old content
<!--END_SECTION:testsec-->

Footer
"""
    new_content = "New updated content"
    updated = update_readme_section(content, "testsec", new_content)
    assert "Old content" not in updated
    assert "```text\nNew updated content\n```" in updated
    assert "<!--START_SECTION:testsec-->" in updated
    assert "<!--END_SECTION:testsec-->" in updated

    # Missing section
    same = update_readme_section(content, "nonexistent", "xyz")
    assert same == content


def test_end_to_end_readme_update():
    initial_readme = """# Profile

<!--START_SECTION:wakaweekly-->
<!--END_SECTION:wakaweekly-->

<!--START_SECTION:wakamonthly-->
<!--END_SECTION:wakamonthly-->

<!--START_SECTION:wakaalltime-->
<!--END_SECTION:wakaalltime-->

<!--START_SECTION:wakaproductivity-->
<!--END_SECTION:wakaproductivity-->

<!--START_SECTION:wakaheatmap-->
<!--END_SECTION:wakaheatmap-->
"""
    with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
        tf.write(initial_readme)
        tf_path = tf.name

    try:
        content = initial_readme
        content = update_readme_section(content, "wakaweekly", "weekly stats")
        content = update_readme_section(content, "wakamonthly", "monthly stats")
        content = update_readme_section(content, "wakaalltime", "all-time stats")
        content = update_readme_section(
            content, "wakaproductivity", "productivity stats"
        )
        content = update_readme_section(content, "wakaheatmap", "heatmap stats")

        assert "weekly stats" in content
        assert "monthly stats" in content
        assert "all-time stats" in content
        assert "productivity stats" in content
        assert "heatmap stats" in content
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_auth_candidates():
    # Empty
    assert get_auth_candidates("") == []
    assert get_auth_candidates(None) == []

    # Explicit Bearer / Basic
    assert get_auth_candidates("Bearer abc") == ["Bearer abc"]
    assert get_auth_candidates("Basic xyz") == ["Basic xyz"]

    # OAuth token waka_tok_
    oauth_candidates = get_auth_candidates("waka_tok_12345")
    assert oauth_candidates[0] == "Bearer waka_tok_12345"
    assert oauth_candidates[1].startswith("Basic ")

    # Standard API key
    key = "12345678-abcd-ef01-2345-6789abcdef01"
    b64_key = base64.b64encode(key.encode("utf-8")).decode("utf-8")
    candidates = get_auth_candidates(key)
    assert candidates[0] == f"Basic {b64_key}"
    assert candidates[1] == f"Bearer {key}"


def test_fetch_json_auth_fallback():
    # Test 401 on first candidate with automatic retry on second candidate
    call_count = 0

    def fake_urlopen(req, timeout=30):
        nonlocal call_count
        call_count += 1
        auth_header = req.get_header("Authorization")
        if auth_header.startswith("Basic "):
            # Simulate 401 on Basic
            fp = mock.MagicMock()
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, fp)
        # Succeed on Bearer
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = b'{"data": "success"}'
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    update_extra_metrics.AUTH_SCHEME_CACHE = None
    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
        res = fetch_json("https://wakatime.com/test", api_key="test_api_key")
        assert res == {"data": "success"}
        assert call_count == 2
        # Verify cache was updated to Bearer
        assert update_extra_metrics.AUTH_SCHEME_CACHE == "Bearer test_api_key"


def test_main_function_integration():
    sample_readme = """# Profile
<!--START_SECTION:wakaweekly-->
<!--END_SECTION:wakaweekly-->
<!--START_SECTION:wakamonthly-->
<!--END_SECTION:wakamonthly-->
<!--START_SECTION:wakaalltime-->
<!--END_SECTION:wakaalltime-->
<!--START_SECTION:wakaproductivity-->
<!--END_SECTION:wakaproductivity-->
<!--START_SECTION:wakaheatmap-->
<!--END_SECTION:wakaheatmap-->
"""
    with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
        tf.write(sample_readme)
        tf_path = tf.name

    try:
        mock_stats = {
            "data": {
                "start": "2026-11-06T00:00:00Z",
                "end": "2026-11-13T23:59:59Z",
                "languages": [{"name": "Python", "text": "10 hrs", "percent": 100.0}],
                "human_readable_daily_average": "2 hrs",
                "human_readable_total": "100 hrs",
                "editors": [{"name": "Zed", "percent": 100.0}],
                "operating_systems": [{"name": "Linux", "percent": 100.0}],
                "ai_additions": 10,
                "human_additions": 20,
                "ai_models": [{"name": "GPT", "lines": 10}],
                "best_day": {"date": "2026-11-01", "text": "5 hrs"},
            }
        }
        mock_summaries = {
            "data": [
                {
                    "range": {"date": "2026-11-14"},
                    "grand_total": {"text": "2 hrs", "total_seconds": 7200},
                }
            ]
        }

        def fake_fetch(url, api_key=None):
            if "summaries" in url:
                return mock_summaries
            return mock_stats

        with mock.patch.dict(
            os.environ,
            {"WAKATIME_API_KEY": "dummy_key", "README_PATH": tf_path},
        ):
            with mock.patch.object(
                update_extra_metrics, "fetch_json", side_effect=fake_fetch
            ):
                main()

        with open(tf_path, "r", encoding="utf-8") as f:
            updated_content = f.read()

        assert "From: 06 November 2026 - To: 13 November 2026" in updated_content
        assert "Total Time: 100 hrs" in updated_content
        assert "💻 Languages:" in updated_content
        assert "🛠️ Tools & Editors:" in updated_content
        assert "🖥️ Operating Systems:" in updated_content
        assert "Python" in updated_content
        assert "Zed (100.00%)" in updated_content
        assert "Linux (100.00%)" in updated_content
        assert "1 / 1 active days this week" in updated_content
        assert "14 Nov (Sat)" in updated_content
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)


def test_main_missing_api_key():
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


def test_main_missing_readme():
    with mock.patch.dict(
        os.environ,
        {
            "WAKATIME_API_KEY": "some_key",
            "README_PATH": "/path/that/does/not/exist.md",
        },
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


def test_main_http_error_exit():
    with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
        tf.write("# Test")
        tf_path = tf.name

    try:
        with mock.patch.dict(
            os.environ,
            {"WAKATIME_API_KEY": "some_key", "README_PATH": tf_path},
        ):
            with mock.patch.object(
                update_extra_metrics,
                "fetch_json",
                side_effect=urllib.error.HTTPError(
                    "http://url", 401, "Unauthorized", {}, None
                ),
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
    finally:
        if os.path.exists(tf_path):
            os.remove(tf_path)
