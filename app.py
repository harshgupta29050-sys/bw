from flask import Flask, render_template, jsonify, request
import requests, json, re
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)

SHEET_ID   = "1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q"
SHEET_NAME = "Form Responses 1"
URL = ("https://docs.google.com/spreadsheets/d/1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q/edit?usp=sharing")


# ─── HELPERS ────────────────────────────────────────────────────────
def parse_time(t):
    if not t: return None
    t = str(t).strip()
    for fmt in ("%I:%M:%S %p", "%H:%M:%S", "%I:%M %p", "%H:%M"):
        try: return datetime.strptime(t, fmt).time()
        except: pass
    return None

def duration_minutes(s, e):
    st, et = parse_time(s), parse_time(e)
    if not st or not et: return 0
    ds = datetime.combine(datetime.today(), st)
    de = datetime.combine(datetime.today(), et)
    if de < ds: de += timedelta(days=1)
    d = (de - ds).total_seconds() / 60
    return round(d, 1) if 0 < d < 600 else 0

def parse_date(d):
    if not d: return None
    d = str(d).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try: return datetime.strptime(d, fmt)
        except: pass
    return None

def machine_for_row(r):
    for col in ["pd-1 machines","pd-2 machines","rd machines","fm machines","wet machines"]:
        v = str(r.get(col,"")).strip()
        if v and v.lower() not in ("skip",""):
            return v
    return "—"

def gcnt(lst):
    d = defaultdict(int)
    for v in lst: d[v] += 1
    return dict(d)

def fetch_raw():
    try:
        resp = requests.get(URL, timeout=15)
        resp.raise_for_status()
        raw = resp.text
        data = json.loads(raw[raw.index("(")+1:raw.rindex(")")])
        cols = [c["label"].strip().lower() for c in data["table"]["cols"]]
        rows = []
        for row in data["table"]["rows"]:
            if not row: continue
            record = {}
            for i, cell in enumerate(row["c"]):
                record[cols[i]] = cell["v"] if cell and cell.get("v") is not None else ""
            rows.append(record)
        return rows, None
    except Exception as ex:
        return [], str(ex)

def build_records(rows):
    """Parse all raw rows into clean records."""
    records = []
    for r in rows:
        sec   = str(r.get("section","")).strip() or "Unknown"
        btype = str(r.get("breakdown type","")).strip() or "Unknown"
        mach  = machine_for_row(r)
        loss  = str(r.get("production loss","")).strip()
        start = r.get("start time","")
        end   = r.get("end time","")
        date_raw = r.get("date","")
        dt    = parse_date(date_raw)
        attn  = str(r.get("attendent name","")).strip() or "Unknown"
        slip  = str(r.get("slip no.","")).strip()
        rem   = str(r.get("remark","")).strip()
        dur   = duration_minutes(start, end)
        loss_bool = loss.upper() in ("YES","Y")

        records.append({
            "date_str":   str(date_raw).strip(),
            "date":       dt,
            "section":    sec,
            "machine":    mach,
            "type":       btype,
            "start":      str(start),
            "end":        str(end),
            "duration":   dur,
            "loss":       loss_bool,
            "loss_str":   loss,
            "attendant":  attn,
            "slip":       slip,
            "remark":     rem,
        })
    return records


