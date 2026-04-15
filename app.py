from flask import Flask, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)

# Database Configuration for Render
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix for Render Postgres URL
if app.config['SQLALCHEMY_DATABASE_URI'] and app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)

db = SQLAlchemy(app)

# Database Model
class Breakdown(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    section = db.Column(db.String(50), nullable=False)
    machine = db.Column(db.String(50), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date,
            'section': self.section,
            'machine': self.machine
        }

# Create tables
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    records = Breakdown.query.order_by(Breakdown.id.desc()).all()
    total_records = len(records)
    return render_template('index.html', records=records, total=total_records)

@app.route('/seed')
def seed_data():
    Breakdown.query.delete()
    
    sample_data = [
        (755, "4/15/2026", "RD", "7H1"),
        (754, "4/15/2026", "PD-2", "5H-1"),
        (753, "4/14/2026", "GI-1", "N/A"),
        (752, "4/14/2026", "WET MACHINE", "WET M/C-1"),
        (751, "4/14/2026", "PD-1", "7H-A"),
        (750, "4/14/2026", "PD-1", "4H-B"),
    ]
    
    for sid, sdate, ssection, smachine in sample_data:
        record = Breakdown(id=sid, date=sdate, section=ssection, machine=smachine)
        db.session.add(record)
    
    db.session.commit()
    return "✅ Sample data seeded successfully! <br><a href='/'>Go to Dashboard</a>"

# Important: This allows Render to start the app correctly
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)