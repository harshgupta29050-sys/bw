from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def index():
    # Hardcoded sample data (no database needed)
    records = [
        {"id": 755, "date": "4/15/2026", "section": "RD", "machine": "7H1"},
        {"id": 754, "date": "4/15/2026", "section": "PD-2", "machine": "5H-1"},
        {"id": 753, "date": "4/14/2026", "section": "GI-1", "machine": "N/A"},
        {"id": 752, "date": "4/14/2026", "section": "WET MACHINE", "machine": "WET M/C-1"},
        {"id": 751, "date": "4/14/2026", "section": "PD-1", "machine": "7H-A"},
        {"id": 750, "date": "4/14/2026", "section": "PD-1", "machine": "4H-B"},
    ]
    total_records = len(records)
    
    return render_template('index.html', records=records, total=total_records)

@app.route('/seed')
def seed_data():
    return "✅ Database is disabled for now.<br><a href='/'>Go to Dashboard</a>"

# Important for Render
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)