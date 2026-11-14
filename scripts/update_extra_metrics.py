#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import datetime
import re

API_KEY = os.environ.get("WAKATIME_API_KEY")
if not API_KEY:
    print("Error: WAKATIME_API_KEY environment variable not set", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "User-Agent": "masred-waka-metrics/1.0"
}

def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def make_bar(percent, length=24):
    filled = int(round((percent / 100.0) * length))
    filled = max(0, min(length, filled))
    return "|" * filled + "-" * (length - filled)

def format_block(items, max_rows=5, pad_name=18, pad_time=20):
    lines = []
    for item in items[:max_rows]:
        name = item.get("name", "Unknown")
        time_text = item.get("text", "")
        percent = float(item.get("percent", 0.0))
        bar = make_bar(percent)
        lines.append(f"{name.ljust(pad_name)} {time_text.ljust(pad_time)} {bar}   {percent:05.2f} %")
    return "\n".join(lines)

def generate_editors_section(stats_all, stats_week):
    lines = []
    lines.append("⚡ Recent Editors (Last 7 Days):")
    recent_editors = stats_week.get("data", {}).get("editors", [])
    if recent_editors:
        lines.append(format_block(recent_editors, max_rows=5))
    else:
        lines.append("No activity tracked")
    
    lines.append("\n💻 All-Time Editors:")
    all_editors = stats_all.get("data", {}).get("editors", [])
    if all_editors:
        lines.append(format_block(all_editors, max_rows=5))

    lines.append("\n🐧 Operating Systems (All-Time):")
    all_os = stats_all.get("data", {}).get("operating_systems", [])
    if all_os:
        lines.append(format_block(all_os, max_rows=4))
        
    return "\n".join(lines)

def generate_productivity_ai_section(stats_all, stats_week):
    data_all = stats_all.get("data", {})
    data_week = stats_week.get("data", {})
    
    daily_avg_week = data_week.get("human_readable_daily_average", "N/A")
    daily_avg_all = data_all.get("human_readable_daily_average", "N/A")
    total_time = data_all.get("human_readable_total", "N/A")
    
    best_day_info = data_all.get("best_day", {})
    best_day_date = best_day_info.get("date", "N/A")
    best_day_text = best_day_info.get("text", "N/A")
    
    ai_additions = data_all.get("ai_additions", 0)
    human_additions = data_all.get("human_additions", 0)
    total_additions = ai_additions + human_additions
    ai_percent = (ai_additions / total_additions * 100.0) if total_additions > 0 else 0.0
    human_percent = (human_additions / total_additions * 100.0) if total_additions > 0 else 0.0
    
    lines = [
        "⚡ Productivity:",
        f"Daily Average:      {daily_avg_week} / day (Last 7 Days) • {daily_avg_all} / day (All Time)",
        f"Best Day:           {best_day_text} ({best_day_date})",
        f"Total Coded:        {total_time}",
        "",
        "🤖 AI Coding Metrics (All-Time):",
        f"AI Additions:       {ai_additions:,} lines ({ai_percent:05.2f} %)",
        f"Human Additions:    {human_additions:,} lines ({human_percent:05.2f} %)",
        "",
        "Top AI Models Used:"
    ]
    
    ai_models = data_all.get("ai_models", []) or data_all.get("ai_model_breakdown", [])
    # Calculate percentages of AI lines
    total_ai_lines = sum(m.get("lines", 0) for m in ai_models)
    model_items = []
    for m in ai_models:
        if m.get("lines", 0) <= 0:
            continue
        pct = (m.get("lines", 0) / total_ai_lines * 100.0) if total_ai_lines > 0 else 0.0
        model_items.append({
            "name": m.get("name", "Unknown"),
            "text": f"{m.get('lines', 0):,} lines",
            "percent": pct
        })
    if model_items:
        lines.append(format_block(model_items, max_rows=6, pad_name=18, pad_time=18))
    else:
        lines.append("No AI model statistics recorded yet")
        
    return "\n".join(lines)

def generate_heatmap_section(summaries):
    data = summaries.get("data", [])
    if not data:
        return "No recent activity tracked"
    
    lines = ["Last 14 Days Coding Activity:"]
    # Find max seconds to scale bars
    max_seconds = max((day.get("grand_total", {}).get("total_seconds", 0) for day in data), default=3600)
    max_bar_length = 24

    for day in data:
        date_str = day.get("range", {}).get("date", "")
        # Parse day of week
        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            display_date = dt.strftime("%d %b (%a)")
        except Exception:
            display_date = date_str
            
        text = day.get("grand_total", {}).get("text", "0 mins")
        seconds = day.get("grand_total", {}).get("total_seconds", 0)
        
        # Scale bar
        ratio = seconds / max_seconds if max_seconds > 0 else 0.0
        filled = int(round(ratio * max_bar_length))
        filled = max(0, min(max_bar_length, filled))
        bar = "█" * filled + "░" * (max_bar_length - filled)
        
        lines.append(f"{display_date.ljust(15)} {text.ljust(18)} {bar}")
        
    return "\n".join(lines)

def update_readme_section(readme_content, section_name, new_content):
    pattern = rf"(<!--START_SECTION:{section_name}-->)[\s\S]*?(<!--END_SECTION:{section_name}-->)"
    replacement = rf"\1\n\n```text\n{new_content}\n```\n\n\2"
    if re.search(pattern, readme_content):
        return re.sub(pattern, replacement, readme_content)
    else:
        print(f"Warning: Marker <!--START_SECTION:{section_name}--> not found in README.md")
        return readme_content

def main():
    print("Fetching WakaTime statistics...")
    stats_all = fetch_json("https://wakatime.com/api/v1/users/current/stats/all_time")
    stats_week = fetch_json("https://wakatime.com/api/v1/users/current/stats/last_7_days")
    
    today = datetime.date.today()
    start_date = (today - datetime.timedelta(days=13)).isoformat()
    end_date = today.isoformat()
    summaries = fetch_json(f"https://wakatime.com/api/v1/users/current/summaries?start={start_date}&end={end_date}")
    
    editors_content = generate_editors_section(stats_all, stats_week)
    prod_ai_content = generate_productivity_ai_section(stats_all, stats_week)
    heatmap_content = generate_heatmap_section(summaries)
    
    readme_path = os.environ.get("README_PATH", "README.md")
    with open(readme_path, "r", encoding="utf-8") as f:
        readme = f.read()
        
    readme = update_readme_section(readme, "wakaeditors", editors_content)
    readme = update_readme_section(readme, "wakaproductivity", prod_ai_content)
    readme = update_readme_section(readme, "wakaheatmap", heatmap_content)
    
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
        
    print("README.md updated successfully with extra metrics.")

if __name__ == "__main__":
    main()
