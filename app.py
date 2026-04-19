from flask import Flask, render_template
import gspread
from google.oauth2.service_account import Credentials
import os
import pandas as pd
import json
from datetime import datetime

app = Flask(__name__)

# ====================== GOOGLE SHEETS INTEGRATION ======================
def get_google_sheet_data():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not creds_json:
        return []  # fallback if credentials not set

    creds_dict = json.loads(creds_json)
    scopes = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)

    # ←←← PASTE YOUR GOOGLE SHEET LINK HERE ↓↓↓
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q/edit?usp=sharing")
    
    data = sheet.sheet1.get_all_records()   # Reads first sheet
    return data


@app.route('/')
def index():
    records = get_google_sheet_data()
    total_records = len(records)

    # Sample data for Daily Trend Chart (you can later pull this from sheet too)
    trend_data = pd.DataFrame({
        'Date': pd.date_range(start='2026-04-01', periods=15),
        'Breakdowns': [35, 28, 42, 31, 45, 38, 29, 50, 33, 41, 27, 36, 44, 30, 22]
    })

    # Convert to Plotly JSON for the chart
    import plotly.express as px
    import plotly.utils

    fig = px.line(trend_data, x='Date', y='Breakdowns', title='Daily Breakdown Trend',
                  line_shape='spline', markers=True)
    fig.update_layout(template='plotly_dark', height=380, margin=dict(l=20, r=20, t=40, b=20))
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('index.html', 
                           records=records,
                           total=total_records,
                           graphJSON=graphJSON)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)