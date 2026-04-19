from flask import Flask, render_template
import gspread
from google.oauth2.service_account import Credentials
import os
import json

app = Flask(__name__)

def get_google_sheet_data():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    if not creds_json:
        return {"error": "GOOGLE_CREDENTIALS not found"}
    
    creds_dict = json.loads(creds_json)
    scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    
    # ←←← PASTE YOUR ACTUAL GOOGLE SHEET LINK HERE
    sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q/edit?usp=sharing")
    
    data = sheet.sheet1.get_all_records()
    return data

@app.route('/')
def index():
    records = get_google_sheet_data()
    total = len(records) if isinstance(records, list) else 0
    return render_template('index.html', records=records, total_logged=total)

# DEBUG ROUTE - Visit this to see raw data from your sheet
@app.route('/debug')
def debug():
    data = get_google_sheet_data()
    return f"<h1>Debug - Raw Data from Google Sheet</h1><pre>{json.dumps(data, indent=2)}</pre>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    
