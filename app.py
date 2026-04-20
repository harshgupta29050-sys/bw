"""
RTMS Breakdown Analytics Dashboard — app.py
Sheet: https://docs.google.com/spreadsheets/d/1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q/
Tab : Form Responses 1

Exact column layout (Row 1 of your sheet):
  A  Timestamp
  B  SECTION
  C  PD-1 MACHINES
  D  PD-2 MACHINES
  E  RD MACHINES
  F  FM MACHINES
  G  WET MACHINES
  H  BREAKDOWN TYPE
  I  START TIME
  J  ATTENDENT NAME
  K  REMARK
  L  END TIME
  M  DATE
  N  PRODUCTION LOSS
  O  SLIP NO.
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
from collections import defaultdict
import requests
import json

app = Flask(__name__)

# ──────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ──────────────────────────────────────────────────────────────────────
SHEET_ID   = "1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q"
SHEET_TAB  = "Form Responses 1"          # exact tab name in your file

GVIZ_URL = (
    "https://docs.google.com/spreadsheets/d/"
    f"{SHEET_ID}/gviz/tq?tqx=out:json&sheet={SHEET_TAB}"
)

# ──────────────────────────────────────────────────────────────────────
#  RAW FETCH  →  list of dicts with lowercased keys
# ──────────────────────────────────────────────────────────────────────
def fetch_sheet() -> tuple[list[dict], str | None]:
    try:
        r = requests.get(GVIZ_URL, timeout=15)
        r.raise_for_status()
        raw = r.text
        # Google wraps the JSON: /*O_o*/\ngoogle.visualization.Query.setResponse({...});
        payload = json.loads(raw[raw.index("(") + 1 : raw.rindex(")")])
        cols = [c["label"].strip().lower() for c in payload["table"]["cols"]]
        rows = []
        for row in payload["table"]["rows"]:
            if row is None:
                continue
            record: dict = {}
            for i, cell in enumerate(row["c"]):
                record[cols[i]] = (
                    cell["v"] if cell and cell.get("v") is not None else ""
                )
            rows.append(record)
        return rows, None
    except Exception as exc:
        return [], str(exc)


# ──────────────────────────────────────────────────────────────────────
#  TIME HELPERS
# ──────────────────────────────────────────────────────────────────────
_TIME_FMTS = ("%I:%M:%S %p", "%H:%M:%S", "%I:%M %p", "%H:%M")
_DATE_FMTS = ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y",
              "%m/%d/%Y %H:%M:%S", "%-m/%-d/%Y")   # Google sometimes returns m/d/YYYY


def _parse_time(val: str):
    val = str(val).strip()
    for fmt in _TIME_FMTS:
        try:
            return datetime.strptime(val, fmt).time()
        except ValueError:
            pass
    return None


def _parse_date(val: str):
    val = str(val).strip()
    # Google's gviz sometimes gives "Date(2026,2,18)" format
    if val.startswith("Date("):
        parts = val[5:-1].split(",")
        try:
            return datetime(int(parts[0]), int(parts[1]) + 1, int(parts[2]))
        except Exception:
            pass
    for fmt in _DATE_FMTS:
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            pass
    return None


def _duration_min(start_raw, end_raw) -> float:
    s = _parse_time(str(start_raw))
    e = _parse_time(str(end_raw))
    if s is None or e is None:
        return 0.0
    ds = datetime.combine(datetime.today(), s)
    de = datetime.combine(datetime.today(), e)
    if de < ds:                          # crosses midnight
        de += timedelta(days=1)
    diff = (de - ds).total_seconds() / 60
    return round(diff, 1) if 0 < diff < 600 else 0.0


# ──────────────────────────────────────────────────────────────────────
#  MACHINE RESOLVER
#  Your sheet has one "Skip" per row and ONE actual machine name.
#  We return that name, or "—" if all are Skip/empty.
# ──────────────────────────────────────────────────────────────────────
_MACHINE_COLS = (
    "pd-1 machines",
    "pd-2 machines",
    "rd machines",
    "fm machines",
    "wet machines",
)


def _machine(row: dict) -> str:
    for col in _MACHINE_COLS:
        v = str(row.get(col, "")).strip()
        if v and v.lower() != "skip":
            return v
    return "—"


# ──────────────────────────────────────────────────────────────────────
#  SECTION NORMALISER
#  Your sheet has variants like "PD -1", "PD-1", "PD -1 " etc.
# ──────────────────────────────────────────────────────────────────────
def _norm_section(raw: str) -> str:
    s = str(raw).strip()
    if not s:
        return "Unknown"
    # collapse internal spaces around hyphens: "PD -1" → "PD-1"
    import re
    s = re.sub(r"\s*-\s*", "-", s)
    return s


# ──────────────────────────────────────────────────────────────────────
#  BUILD CLEAN RECORD LIST  (one dict per row)
# ──────────────────────────────────────────────────────────────────────
def _build_records(raw_rows: list[dict]) -> list[dict]:
    records = []
    for r in raw_rows:
        # ── core fields ──────────────────────────────────────────────
        timestamp_raw = str(r.get("timestamp", "")).strip()
        section       = _norm_section(r.get("section", "Unknown"))
        btype         = str(r.get("breakdown type", "")).strip() or "Unknown"
        start_raw     = r.get("start time", "")
        end_raw       = r.get("end time", "")
        date_raw      = r.get("date", "")
        attendant     = str(r.get("attendent name", "")).strip() or "Unknown"
        remark        = str(r.get("remark", "")).strip()
        loss_raw      = str(r.get("production loss", "")).strip()
        slip          = str(r.get("slip no.", "")).strip()
        machine       = _machine(r)

        # ── derived ──────────────────────────────────────────────────
        date_obj  = _parse_date(str(date_raw))
        duration  = _duration_min(start_raw, end_raw)
        loss_bool = loss_raw.upper() in ("YES", "Y")

        # hour from start time (for heatmap / shift)
        start_time_obj = _parse_time(str(start_raw))
        hour = start_time_obj.hour if start_time_obj else None

        records.append({
            # display fields (for table)
            "Timestamp":         timestamp_raw,
            "Date":              str(date_raw).strip(),
            "Section":           section,
            "Machine":           machine,
            "Breakdown Type":    btype,
            "Start Time":        str(start_raw),
            "End Time":          str(end_raw),
            "Duration (min)":    duration,
            "Production Loss":   "YES" if loss_bool else "No",
            "Attendant":         attendant,
            "Slip No.":          slip,
            "Remark":            remark,
            # analytic fields (internal)
            "_date":             date_obj,           # datetime | None
            "_loss":             loss_bool,           # bool
            "_duration":         duration,            # float
            "_hour":             hour,                # int | None
            "_section":          section,
            "_type":             btype,
            "_machine":          machine,
            "_attendant":        attendant,
        })
    return records


# ──────────────────────────────────────────────────────────────────────
#  ANALYTICS HELPERS
# ──────────────────────────────────────────────────────────────────────
def _gcnt(lst) -> dict:
    d: dict = defaultdict(int)
    for v in lst:
        d[str(v)] += 1
    return dict(d)


def _group_dur(keys, durs) -> dict:
    d: dict = defaultdict(float)
    for k, v in zip(keys, durs):
        d[str(k)] += v
    return dict(d)


# ──────────────────────────────────────────────────────────────────────
#  AI SUGGESTIONS  (pure Python, no API call)
# ──────────────────────────────────────────────────────────────────────
def _ai_suggestions(records: list[dict]) -> list[dict]:
    if not records:
        return []

    sec_cnt   : dict = defaultdict(int)
    sec_loss  : dict = defaultdict(int)
    sec_dur   : dict = defaultdict(float)
    type_cnt  : dict = defaultdict(int)
    attn_cnt  : dict = defaultdict(int)
    attn_dur  : dict = defaultdict(float)
    mach_cnt  : dict = defaultdict(int)
    hour_cnt  : dict = defaultdict(int)
    daily     : dict = defaultdict(int)

    for r in records:
        s = r["_section"]; t = r["_type"]; a = r["_attendant"]
        m = r["_machine"]; d = r["_duration"]

        sec_cnt[s]  += 1
        sec_dur[s]  += d
        type_cnt[t] += 1
        attn_cnt[a] += 1
        attn_dur[a] += d
        if r["_machine"] != "—":
            mach_cnt[m] += 1
        if r["_loss"]:
            sec_loss[s]  += 1
        if r["_hour"] is not None:
            hour_cnt[r["_hour"]] += 1
        if r["_date"]:
            daily[r["_date"].date()] += 1

    total = len(records)
    suggestions: list[dict] = []

    # 1 · Most problematic section
    if sec_cnt:
        ts = max(sec_cnt, key=sec_cnt.get)
        pct = round(sec_cnt[ts] / total * 100, 1)
        suggestions.append({
            "type": "critical", "icon": "🔴",
            "title": f"Critical Section: {ts}",
            "body": (f"{ts} accounts for {pct}% of all breakdowns "
                     f"({sec_cnt[ts]} incidents). "
                     "Prioritise preventive maintenance here."),
            "metric": f"{sec_cnt[ts]} incidents",
        })

    # 2 · Most common failure type
    if type_cnt:
        tt = max(type_cnt, key=type_cnt.get)
        pct2 = round(type_cnt[tt] / total * 100, 1)
        suggestions.append({
            "type": "warning", "icon": "⚡",
            "title": f"Top Failure Mode: {tt}",
            "body": (f"'{tt}' is the leading failure type with "
                     f"{type_cnt[tt]} occurrences ({pct2}%). "
                     "Review root causes and schedule targeted training."),
            "metric": f"{type_cnt[tt]} cases",
        })

    # 3 · Section with highest production-loss rate
    if sec_loss:
        wl = max(sec_loss, key=sec_loss.get)
        lr = round(sec_loss[wl] / sec_cnt[wl] * 100, 1)
        suggestions.append({
            "type": "warning", "icon": "📉",
            "title": f"Production Loss Alert: {wl}",
            "body": (f"{wl} has a {lr}% production-loss rate "
                     f"({sec_loss[wl]} incidents with loss). "
                     "Deploy rapid-response protocols."),
            "metric": f"{lr}% loss rate",
        })

    # 4 · Peak breakdown hour
    if hour_cnt:
        ph = max(hour_cnt, key=hour_cnt.get)
        ampm = "AM" if ph < 12 else "PM"
        h12  = ph if 1 <= ph <= 12 else (ph - 12 if ph > 12 else 12)
        suggestions.append({
            "type": "info", "icon": "🕐",
            "title": f"Peak Hour: {h12}:00 {ampm}",
            "body": (f"Most breakdowns occur around {h12}:00 {ampm} "
                     f"({hour_cnt[ph]} incidents). "
                     "Maximise technician availability at this time."),
            "metric": f"{hour_cnt[ph]} incidents",
        })

    # 5 · High-risk machine
    if mach_cnt:
        tm = max(mach_cnt, key=mach_cnt.get)
        suggestions.append({
            "type": "info", "icon": "⚙️",
            "title": f"High-Risk Machine: {tm}",
            "body": (f"Machine '{tm}' has the highest incident count "
                     f"({mach_cnt[tm]}). Schedule immediate PM and stock spares."),
            "metric": f"{mach_cnt[tm]} breakdowns",
        })

    # 6 · Week-over-week trend
    if daily and len(daily) >= 14:
        sdays = sorted(daily.keys())
        last7 = sum(daily[d] for d in sdays[-7:])
        prev7 = sum(daily[d] for d in sdays[-14:-7])
        if prev7 > 0:
            chg = round((last7 - prev7) / prev7 * 100, 1)
            if chg > 10:
                suggestions.append({
                    "type": "critical", "icon": "📈",
                    "title": f"Rising Trend: +{chg}%",
                    "body": (f"Last 7 days: {last7} incidents vs {prev7} "
                             f"the previous week (+{chg}%). "
                             "Investigate systemic causes immediately."),
                    "metric": f"+{chg}% increase",
                })
            elif chg < -10:
                suggestions.append({
                    "type": "success", "icon": "✅",
                    "title": f"Improvement: {chg}%",
                    "body": (f"Breakdowns dropped {abs(chg)}% this week "
                             f"({last7} vs {prev7}). "
                             "Current maintenance strategy is working."),
                    "metric": f"{chg}% decrease",
                })

    # 7 · Overloaded technician
    if attn_cnt and len(attn_cnt) > 1:
        avg_load = total / len(attn_cnt)
        ta = max(attn_cnt, key=attn_cnt.get)
        if attn_cnt[ta] > avg_load * 1.5:
            suggestions.append({
                "type": "warning", "icon": "👷",
                "title": f"Overloaded Technician: {ta}",
                "body": (f"{ta} handles {attn_cnt[ta]} incidents — "
                         f"{round(attn_cnt[ta]/avg_load,1)}× the average "
                         f"({round(avg_load):.0f}). Redistribute workload."),
                "metric": f"{attn_cnt[ta]} incidents",
            })

    return suggestions[:6]


# ──────────────────────────────────────────────────────────────────────
#  TECHNICIAN LEADERBOARD
# ──────────────────────────────────────────────────────────────────────
def _leaderboard(records: list[dict]) -> list[dict]:
    data: dict = defaultdict(lambda: {
        "count": 0, "dur": 0.0, "loss": 0,
        "sections": set(), "types": set(),
    })
    for r in records:
        a = r["_attendant"]
        data[a]["count"]  += 1
        data[a]["dur"]    += r["_duration"]
        if r["_loss"]:
            data[a]["loss"] += 1
        data[a]["sections"].add(r["_section"])
        data[a]["types"].add(r["_type"])

    board = []
    for name, d in data.items():
        avg_dur   = round(d["dur"] / d["count"], 1) if d["count"] else 0.0
        loss_rate = round(d["loss"] / d["count"] * 100, 1) if d["count"] else 0.0
        eff_score = max(0.0, round(d["count"] * 10 - avg_dur * 0.5, 1))
        board.append({
            "name":             name,
            "incidents":        d["count"],
            "total_dur":        round(d["dur"], 1),
            "avg_duration":     avg_dur,
            "loss_count":       d["loss"],
            "loss_rate":        loss_rate,
            "sections_count":   len(d["sections"]),
            "types_count":      len(d["types"]),
            "efficiency_score": eff_score,
        })
    board.sort(key=lambda x: -x["incidents"])
    return board


# ──────────────────────────────────────────────────────────────────────
#  SECTION DRILL-DOWN
# ──────────────────────────────────────────────────────────────────────
def _drilldown(records: list[dict]) -> dict:
    sec_map: dict = defaultdict(lambda: {
        "count": 0, "dur": 0.0, "loss": 0,
        "machines": defaultdict(int),
        "types":    defaultdict(int),
        "attns":    defaultdict(int),
        "daily":    defaultdict(int),
    })
    for r in records:
        s = r["_section"]
        sec_map[s]["count"] += 1
        sec_map[s]["dur"]   += r["_duration"]
        if r["_loss"]:
            sec_map[s]["loss"] += 1
        sec_map[s]["machines"][r["_machine"]] += 1
        sec_map[s]["types"][r["_type"]]       += 1
        sec_map[s]["attns"][r["_attendant"]]  += 1
        if r["_date"]:
            sec_map[s]["daily"][r["_date"].strftime("%Y-%m-%d")] += 1

    result = {}
    for sec, d in sec_map.items():
        top_m = sorted(d["machines"].items(), key=lambda x: -x[1])[:6]
        top_t = sorted(d["types"].items(),    key=lambda x: -x[1])[:6]
        top_a = sorted(d["attns"].items(),    key=lambda x: -x[1])[:6]
        trend = [{"date": k, "count": v} for k, v in sorted(d["daily"].items())]
        result[sec] = {
            "count":    d["count"],
            "dur_hrs":  round(d["dur"] / 60, 1),
            "loss":     d["loss"],
            "loss_pct": round(d["loss"] / d["count"] * 100, 1) if d["count"] else 0,
            "top_machines":   [{"name": k, "count": v} for k, v in top_m],
            "top_types":      [{"name": k, "count": v} for k, v in top_t],
            "top_attendants": [{"name": k, "count": v} for k, v in top_a],
            "trend":          trend,
        }
    return result


# ──────────────────────────────────────────────────────────────────────
#  FLASK ROUTES
# ──────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dashboard")
def api_dashboard():
    # 1 · Fetch & parse
    raw_rows, err = fetch_sheet()
    if err:
        return jsonify({"error": err}), 500

    records = _build_records(raw_rows)

    # 2 · Optional date-range filter  (?from=YYYY-MM-DD&to=YYYY-MM-DD)
    date_from = request.args.get("from", "").strip()
    date_to   = request.args.get("to",   "").strip()
    if date_from:
        try:
            df = datetime.strptime(date_from, "%Y-%m-%d")
            records = [r for r in records if r["_date"] and r["_date"] >= df]
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, "%Y-%m-%d")
            records = [r for r in records if r["_date"] and r["_date"] <= dt]
        except ValueError:
            pass

    # 3 · KPIs
    total     = len(records)
    tot_dur   = sum(r["_duration"] for r in records)
    yes_loss  = sum(1 for r in records if r["_loss"])
    avg_dur   = round(tot_dur / total, 1) if total else 0.0
    loss_pct  = round(yes_loss / total * 100, 1) if total else 0.0

    # 4 · Group by dimensions
    sections  = [r["_section"]   for r in records]
    types     = [r["_type"]      for r in records]
    machines  = [r["_machine"]   for r in records]
    attns     = [r["_attendant"] for r in records]
    durations = [r["_duration"]  for r in records]

    sec_cnt  = _gcnt(sections)
    type_cnt = _gcnt(types)
    mach_cnt = _gcnt(machines)
    attn_cnt = _gcnt(attns)
    loss_cnt = _gcnt(["With Loss" if r["_loss"] else "No Loss" for r in records])

    sec_dur  = _group_dur(sections,  durations)   # {section: total_min}

    # 5 · Trends
    daily_map  : dict = defaultdict(int)
    weekly_map : dict = defaultdict(int)
    monthly_map: dict = defaultdict(int)
    for r in records:
        if r["_date"]:
            daily_map [r["_date"].strftime("%Y-%m-%d")] += 1
            weekly_map[r["_date"].strftime("%Y-W%W")]   += 1
            monthly_map[r["_date"].strftime("%Y-%m")]   += 1

    trend_daily   = [{"date": k, "count": v} for k, v in sorted(daily_map.items())]
    trend_weekly  = [{"date": k, "count": v} for k, v in sorted(weekly_map.items())]
    trend_monthly = [{"date": k, "count": v} for k, v in sorted(monthly_map.items())]

    # 6 · Hour distribution  (0–23)
    hour_dist: list[int] = [0] * 24
    for r in records:
        if r["_hour"] is not None:
            hour_dist[r["_hour"]] += 1

    # 7 · Top-N sorted lists
    top_mach = sorted(mach_cnt.items(), key=lambda x: -x[1])[:12]
    top_type = sorted(type_cnt.items(), key=lambda x: -x[1])[:12]
    top_attn = sorted(attn_cnt.items(), key=lambda x: -x[1])[:12]

    # 8 · Table rows (strip internal _ keys, return last 500)
    TABLE_COLS = [
        "Timestamp", "Date", "Section", "Machine", "Breakdown Type",
        "Start Time", "End Time", "Duration (min)",
        "Production Loss", "Attendant", "Slip No.", "Remark",
    ]
    table_rows = [{c: r[c] for c in TABLE_COLS} for r in records[-500:]]

    return jsonify({
        # ── KPIs ────────────────────────────────────────────────────
        "kpis": {
            "total":     total,
            "total_hrs": round(tot_dur / 60, 1),
            "avg_min":   avg_dur,
            "loss_pct":  loss_pct,
            "yes_loss":  yes_loss,
        },

        # ── Charts ──────────────────────────────────────────────────
        "by_section": {
            "labels":    list(sec_cnt.keys()),
            "counts":    list(sec_cnt.values()),
            "durations": [round(sec_dur.get(k, 0) / 60, 1) for k in sec_cnt],
        },
        "by_type": {
            "labels": [x[0] for x in top_type],
            "counts": [x[1] for x in top_type],
        },
        "by_machine": {
            "labels": [x[0] for x in top_mach],
            "counts": [x[1] for x in top_mach],
        },
        "by_attendant": {
            "labels": [x[0] for x in top_attn],
            "counts": [x[1] for x in top_attn],
        },
        "by_loss": {
            "labels": list(loss_cnt.keys()),
            "counts": list(loss_cnt.values()),
        },

        # ── Trends ──────────────────────────────────────────────────
        "trend_daily":   trend_daily,
        "trend_weekly":  trend_weekly,
        "trend_monthly": trend_monthly,

        # ── Hour heatmap ─────────────────────────────────────────────
        "hour_dist": {
            "labels": [f"{h:02d}:00" for h in range(24)],
            "data":   hour_dist,
        },

        # ── Advanced ─────────────────────────────────────────────────
        "ai_suggestions": _ai_suggestions(records),
        "leaderboard":    _leaderboard(records),
        "drilldown":      _drilldown(records),

        # ── Raw table ────────────────────────────────────────────────
        "rows": table_rows,
    })


# ──────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)