from flask import Flask, render_template, jsonify
import gspread
from google.oauth2.service_account import Credentials
import os
import json

app = Flask(__name__)

def get_google_sheet_data():
    try:
        creds_json = os.environ.get('GOOGLE_CREDENTIALS')
        if not creds_json:
            return {"error": "GOOGLE_CREDENTIALS environment variable not found"}

        creds_dict = json.loads(creds_json)
        scopes = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        
        # Your exact Google Sheet
        sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1P34KUrokZFbE5PqLOXkSc6EviKUqzGtpEiBOMmseh1Q/edit")
        data = sheet.sheet1.get_all_records()
        return data
    except Exception as e:
        return {"error": str(e)}

@app.route('/')
def index():
    records = get_google_sheet_data()
    return render_template('index.html', records=records if isinstance(records, list) else [])

@app.route('/debug')
def debug():
    data = get_google_sheet_data()
    return f"<h1>DEBUG - Raw Data from Google Sheet</h1><pre>{json.dumps(data, indent=2, ensure_ascii=False)}</pre>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)