# ─── AI SUGGESTIONS ─────────────────────────────────────────────────
def generate_ai_suggestions(records):
    if not records: return []
    suggestions = []

    sec_cnt   = defaultdict(int)
    sec_loss  = defaultdict(int)
    sec_dur   = defaultdict(float)
    type_cnt  = defaultdict(int)
    attn_cnt  = defaultdict(int)
    attn_loss = defaultdict(int)
    attn_dur  = defaultdict(float)
    mach_cnt  = defaultdict(int)
    daily     = defaultdict(int)
    hour_cnt  = defaultdict(int)

    for r in records:
        sec_cnt[r["section"]] += 1
        sec_dur[r["section"]] += r["duration"]
        if r["loss"]:
            sec_loss[r["section"]] += 1
            attn_loss[r["attendant"]] += 1
        type_cnt[r["type"]] += 1
        attn_cnt[r["attendant"]] += 1
        attn_dur[r["attendant"]] += r["duration"]
        mach_cnt[r["machine"]] += 1
        if r["date"]:
            daily[r["date"].date()] += 1
        # parse hour
        for fmt in ("%I:%M:%S %p","%H:%M:%S"):
            try:
                h = datetime.strptime(str(r["start"]).strip(), fmt).hour
                hour_cnt[h] += 1
                break
            except: pass

    total = len(records)

    # 1. Most problematic section
    top_sec = max(sec_cnt, key=sec_cnt.get)
    top_sec_pct = round(sec_cnt[top_sec]/total*100,1)
    suggestions.append({
        "type":"critical","icon":"🔴",
        "title":f"Critical Section: {top_sec}",
        "body":f"{top_sec} accounts for {top_sec_pct}% of all breakdowns ({sec_cnt[top_sec]} incidents). Prioritize preventive maintenance here.",
        "metric": f"{sec_cnt[top_sec]} incidents",
    })

    # 2. Most common failure type
    top_type = max(type_cnt, key=type_cnt.get)
    suggestions.append({
        "type":"warning","icon":"⚡",
        "title":f"Most Common Fault: {top_type}",
        "body":f"'{top_type}' is the leading failure mode with {type_cnt[top_type]} occurrences ({round(type_cnt[top_type]/total*100,1)}%). Review root causes and schedule targeted training.",
        "metric": f"{type_cnt[top_type]} cases",
    })

    # 3. High-loss section
    if sec_loss:
        worst_loss_sec = max(sec_loss, key=sec_loss.get)
        loss_rate = round(sec_loss[worst_loss_sec]/sec_cnt[worst_loss_sec]*100,1)
        suggestions.append({
            "type":"warning","icon":"📉",
            "title":f"Production Loss Alert: {worst_loss_sec}",
            "body":f"{worst_loss_sec} has a {loss_rate}% production loss rate ({sec_loss[worst_loss_sec]} incidents with loss). Deploy rapid response protocols.",
            "metric": f"{loss_rate}% loss rate",
        })

    # 4. Peak hour
    if hour_cnt:
        peak_h = max(hour_cnt, key=hour_cnt.get)
        am_pm = "AM" if peak_h < 12 else "PM"
        h12 = peak_h if 1 <= peak_h <= 12 else (peak_h-12 if peak_h>12 else 12)
        suggestions.append({
            "type":"info","icon":"🕐",
            "title":f"Peak Breakdown Hour: {h12}:00 {am_pm}",
            "body":f"Most breakdowns occur around {h12}:00 {am_pm} ({hour_cnt[peak_h]} incidents). Ensure maximum technician availability and pre-shift inspections at this time.",
            "metric": f"{hour_cnt[peak_h]} incidents",
        })

    # 5. Top machine
    valid_mach = {k:v for k,v in mach_cnt.items() if k != "—"}
    if valid_mach:
        top_m = max(valid_mach, key=valid_mach.get)
        suggestions.append({
            "type":"info","icon":"⚙️",
            "title":f"High-Risk Machine: {top_m}",
            "body":f"Machine '{top_m}' has the highest incident count ({valid_mach[top_m]}). Schedule immediate preventive maintenance and consider spares stocking.",
            "metric": f"{valid_mach[top_m]} breakdowns",
        })

    # 6. Trend detection (last 7 vs previous 7 days)
    if daily:
        sorted_days = sorted(daily.keys())
        if len(sorted_days) >= 14:
            last7  = sum(daily[d] for d in sorted_days[-7:])
            prev7  = sum(daily[d] for d in sorted_days[-14:-7])
            if prev7 > 0:
                change = round((last7-prev7)/prev7*100,1)
                if change > 10:
                    suggestions.append({
                        "type":"critical","icon":"📈",
                        "title":f"Breakdown Rate Rising: +{change}%",
                        "body":f"Last 7 days saw {last7} incidents vs {prev7} the week before (+{change}%). Investigate systemic causes immediately.",
                        "metric": f"+{change}% increase",
                    })
                elif change < -10:
                    suggestions.append({
                        "type":"success","icon":"📉",
                        "title":f"Improvement Detected: {change}%",
                        "body":f"Breakdowns dropped {abs(change)}% this week ({last7} vs {prev7}). Current maintenance strategies are showing results.",
                        "metric": f"{change}% decrease",
                    })

    # 7. Attendant overload
    if attn_cnt:
        top_attn = max(attn_cnt, key=attn_cnt.get)
        avg_load = total / len(attn_cnt)
        if attn_cnt[top_attn] > avg_load * 1.5:
            suggestions.append({
                "type":"warning","icon":"👷",
                "title":f"Technician Overloaded: {top_attn}",
                "body":f"{top_attn} handles {attn_cnt[top_attn]} incidents — {round(attn_cnt[top_attn]/avg_load,1)}x the average ({round(avg_load,0):.0f}). Redistribute workload to prevent burnout and errors.",
                "metric": f"{attn_cnt[top_attn]} incidents",
            })

    return suggestions[:6]


