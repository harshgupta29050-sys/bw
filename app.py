from flask import Flask, render_template
import gspread
from google.oauth2.service_account import Credentials
import os
import json
import pandas as pd
import plotly.express as px
import plotly.utils

app = Flask(__name__)

def get_google_sheet_data():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not creds_json:
        return []
    
    creds_dict = json.loads(creds_json)
    scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # Your Google Sheet (already added)
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q/edit")
    data = sheet.sheet1.get_all_records()
    return data

@app.route('/')
def index():
    records = get_google_sheet_data()
    df = pd.DataFrame(records)

    # Stats
    total_logged = len(records)
    open_count = sum(1 for r in records if str(r.get('Status', '')).lower() in ['open', 'pending'])
    in_progress = sum(1 for r in records if str(r.get('Status', '')).lower() == 'in progress')
    resolved = sum(1 for r in records if str(r.get('Status', '')).lower() == 'resolved')

    # Interactive Charts
    # 1. Daily Trend
    if not df.empty and 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
        trend = df.groupby(df['Date'].dt.date).size().reset_index(name='count')
        fig_trend = px.line(trend, x='Date', y='count', title='Daily Breakdown Trend', markers=True, line_shape='spline')
    else:
        fig_trend = px.line(title='Daily Breakdown Trend')
    fig_trend.update_layout(template='plotly_dark', height=380)

    # 2. Breakdown by Machine / Section
    if not df.empty and 'Machine' in df.columns:
        machine_count = df['Machine'].value_counts().reset_index()
        fig_section = px.bar(machine_count, x='Machine', y='count', title='Breakdowns by Machine')
    else:
        fig_section = px.bar(title='Breakdowns by Machine')
    fig_section.update_layout(template='plotly_dark', height=380)

    # 3. Priority Pie Chart
    if not df.empty and 'Priority' in df.columns:
        priority_count = df['Priority'].value_counts()
        fig_priority = px.pie(values=priority_count.values, names=priority_count.index, title='Priority Distribution')
    else:
        fig_priority = px.pie(title='Priority Distribution')
    fig_priority.update_layout(template='plotly_dark', height=380)

    trendJSON = json.dumps(fig_trend, cls=plotly.utils.PlotlyJSONEncoder)
    sectionJSON = json.dumps(fig_section, cls=plotly.utils.PlotlyJSONEncoder)
    priorityJSON = json.dumps(fig_priority, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('index.html', 
                           records=records,
                           total_logged=total_logged,
                           open_count=open_count,
                           in_progress=in_progress,
                           resolved=resolved,
                           trendJSON=trendJSON,
                           sectionJSON=sectionJSON,
                           priorityJSON=priorityJSON)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)