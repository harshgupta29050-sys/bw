from flask import Flask, render_template
import gspread
from google.oauth2.service_account import Credentials
import os
import json

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
    
    # Calculate live stats
    total_logged = len(records)
    open_count = sum(1 for r in records if str(r.get('Status', '')).lower() in ['open', 'pending'])
    in_progress = sum(1 for r in records if str(r.get('Status', '')).lower() == 'in progress')
    resolved = sum(1 for r in records if str(r.get('Status', '')).lower() == 'resolved')
    
    return render_template('index.html', 
                           records=records,
                           total_logged=total_logged,
                           open_count=open_count,
                           in_progress=in_progress,
                           resolved=resolved)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)