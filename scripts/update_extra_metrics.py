#!/usr/bin/env python3
import base64
import datetime
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request

AUTH_SCHEME_CACHE = None


def safe_float(val, default=0.0):
    if val is None:
        return default
    try:
        f = float(val)
        return default if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return default


def safe_int(val, default=0):
    if val is None:
        return default
    try:
        if isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                return default
            return int(round(val))
        s = str(val).strip()
        if not s:
            return default
        f = float(s)
        if math.isnan(f) or math.isinf(f):
            return default
        return int(round(f))
    except (ValueError, TypeError):
        return default


def get_auth_candidates(api_key: str):
    global AUTH_SCHEME_CACHE
    api_key = (api_key or "").strip()
    if not api_key:
        return []
    if api_key.startswith("Bearer ") or api_key.startswith("Basic "):
        return [api_key]

    b64_key = base64.b64encode(api_key.encode("utf-8")).decode("utf-8")
    basic_header = f"Basic {b64_key}"
    bearer_header = f"Bearer {api_key}"

    if AUTH_SCHEME_CACHE:
        if AUTH_SCHEME_CACHE == basic_header:
            return [basic_header, bearer_header]
        else:
            return [bearer_header, basic_header]

    if api_key.startswith("waka_tok_"):
        return [bearer_header, basic_header]
    else:
        # Standard WakaTime API keys require Basic base64 auth
        return [basic_header, bearer_header]


