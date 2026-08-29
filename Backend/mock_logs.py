import sqlite3
from datetime import datetime, timedelta

def mock_daily_logs(order_id):
    db = sqlite3.connect('garment.db')
    
    # Check if order exists
    order = db.execute("SELECT bulk_order_quantity FROM bulk_orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        print(f"Order #{order_id} not found.")
        return
        
    alloc = db.execute("SELECT plant_id FROM order_plant_allocations WHERE bulk_order_id=?", (order_id,)).fetchone()
    if not alloc:
        print(f"No plant allocated for order #{order_id}.")
        return
        
    plant_id = alloc[0]
    start_date = datetime.now() - timedelta(days=10)
    
    # Insert 10 days of dummy production logs
    cum_qty = 0
    daily_output = 400
    
    for i in range(1, 11):
        log_date = (start_date + timedelta(days=i)).strftime('%Y-%m-%d')
        cum_qty += daily_output
        
        # Add some random breakdowns/shortages
        breakdowns = 1 if i % 3 == 0 else 0
        shortages = 1 if i % 4 == 0 else 0
        damage = 15 if i % 2 == 0 else 5
        
        db.execute('''
            INSERT OR IGNORE INTO daily_logs 
            (bulk_order_id, plant_id, log_date, working_day_no, plant_daily_output, daily_damage_qty, machine_breakdown_count, worker_shortage_count, cumulative_completed_qty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, plant_id, log_date, i, daily_output, damage, breakdowns, shortages, cum_qty))
        
    db.commit()
    db.close()
    print(f"Successfully added 10 days of dummy production logs for Order #{order_id}!")

if __name__ == "__main__":
    mock_daily_logs(6)
