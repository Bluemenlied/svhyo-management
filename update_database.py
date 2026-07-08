from app import app, db
from sqlalchemy import text

with app.app_context():
    # Drop and recreate the table with nullable=True
    db.session.execute(text("DROP TABLE IF EXISTS sport_transactions"))
    db.session.commit()
    db.create_all()
    print("✅ Table recreated with transaction_date nullable=True")