# ─── TECHNICIAN LEADERBOARD ────────────────────────────────────────
def build_leaderboard(records):
    attn_data = defaultdict(lambda: {"count":0,"dur":0,"loss":0,"sections":set(),"types":set()})
    for r in records:
        a = r["attendant"]
        attn_data[a]["count"]  += 1
        attn_data[a]["dur"]    += r["duration"]
        if r["loss"]: attn_data[a]["loss"] += 1
        attn_data[a]["sections"].add(r["section"])
        attn_data[a]["types"].add(r["type"])

    board = []
    for name, d in attn_data.items():
        avg_dur = round(d["dur"]/d["count"],1) if d["count"] else 0
        loss_rate = round(d["loss"]/d["count"]*100,1) if d["count"] else 0
        # score: more incidents handled = higher score, lower avg duration = better
        eff_score = round(d["count"] * 10 - avg_dur * 0.5, 1)
        board.append({
            "name": name,
            "incidents": d["count"],
            "avg_duration": avg_dur,
            "loss_count": d["loss"],
            "loss_rate": loss_rate,
            "sections": len(d["sections"]),
            "types": len(d["types"]),
            "efficiency_score": max(0, eff_score),
        })
    board.sort(key=lambda x: -x["incidents"])
    return board


# ─── SECTION DRILL-DOWN ────────────────────────────────────────────
def build_section_drilldown(records):
    sec_map = defaultdict(lambda: {
        "count":0,"dur":0,"loss":0,
        "machines":defaultdict(int),
        "types":defaultdict(int),
        "attns":defaultdict(int),
        "daily":defaultdict(int),
    })
    for r in records:
        s = r["section"]
        sec_map[s]["count"] += 1
        sec_map[s]["dur"]   += r["duration"]
        if r["loss"]: sec_map[s]["loss"] += 1
        sec_map[s]["machines"][r["machine"]] += 1
        sec_map[s]["types"][r["type"]] += 1
        sec_map[s]["attns"][r["attendant"]] += 1
        if r["date"]:
            sec_map[s]["daily"][r["date"].strftime("%Y-%m-%d")] += 1

    result = {}
    for sec, d in sec_map.items():
        top_m = sorted(d["machines"].items(), key=lambda x:-x[1])[:5]
        top_t = sorted(d["types"].items(),    key=lambda x:-x[1])[:5]
        top_a = sorted(d["attns"].items(),    key=lambda x:-x[1])[:5]
        daily_sorted = [{"date":k,"count":v} for k,v in sorted(d["daily"].items())]
        result[sec] = {
            "count":d["count"],
            "dur_hrs":round(d["dur"]/60,1),
            "loss":d["loss"],
            "loss_pct":round(d["loss"]/d["count"]*100,1) if d["count"] else 0,
            "top_machines":  [{"name":k,"count":v} for k,v in top_m],
            "top_types":     [{"name":k,"count":v} for k,v in top_t],
            "top_attendants":[{"name":k,"count":v} for k,v in top_a],
            "trend": daily_sorted,
        }
    return result


