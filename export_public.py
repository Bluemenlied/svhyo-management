# update_database.py
import sqlite3
import os

db_path = os.path.join('instance', 'svhyo.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Updating database schema...")

# Add category to sport_participants
try:
    cursor.execute("ALTER TABLE sport_participants ADD COLUMN category VARCHAR(50) DEFAULT 'General'")
    print("✓ Added category column to sport_participants")
except Exception as e:
    if "duplicate column name" in str(e).lower():
        print("✓ category column already exists")
    else:
        print(f"! {e}")

# Add event_type to sport_events
try:
    cursor.execute("ALTER TABLE sport_events ADD COLUMN event_type VARCHAR(50) DEFAULT 'Sports'")
    print("✓ Added event_type column to sport_events")
except Exception as e:
    if "duplicate column name" in str(e).lower():
        print("✓ event_type column already exists")
    else:
        print(f"! {e}")

# Add quota_contribution to transaction_type check if needed
try:
    # Check if quota_contribution values exist
    cursor.execute("SELECT DISTINCT transaction_type FROM sport_transactions WHERE transaction_type = 'quota_contribution'")
    if not cursor.fetchone():
        print("✓ quota_contribution transaction type is available")
except Exception as e:
    print(f"! {e}")

conn.commit()
conn.close()

print("\n" + "="*40)
print("Database update complete!")
print("="*40)