import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta

db = sqlite3.connect('garment.db')
plants = db.execute('SELECT id, total_machines FROM plants').fetchall()

now = datetime.now()
for i in range(12):
    d = now + relativedelta(months=i)
    month_year = d.strftime('%Y-%m')
    for plant in plants:
        plant_id = plant[0]
        machines = plant[1]
        # Calculate a reasonable capacity based on machines (e.g. 3000 units per machine per month)
        cap = machines * 3000
        
        # Check if exists
        exists = db.execute('SELECT id FROM plant_monthly_capacity WHERE plant_id=? AND month_year=?', (plant_id, month_year)).fetchone()
        if not exists:
            db.execute('''
                INSERT INTO plant_monthly_capacity (plant_id, month_year, total_capacity, used_capacity)
                VALUES (?, ?, ?, 0)
            ''', (plant_id, month_year, cap))
db.commit()
db.close()
print("Populated capacity table successfully.")
