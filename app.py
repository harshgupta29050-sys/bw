"""
RTMS Breakdown Analytics — app.py
Google Sheet: 1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q
Tab: Form Responses 1

Columns (exact, Row 1):
  A Timestamp | B SECTION | C PD-1 MACHINES | D PD-2 MACHINES
  E RD MACHINES | F FM MACHINES | G WET MACHINES | H BREAKDOWN TYPE
  I START TIME | J ATTENDENT NAME | K REMARK | L END TIME
  M DATE | N PRODUCTION LOSS | O SLIP NO.
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
from collections import defaultdict
import requests, json, re

app = Flask(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────────
SHEET_ID  = "1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q"
SHEET_TAB = "Form Responses 1"
GVIZ_URL  = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
             f"/gviz/tq?tqx=out:json&sheet={SHEET_TAB}")

# ─── FETCH ────────────────────────────────────────────────────────────
def fetch_sheet():
    try:
        r = requests.get(GVIZ_URL, timeout=15)
        r.raise_for_status()
        raw     = r.text
        payload = json.loads(raw[raw.index("(") + 1 : raw.rindex(")")])
        cols    = [c["label"].strip().lower() for c in payload["table"]["cols"]]
        rows    = []
        for row in payload["table"]["rows"]:
            if row is None:
                continue
            rec = {}
            for i, cell in enumerate(row["c"]):
                rec[cols[i]] = cell["v"] if cell and cell.get("v") is not None else ""
            rows.append(rec)
        return rows, None
    except Exception as e:
        return [], str(e)

# ─── PARSERS ──────────────────────────────────────────────────────────
_TIME_FMTS = ("%I:%M:%S %p", "%H:%M:%S", "%I:%M %p", "%H:%M")
_DATE_FMTS = ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y")

def _parse_time(v):
    v = str(v).strip()
    for f in _TIME_FMTS:
        try: return datetime.strptime(v, f).time()
        except: pass
    return None

def _parse_date(v):
    v = str(v).strip()
    if v.startswith("Date("):
        p = v[5:-1].split(",")
        try: return datetime(int(p[0]), int(p[1]) + 1, int(p[2]))
        except: pass
    for f in _DATE_FMTS:
        try: return datetime.strptime(v, f)
        except: pass
    return None

def _duration(start, end):
    s, e = _parse_time(str(start)), _parse_time(str(end))
    if not s or not e: return 0.0
    ds = datetime.combine(datetime.today(), s)
    de = datetime.combine(datetime.today(), e)
    if de < ds: de += timedelta(days=1)
    d  = (de - ds).total_seconds() / 60
    return round(d, 1) if 0 < d < 720 else 0.0

_MCOLS = ("pd-1 machines","pd-2 machines","rd machines","fm machines","wet machines")
def _machine(r):
    for c in _MCOLS:
        v = str(r.get(c,"")).strip()
        if v and v.lower() != "skip": return v
    return "—"

def _norm_sec(s):
    s = str(s).strip()
    s = re.sub(r"\s*-\s*", "-", s)
    return s or "Unknown"

# ─── BUILD RECORDS ────────────────────────────────────────────────────
def build_records(raw):
    out = []
    for r in raw:
        sec       = _norm_sec(r.get("section",""))
        btype     = str(r.get("breakdown type","")).strip() or "Unknown"
        machine   = _machine(r)
        start_raw = r.get("start time","")
        end_raw   = r.get("end time","")
        date_raw  = r.get("date","")
        attn      = str(r.get("attendent name","")).strip() or "Unknown"
        remark    = str(r.get("remark","")).strip()
        loss_raw  = str(r.get("production loss","")).strip()
        slip      = str(r.get("slip no.","")).strip()
        ts_raw    = str(r.get("timestamp","")).strip()

        date_obj  = _parse_date(str(date_raw))
        dur       = _duration(start_raw, end_raw)
        loss_bool = loss_raw.upper() in ("YES","Y")
        st_obj    = _parse_time(str(start_raw))
        hour      = st_obj.hour if st_obj else None
        dow       = date_obj.weekday() if date_obj else None  # 0=Mon

        out.append({
            # ── display columns ──
            "Timestamp":      ts_raw,
            "Date":           str(date_raw).strip(),
            "Section":        sec,
            "Machine":        machine,
            "Breakdown Type": btype,
            "Start Time":     str(start_raw),
            "End Time":       str(end_raw),
            "Duration (min)": dur,
            "Production Loss":"YES" if loss_bool else "No",
            "Attendant":      attn,
            "Slip No.":       slip,
            "Remark":         remark,
            # ── analytic ──
            "_date": date_obj,
            "_loss": loss_bool,
            "_dur":  dur,
            "_hour": hour,
            "_dow":  dow,
            "_sec":  sec,
            "_type": btype,
            "_mach": machine,
            "_attn": attn,
        })
    return out

# ─── SMALL HELPERS ───────────────────────────────────────────────────
def gcnt(lst):
    d = defaultdict(int)
    for v in lst: d[str(v)] += 1
    return dict(d)

def top_n(d, n=12):
    return sorted(d.items(), key=lambda x: -x[1])[:n]

# ─── AI ENGINE ───────────────────────────────────────────────────────
def ai_insights(records, context="global"):
    """Generate rule-based AI suggestions from records."""
    if not records: return []
    total = len(records)
    sec_cnt  = defaultdict(int); sec_loss = defaultdict(int); sec_dur = defaultdict(float)
    type_cnt = defaultdict(int); attn_cnt = defaultdict(int); attn_dur = defaultdict(float)
    mach_cnt = defaultdict(int); hour_cnt = defaultdict(int); daily    = defaultdict(int)

    for r in records:
        sec_cnt [r["_sec"]]  += 1;  sec_dur [r["_sec"]]  += r["_dur"]
        type_cnt[r["_type"]] += 1;  attn_cnt[r["_attn"]] += 1
        attn_dur[r["_attn"]] += r["_dur"]
        if r["_mach"] != "—": mach_cnt[r["_mach"]] += 1
        if r["_loss"]:         sec_loss[r["_sec"]]  += 1
        if r["_hour"] is not None: hour_cnt[r["_hour"]] += 1
        if r["_date"]: daily[r["_date"].date()] += 1

    tips = []

    # 1 Peak section
    if sec_cnt:
        ts = max(sec_cnt, key=sec_cnt.get)
        pct = round(sec_cnt[ts]/total*100,1)
        tips.append({"type":"critical","icon":"🔴","title":f"Hot Zone: {ts}",
            "body":f"{ts} contributes {pct}% of all breakdowns ({sec_cnt[ts]} incidents). Immediate preventive maintenance schedule recommended.",
            "metric":f"{sec_cnt[ts]} incidents"})

    # 2 Top failure type
    if type_cnt:
        tt = max(type_cnt, key=type_cnt.get)
        pct2 = round(type_cnt[tt]/total*100,1)
        tips.append({"type":"warning","icon":"⚡","title":f"Dominant Fault: {tt}",
            "body":f"'{tt}' accounts for {pct2}% of failures ({type_cnt[tt]} cases). Root cause analysis and targeted technician training advised.",
            "metric":f"{type_cnt[tt]} cases"})

    # 3 Production loss leader
    if sec_loss:
        wl = max(sec_loss, key=sec_loss.get)
        lr = round(sec_loss[wl]/sec_cnt[wl]*100,1)
        tips.append({"type":"critical","icon":"📉","title":f"Loss Leader: {wl}",
            "body":f"{wl} has {lr}% production-loss rate ({sec_loss[wl]} incidents with confirmed loss). Rapid-response protocol needed.",
            "metric":f"{lr}% loss rate"})

    # 4 Peak hour
    if hour_cnt:
        ph   = max(hour_cnt, key=hour_cnt.get)
        ampm = "AM" if ph < 12 else "PM"
        h12  = ph if 1<=ph<=12 else (ph-12 if ph>12 else 12)
        tips.append({"type":"info","icon":"🕐","title":f"Peak Hour: {h12}:00 {ampm}",
            "body":f"Maximum breakdowns occur at {h12}:00 {ampm} ({hour_cnt[ph]} incidents). Pre-shift inspection at this time is strongly recommended.",
            "metric":f"{hour_cnt[ph]} incidents"})

    # 5 High-risk machine
    if mach_cnt:
        tm = max(mach_cnt, key=mach_cnt.get)
        tips.append({"type":"warning","icon":"⚙️","title":f"Risk Machine: {tm}",
            "body":f"Machine '{tm}' has the highest incident count ({mach_cnt[tm]}). Schedule PM, check lubrication, and maintain a spare-parts buffer.",
            "metric":f"{mach_cnt[tm]} breakdowns"})

    # 6 WoW trend
    if len(daily) >= 14:
        sd = sorted(daily); last7=sum(daily[d] for d in sd[-7:]); prev7=sum(daily[d] for d in sd[-14:-7])
        if prev7 > 0:
            chg = round((last7-prev7)/prev7*100,1)
            if chg > 10:
                tips.append({"type":"critical","icon":"📈","title":f"Rising Trend +{chg}%",
                    "body":f"Last 7 days: {last7} vs previous 7: {prev7} (+{chg}%). Escalating pattern—investigate systemic root cause.",
                    "metric":f"+{chg}% week-on-week"})
            elif chg < -10:
                tips.append({"type":"success","icon":"✅","title":f"Improving Trend {chg}%",
                    "body":f"Breakdowns down {abs(chg)}% this week ({last7} vs {prev7}). Current strategy working—maintain momentum.",
                    "metric":f"{chg}% WoW"})

    # 7 Overloaded technician
    if len(attn_cnt) > 1:
        avg_l = total/len(attn_cnt); ta = max(attn_cnt, key=attn_cnt.get)
        if attn_cnt[ta] > avg_l*1.5:
            tips.append({"type":"warning","icon":"👷","title":f"Overloaded: {ta}",
                "body":f"{ta} handles {attn_cnt[ta]} incidents ({round(attn_cnt[ta]/avg_l,1)}× average). Redistribute workload to prevent fatigue errors.",
                "metric":f"{attn_cnt[ta]} incidents"})

    # 8 Avg duration alert
    durs = [r["_dur"] for r in records if r["_dur"]>0]
    if durs:
        avg_d = round(sum(durs)/len(durs),1)
        if avg_d > 30:
            tips.append({"type":"warning","icon":"⏱","title":f"Slow Response: {avg_d} min avg",
                "body":f"Average breakdown duration is {avg_d} minutes. Target under 20 min. Consider pre-positioned spares and faster escalation protocol.",
                "metric":f"{avg_d} min avg"})
        else:
            tips.append({"type":"success","icon":"⚡","title":f"Fast Response: {avg_d} min avg",
                "body":f"Average resolution time of {avg_d} min is excellent. Benchmark this performance for other sections.",
                "metric":f"{avg_d} min avg"})

    return tips[:8]

# ─── LEADERBOARD ─────────────────────────────────────────────────────
def leaderboard(records):
    data = defaultdict(lambda:{"count":0,"dur":0.0,"loss":0,"secs":set(),"types":set()})
    for r in records:
        a = r["_attn"]
        data[a]["count"] += 1; data[a]["dur"] += r["_dur"]
        if r["_loss"]: data[a]["loss"] += 1
        data[a]["secs"].add(r["_sec"]); data[a]["types"].add(r["_type"])
    board=[]
    for name,d in data.items():
        avg_d = round(d["dur"]/d["count"],1) if d["count"] else 0
        lr    = round(d["loss"]/d["count"]*100,1) if d["count"] else 0
        score = max(0.0, round(d["count"]*10 - avg_d*0.5, 1))
        board.append({"name":name,"incidents":d["count"],"total_dur":round(d["dur"],1),
                      "avg_dur":avg_d,"loss":d["loss"],"loss_rate":lr,
                      "sections":len(d["secs"]),"types":len(d["types"]),"score":score})
    board.sort(key=lambda x:-x["incidents"])
    return board

# ─── SECTION DRILLDOWN ────────────────────────────────────────────────
def section_drilldown(records):
    sm = defaultdict(lambda:{
        "count":0,"dur":0.0,"loss":0,
        "machines":defaultdict(int),"types":defaultdict(int),
        "attns":defaultdict(int),"daily":defaultdict(int),
        "hours":defaultdict(int),"remarks":[],
    })
    for r in records:
        s = r["_sec"]
        sm[s]["count"]+=1; sm[s]["dur"]+=r["_dur"]
        if r["_loss"]: sm[s]["loss"]+=1
        sm[s]["machines"][r["_mach"]]+=1
        sm[s]["types"][r["_type"]]+=1
        sm[s]["attns"][r["_attn"]]+=1
        if r["_date"]: sm[s]["daily"][r["_date"].strftime("%Y-%m-%d")]+=1
        if r["_hour"] is not None: sm[s]["hours"][r["_hour"]]+=1
        if r["Remark"]: sm[s]["remarks"].append(r["Remark"])

    result={}
    for sec,d in sm.items():
        top_m = top_n(d["machines"],6); top_t = top_n(d["types"],6)
        top_a = top_n(d["attns"],6)
        # hour heatmap
        hour_d = [d["hours"].get(h,0) for h in range(24)]
        trend  = [{"date":k,"count":v} for k,v in sorted(d["daily"].items())]
        # sub-ai for this section
        sec_recs = [r for r in records if r["_sec"]==sec]
        sub_ai   = ai_insights(sec_recs, context=sec)

        result[sec]={
            "count":d["count"],"dur_hrs":round(d["dur"]/60,1),
            "loss":d["loss"],"loss_pct":round(d["loss"]/d["count"]*100,1) if d["count"] else 0,
            "avg_dur":round(d["dur"]/d["count"],1) if d["count"] else 0,
            "top_machines":  [{"name":k,"count":v} for k,v in top_m],
            "top_types":     [{"name":k,"count":v} for k,v in top_t],
            "top_attendants":[{"name":k,"count":v} for k,v in top_a],
            "hour_dist":     hour_d,
            "trend":         trend,
            "ai":            sub_ai[:4],
            "recent_remarks":d["remarks"][-5:],
        }
    return result

# ─── ROUTES ──────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


def _filter_by_date(records, date_from, date_to):
    if date_from:
        try:
            df=datetime.strptime(date_from,"%Y-%m-%d")
            records=[r for r in records if r["_date"] and r["_date"]>=df]
        except: pass
    if date_to:
        try:
            dt=datetime.strptime(date_to,"%Y-%m-%d")
            records=[r for r in records if r["_date"] and r["_date"]<=dt]
        except: pass
    return records


@app.route("/api/dashboard")
def api_dashboard():
    raw,err = fetch_sheet()
    if err: return jsonify({"error":err}),500
    records = build_records(raw)
    records = _filter_by_date(records,
                              request.args.get("from","").strip(),
                              request.args.get("to","").strip())

    total   = len(records)
    tot_dur = sum(r["_dur"] for r in records)
    yes_loss= sum(1 for r in records if r["_loss"])

    sec_cnt  = gcnt(r["_sec"]  for r in records)
    type_cnt = gcnt(r["_type"] for r in records)
    mach_cnt = gcnt(r["_mach"] for r in records)
    attn_cnt = gcnt(r["_attn"] for r in records)
    loss_cnt = gcnt("With Loss" if r["_loss"] else "No Loss" for r in records)

    sec_dur  = defaultdict(float)
    for r in records: sec_dur[r["_sec"]] += r["_dur"]

    # trends
    daily_m=defaultdict(int); week_m=defaultdict(int); month_m=defaultdict(int)
    for r in records:
        if r["_date"]:
            daily_m [r["_date"].strftime("%Y-%m-%d")]+=1
            week_m  [r["_date"].strftime("%Y-W%W")]  +=1
            month_m [r["_date"].strftime("%Y-%m")]   +=1

    hour_dist = [0]*24
    for r in records:
        if r["_hour"] is not None: hour_dist[r["_hour"]]+=1

    dow_dist = [0]*7
    for r in records:
        if r["_dow"] is not None: dow_dist[r["_dow"]]+=1

    # table rows — all fields
    TABLE_COLS=["Timestamp","Date","Section","Machine","Breakdown Type",
                "Start Time","End Time","Duration (min)","Production Loss",
                "Attendant","Slip No.","Remark"]
    table_rows=[{c:r[c] for c in TABLE_COLS} for r in records]

    return jsonify({
        "kpis":{
            "total":total,
            "total_hrs":round(tot_dur/60,1),
            "avg_min":round(tot_dur/total,1) if total else 0,
            "loss_pct":round(yes_loss/total*100,1) if total else 0,
            "yes_loss":yes_loss,
        },
        "by_section" :{"labels":list(sec_cnt.keys()),"counts":list(sec_cnt.values()),
                        "durations":[round(sec_dur.get(k,0)/60,1) for k in sec_cnt]},
        "by_type"    :{"labels":[x[0] for x in top_n(type_cnt,12)],
                       "counts":[x[1] for x in top_n(type_cnt,12)]},
        "by_machine" :{"labels":[x[0] for x in top_n(mach_cnt,12)],
                       "counts":[x[1] for x in top_n(mach_cnt,12)]},
        "by_attendant":{"labels":[x[0] for x in top_n(attn_cnt,12)],
                        "counts":[x[1] for x in top_n(attn_cnt,12)]},
        "by_loss"    :{"labels":list(loss_cnt.keys()),"counts":list(loss_cnt.values())},
        "trend_daily"  :[{"date":k,"count":v} for k,v in sorted(daily_m.items())],
        "trend_weekly" :[{"date":k,"count":v} for k,v in sorted(week_m.items())],
        "trend_monthly":[{"date":k,"count":v} for k,v in sorted(month_m.items())],
        "hour_dist":{"labels":[f"{h:02d}:00" for h in range(24)],"data":hour_dist},
        "dow_dist" :{"labels":["Mon","Tue","Wed","Thu","Fri","Sat","Sun"],"data":dow_dist},
        "ai_suggestions":ai_insights(records),
        "leaderboard"   :leaderboard(records),
        "drilldown"     :section_drilldown(records),
        "rows"          :table_rows,       # FULL dataset — sorting done client-side
    })


@app.route("/api/section/<path:sec_name>")
def api_section(sec_name):
    """Dedicated endpoint for single-section deep-dive."""
    raw,err = fetch_sheet()
    if err: return jsonify({"error":err}),500
    records = build_records(raw)
    records = _filter_by_date(records,
                              request.args.get("from","").strip(),
                              request.args.get("to","").strip())
    sec_recs=[r for r in records if r["_sec"]==sec_name]
    if not sec_recs: return jsonify({"error":"Section not found"}),404

    dd = section_drilldown(records)
    data = dd.get(sec_name,{})

    TABLE_COLS=["Timestamp","Date","Section","Machine","Breakdown Type",
                "Start Time","End Time","Duration (min)","Production Loss",
                "Attendant","Slip No.","Remark"]
    data["rows"]=[{c:r[c] for c in TABLE_COLS} for r in sec_recs]
    data["ai"]  = ai_insights(sec_recs, context=sec_name)
    return jsonify(data)


if __name__=="__main__":
    app.run(debug=True, port=5000)