def fetch_json(url, api_key=None):
    global AUTH_SCHEME_CACHE
    if not api_key:
        api_key = os.environ.get("WAKATIME_API_KEY", "")

    candidates = get_auth_candidates(api_key)
    if not candidates:
        headers = {"User-Agent": "masred-waka-metrics/1.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    last_err = None
    for idx, auth_val in enumerate(candidates):
        headers = {
            "Authorization": auth_val,
            "User-Agent": "masred-waka-metrics/1.0",
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                AUTH_SCHEME_CACHE = auth_val
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 401 and idx < len(candidates) - 1:
                continue
            raise
        except Exception as e:
            last_err = e
            raise
    if last_err:
        raise last_err


def make_bar(percent, length=24):
    bar_len = max(0, safe_int(length, 24))
    if bar_len == 0:
        return ""
    p = safe_float(percent, 0.0)
    filled = int(round((p / 100.0) * bar_len))
    filled = max(0, min(bar_len, filled))
    return "|" * filled + "-" * (bar_len - filled)


def format_seconds(total_seconds):
    secs = safe_int(total_seconds)
    if secs <= 0:
        return "0 mins"
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    hr_str = f"{hours:,} hr" if hours == 1 else f"{hours:,} hrs"
    min_str = f"{minutes} min" if minutes == 1 else f"{minutes} mins"
    if hours > 0 and minutes > 0:
        return f"{hr_str} {min_str}"
    elif hours > 0:
        return hr_str
    elif minutes > 0:
        return min_str
    else:
        return "0 mins"


def format_waka_date(date_val):
    if not date_val:
        return ""
    if isinstance(date_val, (datetime.date, datetime.datetime)):
        return date_val.strftime("%d %B %Y")
    if isinstance(date_val, (int, float)) and date_val > 100000000:
        try:
            dt = datetime.datetime.fromtimestamp(date_val, tz=datetime.timezone.utc)
            return dt.strftime("%d %B %Y")
        except Exception:
            pass
    val_str = str(date_val).strip()
    if not val_str:
        return ""
    if val_str.isdigit():
        try:
            ts = int(val_str)
            if len(val_str) == 13:
                ts = ts / 1000.0
            if ts > 100000000:
                dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                return dt.strftime("%d %B %Y")
        except Exception:
            pass
    try:
        val_clean = val_str.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(val_clean)
        return dt.strftime("%d %B %Y")
    except Exception:
        pass
    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d %B %Y",
        "%d %b %Y",
    ):
        try:
            dt = datetime.datetime.strptime(val_str[:11].strip(), fmt)
            return dt.strftime("%d %B %Y")
        except Exception:
            pass
    return val_str


def resolve_time_text(item):
    if not isinstance(item, dict):
        return ""
    text = item.get("text")
    if text is not None and str(text).strip() != "":
        return str(text)
    if safe_int(item.get("total_seconds")) > 0:
        return format_seconds(item.get("total_seconds"))
    if "hours" in item or "minutes" in item:
        h = safe_int(item.get("hours"))
        m = safe_int(item.get("minutes"))
        if h > 0 or m > 0:
            return format_seconds(h * 3600 + m * 60)
    return ""


def format_block(items, max_rows=6, pad_name=18, pad_time=20):
    if not isinstance(items, list):
        return ""
    slice_items = [it for it in items if isinstance(it, dict)][:max_rows]
    if not slice_items:
        return ""
    resolved_items = []
    for it in slice_items:
        name = str(it.get("name") or "Unknown")
        time_text = resolve_time_text(it)
        percent = safe_float(it.get("percent"), 0.0)
        resolved_items.append((name, time_text, percent))

    p_name = max(
        max((len(r[0]) for r in resolved_items), default=10),
        pad_name,
    )
    p_time = max(
        max((len(r[1]) for r in resolved_items), default=10),
        pad_time,
    )
    lines = []
    for name, time_text, percent in resolved_items:
        bar = make_bar(percent, length=24)
        lines.append(
            f"{name.ljust(p_name)} {time_text.ljust(p_time)} {bar}   {percent:05.2f} %"
        )
    return "\n".join(lines)


def generate_language_section(stats, max_rows=6):
    data = stats.get("data", {}) if isinstance(stats, dict) else {}
    if not isinstance(data, dict):
        return "No activity tracked"
    languages = data.get("languages", []) or []
    if not isinstance(languages, list) or not languages:
        return "No activity tracked"
    res = format_block(languages, max_rows=max_rows, pad_name=18, pad_time=20)
    return res if res else "No activity tracked"


def generate_timeframe_snapshot(stats, max_rows=6, show_ai=True):
    if not isinstance(stats, dict):
        return "No activity tracked"
    data = stats.get("data")
    if not isinstance(data, dict) or not data:
        return "No activity tracked"

    has_info = any(
        [
            data.get("languages"),
            data.get("editors"),
            data.get("operating_systems"),
            data.get("human_readable_total"),
            data.get("human_readable_total_including_other_language"),
            data.get("total_seconds"),
            data.get("total_seconds_including_other_language"),
            data.get("start"),
            data.get("ai_additions"),
            data.get("human_additions"),
            data.get("ai_models"),
            data.get("ai_model_breakdown"),
        ]
    )
    if not has_info:
        return "No activity tracked"

    start_val = data.get("start") or (
        data.get("range", {}).get("start")
        if isinstance(data.get("range"), dict)
        else None
    )
    end_val = data.get("end") or (
        data.get("range", {}).get("end")
        if isinstance(data.get("range"), dict)
        else None
    )
    start_str = format_waka_date(start_val) or "N/A"
    end_str = format_waka_date(end_val) or "N/A"

    total_sec = data.get("total_seconds") or data.get(
        "total_seconds_including_other_language"
    )
    total_time = str(
        data.get("human_readable_total")
        or data.get("human_readable_total_including_other_language")
        or (format_seconds(total_sec) if safe_int(total_sec) > 0 else "")
        or "N/A"
    ).strip()

    lines = [
        f"From: {start_str} - To: {end_str}",
        "",
        f"Total Time: {total_time}",
        "",
        "💻 Languages:",
    ]

    languages = data.get("languages") or []
    lang_block = (
        format_block(languages, max_rows=max_rows)
        if isinstance(languages, list)
        else ""
    )
    lines.append(lang_block if lang_block else "No languages tracked")
    lines.append("")

    lines.append("🛠️ Tools & Editors:")
    editors = data.get("editors") or []
    editors_block = (
        format_block(editors, max_rows=max_rows) if isinstance(editors, list) else ""
    )
    lines.append(editors_block if editors_block else "No tools or editors tracked")
    lines.append("")

    lines.append("🖥️ Operating Systems:")
    operating_systems = data.get("operating_systems") or []
    os_block = (
        format_block(operating_systems, max_rows=max_rows)
        if isinstance(operating_systems, list)
        else ""
    )
    lines.append(os_block if os_block else "No operating systems tracked")

    if show_ai:
        ai_additions = safe_int(data.get("ai_additions"))
        human_additions = safe_int(data.get("human_additions"))
        ai_models = data.get("ai_models") or data.get("ai_model_breakdown") or []
        if not isinstance(ai_models, list):
            ai_models = []

        valid_models = [
            m
            for m in ai_models
            if isinstance(m, dict)
            and (safe_int(m.get("lines")) > 0 or safe_float(m.get("percent")) > 0)
        ]
        total_ai_lines = sum(safe_int(m.get("lines")) for m in valid_models)
        if ai_additions == 0 and total_ai_lines > 0:
            ai_additions = total_ai_lines

        if ai_additions > 0 or human_additions > 0 or valid_models:
            lines.append("")
            lines.append("🤖 AI Coding Metrics:")
            total_additions = ai_additions + human_additions
            ai_percent = (
                (ai_additions / total_additions * 100.0) if total_additions > 0 else 0.0
            )
            human_percent = (
                (human_additions / total_additions * 100.0)
                if total_additions > 0
                else 0.0
            )
            lines.append(
                f"{'AI Additions:'.ljust(20)}{ai_additions:,} lines ({ai_percent:05.2f} %)"
            )
            lines.append(
                f"{'Human Additions:'.ljust(20)}{human_additions:,} lines ({human_percent:05.2f} %)"
            )

            if valid_models:
                lines.append("")
                lines.append("Top AI Models:")
                model_items = []
                for m in valid_models:
                    lines_count = safe_int(m.get("lines"))
                    if "percent" in m and m.get("percent") is not None:
                        pct = safe_float(m.get("percent"))
                    else:
                        pct = (
                            (lines_count / total_ai_lines * 100.0)
                            if total_ai_lines > 0
                            else 0.0
                        )
                    text_str = (
                        f"{lines_count:,} lines"
                        if lines_count > 0
                        else str(m.get("text") or "")
                    )
                    model_items.append(
                        {
                            "name": str(m.get("name") or "Unknown"),
                            "text": text_str,
                            "percent": pct,
                        }
                    )
                model_items.sort(key=lambda x: x["percent"], reverse=True)
                lines.append(
                    format_block(model_items, max_rows=4, pad_name=18, pad_time=20)
                )

    return "\n".join(lines).strip()


def generate_productivity_ai_section(stats_all, stats_week, summaries):
    data_all = stats_all.get("data", {}) if isinstance(stats_all, dict) else {}
    if not isinstance(data_all, dict):
        data_all = {}
    data_week = stats_week.get("data", {}) if isinstance(stats_week, dict) else {}
    if not isinstance(data_week, dict):
        data_week = {}
    summaries_data = summaries.get("data", []) if isinstance(summaries, dict) else []
    if not isinstance(summaries_data, list):
        summaries_data = []

    valid_summary_days = [d for d in summaries_data if isinstance(d, dict)]
    week_summaries = (
        valid_summary_days[-7:] if len(valid_summary_days) > 7 else valid_summary_days
    )
    total_days = len(week_summaries) if week_summaries else 7
    active_days = sum(
        1
        for d in week_summaries
        if safe_int((d.get("grand_total") or {}).get("total_seconds")) > 0
    )
    consistency_text = f"{active_days} / {total_days} active days this week"

    daily_avg_week = str(
        data_week.get("human_readable_daily_average")
        or (
            format_seconds(data_week.get("daily_average"))
            if safe_int(data_week.get("daily_average")) > 0
            else ""
        )
        or "N/A"
    ).strip()
    daily_avg_all = str(
        data_all.get("human_readable_daily_average")
        or (
            format_seconds(data_all.get("daily_average"))
            if safe_int(data_all.get("daily_average")) > 0
            else ""
        )
        or "N/A"
    ).strip()
    daily_avg_text = (
        f"{daily_avg_week} / day (7 Days) • {daily_avg_all} / day (All Time)"
    )

    best_day_info = data_all.get("best_day") or {}
    if not isinstance(best_day_info, dict):
        best_day_info = {}
    best_day_date = str(best_day_info.get("date") or "N/A")
    best_day_text = str(
        best_day_info.get("text")
        or (
            format_seconds(best_day_info.get("total_seconds"))
            if safe_int(best_day_info.get("total_seconds")) > 0
            else ""
        )
        or "N/A"
    )

    total_time = str(
        data_all.get("human_readable_total")
        or data_all.get("human_readable_total_including_other_language")
        or (
            format_seconds(data_all.get("total_seconds"))
            if safe_int(data_all.get("total_seconds")) > 0
            else ""
        )
        or "N/A"
    )

    recent_editors = data_week.get("editors") or []
    if not isinstance(recent_editors, list):
        recent_editors = []
    valid_editors = [
        e
        for e in recent_editors
        if isinstance(e, dict) and safe_float(e.get("percent")) > 0
    ]
    top_editors = sorted(
        valid_editors, key=lambda e: safe_float(e.get("percent")), reverse=True
    )[:3]
    if top_editors:
        editors_str = ", ".join(
            f"{e.get('name') or 'Unknown'} ({safe_float(e.get('percent')):.2f}%)"
            for e in top_editors
        )
    else:
        editors_str = "N/A"

    all_os = data_all.get("operating_systems") or []
    if not isinstance(all_os, list):
        all_os = []
    valid_os = [
        o for o in all_os if isinstance(o, dict) and safe_float(o.get("percent")) > 0
    ]
    top_os = [o for o in valid_os if safe_float(o.get("percent")) >= 1.0]
    if not top_os and valid_os:
        top_os = valid_os
    top_os = sorted(top_os, key=lambda o: safe_float(o.get("percent")), reverse=True)[
        :3
    ]
    if top_os:
        os_str = ", ".join(
            f"{o.get('name') or 'Unknown'} ({safe_float(o.get('percent')):.2f}%)"
            for o in top_os
        )
    else:
        os_str = "N/A"

    ai_models = data_all.get("ai_models") or data_all.get("ai_model_breakdown") or []
    if not isinstance(ai_models, list):
        ai_models = []
    total_ai_lines = sum(
        safe_int(m.get("lines")) for m in ai_models if isinstance(m, dict)
    )

    ai_additions = safe_int(data_all.get("ai_additions"))
    human_additions = safe_int(data_all.get("human_additions"))
    if ai_additions == 0 and total_ai_lines > 0:
        ai_additions = total_ai_lines

    total_additions = ai_additions + human_additions
    ai_percent = (
        (ai_additions / total_additions * 100.0) if total_additions > 0 else 0.0
    )
    human_percent = (
        (human_additions / total_additions * 100.0) if total_additions > 0 else 0.0
    )

    lines = [
        "⚡ Productivity:",
        f"{'Consistency:'.ljust(20)}{consistency_text}",
        f"{'Daily Average:'.ljust(20)}{daily_avg_text}",
        f"{'Best Day:'.ljust(20)}{best_day_text} ({best_day_date})",
        f"{'Total Coded:'.ljust(20)}{total_time}",
        "",
        "💻 Top Tools:",
        f"{'Recent Editors:'.ljust(20)}{editors_str}",
        f"{'Primary Platforms:'.ljust(20)}{os_str}",
        "",
        "🤖 AI Coding Assistance:",
        f"{'AI Additions:'.ljust(20)}{ai_additions:,} lines ({ai_percent:05.2f} %)",
        f"{'Human Additions:'.ljust(20)}{human_additions:,} lines ({human_percent:05.2f} %)",
        "",
        "Top AI Models:",
    ]

    model_items = []
    for m in ai_models:
        if not isinstance(m, dict):
            continue
        lines_count = safe_int(m.get("lines"))
        if lines_count <= 0 and safe_float(m.get("percent")) <= 0:
            continue
        if "percent" in m and m.get("percent") is not None:
            pct = safe_float(m.get("percent"))
        else:
            pct = (lines_count / total_ai_lines * 100.0) if total_ai_lines > 0 else 0.0
        text_str = (
            f"{lines_count:,} lines" if lines_count > 0 else str(m.get("text") or "")
        )
        model_items.append(
            {
                "name": str(m.get("name") or "Unknown"),
                "text": text_str,
                "percent": pct,
            }
        )
    model_items.sort(key=lambda x: x["percent"], reverse=True)

    if model_items:
        lines.append(format_block(model_items, max_rows=4, pad_name=18, pad_time=20))
    else:
        lines.append("No AI model statistics recorded yet")

    return "\n".join(lines)


def generate_heatmap_section(summaries):
    data = summaries.get("data", []) if isinstance(summaries, dict) else []
    if not isinstance(data, list) or not data:
        return "No recent activity tracked"

    valid_days = [d for d in data if isinstance(d, dict)]
    if not valid_days:
        return "No recent activity tracked"

    def get_day_date(day):
        return str((day.get("range") or {}).get("date") or day.get("date") or "")

    sorted_days = sorted(valid_days, key=get_day_date)
    recent_data = sorted_days[-7:]

    max_seconds = max(
        (
            safe_int((day.get("grand_total") or {}).get("total_seconds"))
            for day in recent_data
        ),
        default=3600,
    )
    max_bar_length = 24
    lines = []

    for day in recent_data:
        date_str = str((day.get("range") or {}).get("date") or day.get("date") or "")
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            display_date = dt.strftime("%d %b (%a)")
        except Exception:
            display_date = date_str

        gt = day.get("grand_total") or {}
        seconds = safe_int(gt.get("total_seconds"))
        text = str(
            gt.get("text") or (format_seconds(seconds) if seconds > 0 else "0 mins")
        )

        ratio = (seconds / max_seconds) if max_seconds > 0 else 0.0
        bar = make_bar(ratio * 100.0, length=max_bar_length)

        lines.append(f"{display_date.ljust(16)}{text.ljust(19)}{bar}")

    return "\n".join(lines)


def update_readme_section(readme_content, section_name, new_content):
    pattern = rf"(<!--START_SECTION:{re.escape(section_name)}-->)[\s\S]*?(<!--END_SECTION:{re.escape(section_name)}-->)"
    stripped_content = new_content.strip()
    if re.search(pattern, readme_content):
        return re.sub(
            pattern,
            lambda m: f"{m.group(1)}\n\n```text\n{stripped_content}\n```\n\n{m.group(2)}",
            readme_content,
        )
    else:
        print(
            f"Warning: Marker <!--START_SECTION:{section_name}--> not found in README.md"
        )
        return readme_content


def main():
    api_key = os.environ.get("WAKATIME_API_KEY")
    if not api_key:
        print(
            "Error: WAKATIME_API_KEY environment variable not set",
            file=sys.stderr,
        )
        sys.exit(1)

    readme_path = os.environ.get("README_PATH", "README.md")
    if not os.path.exists(readme_path):
        print(f"Error: README file not found at {readme_path}", file=sys.stderr)
        sys.exit(1)

    print("Fetching WakaTime statistics...")
    try:
        stats_week = fetch_json(
            "https://wakatime.com/api/v1/users/current/stats/last_7_days", api_key
        )
        stats_month = fetch_json(
            "https://wakatime.com/api/v1/users/current/stats/last_30_days", api_key
        )
        stats_all = fetch_json(
            "https://wakatime.com/api/v1/users/current/stats/all_time", api_key
        )

        today = datetime.date.today()
        start_date = (today - datetime.timedelta(days=6)).isoformat()
        end_date = today.isoformat()
        summaries = fetch_json(
            f"https://wakatime.com/api/v1/users/current/summaries?start={start_date}&end={end_date}",
            api_key,
        )
    except urllib.error.HTTPError as e:
        print(f"Error: WakaTime API HTTP {e.code} ({e.reason})", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(
            f"Error: Network error reaching WakaTime API ({e.reason})",
            file=sys.stderr,
        )
        sys.exit(1)

    weekly_content = generate_timeframe_snapshot(stats_week, show_ai=True)
    monthly_content = generate_timeframe_snapshot(stats_month, show_ai=True)
    alltime_content = generate_timeframe_snapshot(stats_all, show_ai=True)
    prod_ai_content = generate_productivity_ai_section(stats_all, stats_week, summaries)
    heatmap_content = generate_heatmap_section(summaries)

    with open(readme_path, "r", encoding="utf-8") as f:
        readme = f.read()

    readme = update_readme_section(readme, "wakaweekly", weekly_content)
    readme = update_readme_section(readme, "wakamonthly", monthly_content)
    readme = update_readme_section(readme, "wakaalltime", alltime_content)
    readme = update_readme_section(readme, "wakaproductivity", prod_ai_content)
    readme = update_readme_section(readme, "wakaheatmap", heatmap_content)

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)

    print("README.md updated successfully with extra metrics.")


if __name__ == "__main__":
    main()