# ─── ROUTES ────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dashboard")
def dashboard():
    raw, err = fetch_raw()
    if err: return jsonify({"error": err}), 500
    records = build_records(raw)

    # date filter
    df = request.args.get("from")
    dt = request.args.get("to")
    if df:
        try:
            d = datetime.strptime(df, "%Y-%m-%d")
            records = [r for r in records if r["date"] and r["date"] >= d]
        except: pass
    if dt:
        try:
            d = datetime.strptime(dt, "%Y-%m-%d")
            records = [r for r in records if r["date"] and r["date"] <= d]
        except: pass

    total   = len(records)
    tot_dur = sum(r["duration"] for r in records)
    yes_loss= sum(1 for r in records if r["loss"])
    avg_dur = round(tot_dur/total,1) if total else 0
    loss_pct= round(yes_loss/total*100,1) if total else 0

    sections  = [r["section"]   for r in records]
    types     = [r["type"]      for r in records]
    machines  = [r["machine"]   for r in records]
    attns     = [r["attendant"] for r in records]
    losses    = [r["loss"]      for r in records]
    durations = [r["duration"]  for r in records]

    sec_cnt  = gcnt(sections)
    type_cnt = gcnt(types)
    mach_cnt = gcnt(machines)
    attn_cnt = gcnt(attns)

    sec_dur = defaultdict(float)
    for s,d in zip(sections,durations): sec_dur[s] += d

    daily = defaultdict(int)
    weekly= defaultdict(int)
    monthly=defaultdict(int)
    for r in records:
        if r["date"]:
            daily[r["date"].strftime("%Y-%m-%d")] += 1
            weekly[r["date"].strftime("%Y-W%W")] += 1
            monthly[r["date"].strftime("%Y-%m")]  += 1

    trend_daily   = [{"date":k,"count":v} for k,v in sorted(daily.items())]
    trend_weekly  = [{"date":k,"count":v} for k,v in sorted(weekly.items())]
    trend_monthly = [{"date":k,"count":v} for k,v in sorted(monthly.items())]

    top_mach = sorted(mach_cnt.items(), key=lambda x:-x[1])[:12]
    top_type = sorted(type_cnt.items(), key=lambda x:-x[1])[:12]
    top_attn = sorted(attn_cnt.items(), key=lambda x:-x[1])[:12]

    loss_cnt = gcnt(["With Loss" if x else "No Loss" for x in losses])

    # hour distribution
    hour_dist = defaultdict(int)
    for r in records:
        for fmt in ("%I:%M:%S %p","%H:%M:%S","%I:%M %p","%H:%M"):
            try:
                h = datetime.strptime(str(r["start"]).strip(), fmt).hour
                hour_dist[h] += 1
                break
            except: pass
    hour_labels = [f"{h:02d}:00" for h in range(24)]
    hour_data   = [hour_dist.get(h,0) for h in range(24)]

    # table rows
    table_rows = [{
        "Date": r["date_str"],
        "Section": r["section"],
        "Machine": r["machine"],
        "Breakdown Type": r["type"],
        "Start": r["start"],
        "End": r["end"],
        "Duration (min)": r["duration"],
        "Production Loss": "YES" if r["loss"] else "No",
        "Attendant": r["attendant"],
        "Slip No.": r["slip"],
        "Remark": r["remark"],
    } for r in records]

    return jsonify({
        "kpis": {"total":total,"total_hrs":round(tot_dur/60,1),"avg_min":avg_dur,
                 "loss_pct":loss_pct,"yes_loss":yes_loss},
        "by_section":   {"labels":list(sec_cnt.keys()),"counts":list(sec_cnt.values()),
                         "durations":[round(sec_dur.get(k,0)/60,1) for k in sec_cnt]},
        "by_type":      {"labels":[x[0] for x in top_type],"counts":[x[1] for x in top_type]},
        "by_machine":   {"labels":[x[0] for x in top_mach],"counts":[x[1] for x in top_mach]},
        "by_attendant": {"labels":[x[0] for x in top_attn],"counts":[x[1] for x in top_attn]},
        "by_loss":      {"labels":list(loss_cnt.keys()),"counts":list(loss_cnt.values())},
        "trend_daily":   trend_daily,
        "trend_weekly":  trend_weekly,
        "trend_monthly": trend_monthly,
        "hour_dist":    {"labels":hour_labels,"data":hour_data},
        "ai_suggestions": generate_ai_suggestions(records),
        "leaderboard":    build_leaderboard(records),
        "drilldown":      build_section_drilldown(records),
        "rows": table_rows[-500:],
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)