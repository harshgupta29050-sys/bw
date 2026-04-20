from flask import Flask, render_template, jsonify
import requests, json
from datetime import datetime, timedelta

app = Flask(__name__)

# ─── YOUR SHEET CONFIG ────────────────────────────────────
SHEET_ID   = "1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q"
SHEET_NAME = "Form Responses 1"
# ──────────────────────────────────────────────────────────

URL = (f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
       f"/gviz/tq?tqx=out:json&sheet={SHEET_NAME}")


def parse_time(t):
    if not t:
        return None
    t = str(t).strip()
    for fmt in ("%I:%M:%S %p", "%H:%M:%S", "%I:%M %p", "%H:%M"):
        try:
            return datetime.strptime(t, fmt).time()
        except ValueError:
            pass
    return None


def duration_minutes(start_str, end_str):
    s, e = parse_time(start_str), parse_time(end_str)
    if s is None or e is None:
        return 0
    dt_s = datetime.combine(datetime.today(), s)
    dt_e = datetime.combine(datetime.today(), e)
    if dt_e < dt_s:
        dt_e += timedelta(days=1)
    diff = (dt_e - dt_s).total_seconds() / 60
    return round(diff, 1) if 0 < diff < 600 else 0


def machine_for_row(r):
    for col in ["pd-1 machines", "pd-2 machines", "rd machines",
                "fm machines", "wet machines"]:
        v = str(r.get(col, "")).strip()
        if v and v.lower() not in ("skip", ""):
            return v
    return "—"


def fetch_data():
    try:
        resp = requests.get(URL, timeout=12)
        resp.raise_for_status()
        raw   = resp.text
        start = raw.index("(") + 1
        end   = raw.rindex(")")
        data  = json.loads(raw[start:end])
        cols  = [c["label"].strip().lower() for c in data["table"]["cols"]]
        rows  = []
        for row in data["table"]["rows"]:
            if row is None:
                continue
            record = {}
            for i, cell in enumerate(row["c"]):
                record[cols[i]] = (cell["v"] if cell and cell.get("v") is not None else "")
            rows.append(record)
        return rows, None
    except Exception as ex:
        return [], str(ex)


def gcnt(lst):
    d = {}
    for v in lst:
        d[v] = d.get(v, 0) + 1
    return d


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dashboard")
def dashboard():
    rows, err = fetch_data()
    if err:
        return jsonify({"error": err}), 500

    sections, types, machines, losses, durations, dates, attns = \
        [], [], [], [], [], [], []

    table_rows = []
    for r in rows:
        sec   = str(r.get("section", "")).strip() or "Unknown"
        btype = str(r.get("breakdown type", "")).strip() or "Unknown"
        mach  = machine_for_row(r)
        loss  = str(r.get("production loss", "")).strip()
        start = r.get("start time", "")
        end   = r.get("end time", "")
        date  = str(r.get("date", "")).strip()
        attn  = str(r.get("attendent name", "")).strip() or "Unknown"
        slip  = str(r.get("slip no.", "")).strip()
        rem   = str(r.get("remark", "")).strip()
        dur   = duration_minutes(start, end)

        sections.append(sec)
        types.append(btype)
        machines.append(mach)
        losses.append(loss.upper() in ("YES", "Y"))
        durations.append(dur)
        dates.append(date)
        attns.append(attn)

        table_rows.append({
            "Date": date, "Section": sec, "Machine": mach,
            "Breakdown Type": btype,
            "Start": str(start), "End": str(end),
            "Duration (min)": dur,
            "Production Loss": loss, "Attendant": attn,
            "Slip No.": slip, "Remark": rem,
        })

    total     = len(rows)
    tot_dur   = sum(durations)
    yes_loss  = sum(losses)
    avg_dur   = round(tot_dur / total, 1) if total else 0
    loss_pct  = round(yes_loss / total * 100, 1) if total else 0

    sec_cnt  = gcnt(sections)
    type_cnt = gcnt(types)
    mach_cnt = gcnt(machines)
    attn_cnt = gcnt(attns)
    loss_cnt = gcnt(["With Loss" if x else "No Loss" for x in losses])

    # section durations
    sec_dur = {}
    for s, d in zip(sections, durations):
        sec_dur[s] = sec_dur.get(s, 0) + d

    daily = {}
    for d in dates:
        if d:
            daily[d] = daily.get(d, 0) + 1
    trend = [{"date": k, "count": v} for k, v in sorted(daily.items())]

    top_mach = sorted(mach_cnt.items(), key=lambda x: -x[1])[:10]
    top_attn = sorted(attn_cnt.items(), key=lambda x: -x[1])[:10]
    top_type = sorted(type_cnt.items(), key=lambda x: -x[1])[:12]

    return jsonify({
        "kpis": {
            "total": total,
            "total_hrs": round(tot_dur / 60, 1),
            "avg_min": avg_dur,
            "loss_pct": loss_pct,
            "yes_loss": yes_loss,
        },
        "by_section":  {
            "labels":    list(sec_cnt.keys()),
            "counts":    list(sec_cnt.values()),
            "durations": [round(sec_dur.get(k, 0)/60, 1) for k in sec_cnt],
        },
        "by_type":     {
            "labels": [x[0] for x in top_type],
            "counts": [x[1] for x in top_type],
        },
        "by_machine":  {
            "labels": [x[0] for x in top_mach],
            "counts": [x[1] for x in top_mach],
        },
        "by_attendant":{
            "labels": [x[0] for x in top_attn],
            "counts": [x[1] for x in top_attn],
        },
        "by_loss":     {
            "labels": list(loss_cnt.keys()),
            "counts": list(loss_cnt.values()),
        },
        "trend": trend,
        "rows":  table_rows[-500:],
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)