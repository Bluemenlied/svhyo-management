import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date
from functools import wraps
import pandas as pd
import json

# ============ FIX: Set timezone to Philippine Time ============
# Set the timezone environment variable
os.environ['TZ'] = 'Asia/Manila'

# Try to apply the timezone
try:
    import time
    time.tzset()
except AttributeError:
    # Windows doesn't support tzset, but we'll use a different method
    pass

# Alternative method for Windows: Create a custom timezone-aware now function
from datetime import datetime, timezone, timedelta

# Philippine Timezone (UTC+8)
PH_TIMEZONE = timezone(timedelta(hours=8))

def get_philippine_now():
    """Get current date and time in Philippine timezone"""
    return datetime.now(PH_TIMEZONE)

def get_philippine_today():
    """Get current date in Philippine timezone"""
    return get_philippine_now().date()

# ==============================================================

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'

# Use absolute path for database - THIS IS THE FIX
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'svhyo.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads/events'
app.config['LOGO_UPLOAD_FOLDER'] = 'static/uploads/logos'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Create directories
os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['LOGO_UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(basedir, 'static', 'uploads', 'events'), exist_ok=True)  # Add this line

# ==================== CACHE CONTROL ====================
@app.after_request
def add_cache_control(response):
    """Prevent caching of pages after login/logout"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# ==================== MODELS ====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    full_name = db.Column(db.String(100))
    email = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Officer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    position = db.Column(db.String(100), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    term_start = db.Column(db.Date)
    term_end = db.Column(db.Date)
    order_rank = db.Column(db.Integer)
    email = db.Column(db.String(120))
    contact = db.Column(db.String(20))
    is_current = db.Column(db.Boolean, default=True)
    photo = db.Column(db.String(200), nullable=True)

class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100))
    hs_no = db.Column(db.String(50))
    address = db.Column(db.String(200))
    contact_no = db.Column(db.String(20))
    birthday = db.Column(db.Date)
    age = db.Column(db.Integer)

    def calculate_age(self):
        if self.birthday:
            today = date.today()
            return today.year - self.birthday.year - ((today.month, today.day) < (self.birthday.month, self.birthday.day))
        return None

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    account = db.Column(db.String(50))
    description = db.Column(db.String(200))
    transaction_type = db.Column(db.String(20))
    amount = db.Column(db.Float, nullable=False)
    net_balance = db.Column(db.Float)
    category = db.Column(db.String(50))
    reference_no = db.Column(db.String(100))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))


# ==================== SPORTS EVENT MANAGEMENT MODELS ====================

class SportEvent(db.Model):
    __tablename__ = 'sport_events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    event_type = db.Column(db.String(50), default='Sports')
    sport_type = db.Column(db.String(100), nullable=True)
    event_date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200))
    court_fee = db.Column(db.Float, default=0)
    other_expenses = db.Column(db.Float, default=0)
    registration_fee = db.Column(db.Float, default=0)
    total_expenses = db.Column(db.Float, default=0)
    status = db.Column(db.String(50), default='upcoming')
    
    # NEW: Event type for quota tracking
    quota_type = db.Column(db.String(50), default='team')  # 'team', 'individual', 'both', 'none'
    brackets = db.Column(db.String(200), nullable=True)  # Comma separated brackets
    age_groups = db.Column(db.String(200), nullable=True)  # Comma separated age groups
    team_quota_target = db.Column(db.Float, default=0)  # Default team quota
    individual_quota_target = db.Column(db.Float, default=0)  # Default individual quota
    
    # NEW: Bracket quota mapping (JSON string)
    bracket_quotas = db.Column(db.Text, nullable=True)  # JSON: {"U12": 1000, "U15": 1500, "Open": 2000}
    
    # NEW: Expense tracking relationship
    expenses = db.relationship('EventExpense', backref='event', lazy=True, cascade='all, delete-orphan')
    
    # ========== EXISTING COLUMNS ==========
    completed_date = db.Column(db.DateTime, nullable=True)
    facebook_link = db.Column(db.String(500), nullable=True)
    instagram_link = db.Column(db.String(500), nullable=True)
    tiktok_link = db.Column(db.String(500), nullable=True)
    event_image = db.Column(db.String(500), nullable=True)
    completed_description = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    teams = db.relationship('SportTeam', backref='event', lazy=True, cascade='all, delete-orphan')
    participants = db.relationship('SportParticipant', backref='event', lazy=True, cascade='all, delete-orphan')
    transactions = db.relationship('SportTransaction', backref='event', lazy=True)
    
    def calculate_total_expenses(self):
        self.total_expenses = (self.court_fee or 0) + (self.other_expenses or 0)
        return self.total_expenses
    
    def get_bracket_quota(self, bracket):
        """Get team quota for a specific bracket"""
        if not bracket:
            return self.team_quota_target or 0
        
        if self.bracket_quotas:
            import json
            try:
                quotas = json.loads(self.bracket_quotas)
                return quotas.get(bracket, self.team_quota_target or 0)
            except:
                pass
        return self.team_quota_target or 0
    
    def get_individual_bracket_quota(self, bracket):
        """Get individual quota for a specific bracket"""
        if not bracket:
            return self.individual_quota_target or 0
        
        if self.bracket_quotas:
            import json
            try:
                quotas = json.loads(self.bracket_quotas)
                return quotas.get(bracket, self.individual_quota_target or 0)
            except:
                pass
        return self.individual_quota_target or 0
    
    def get_all_bracket_quotas(self):
        """Get all bracket quotas as a dictionary"""
        if self.bracket_quotas:
            import json
            try:
                return json.loads(self.bracket_quotas)
            except:
                pass
        return {}


class SportTeam(db.Model):
    __tablename__ = 'sport_teams'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('sport_events.id'), nullable=False)
    team_name = db.Column(db.String(100), nullable=False)
    captain_name = db.Column(db.String(100))
    contact_number = db.Column(db.String(20))
    registration_fee = db.Column(db.Float, default=0)
    is_paid = db.Column(db.Boolean, default=False)
    
    # NEW: Team quota tracking
    quota_target = db.Column(db.Float, default=0)
    quota_achieved = db.Column(db.Float, default=0)
    has_reached_quota = db.Column(db.Boolean, default=False)
    
    # NEW: Bracket/Age group
    bracket = db.Column(db.String(50), nullable=True)
    age_group = db.Column(db.String(50), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    members = db.relationship('SportParticipant', backref='team', lazy=True, cascade='all, delete-orphan')
    
    def update_quota_status(self):
        self.has_reached_quota = self.quota_achieved >= self.quota_target
        return self.has_reached_quota


class SportParticipant(db.Model):
    __tablename__ = 'sport_participants'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('sport_events.id'), nullable=False)
    team_id = db.Column(db.Integer, db.ForeignKey('sport_teams.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    
    # NEW: Individual quota tracking
    quota_target = db.Column(db.Float, default=0)
    quota_achieved = db.Column(db.Float, default=0)
    has_reached_quota = db.Column(db.Boolean, default=False)
    
    # NEW: Participant details
    age = db.Column(db.Integer, nullable=True)
    bracket = db.Column(db.String(50), nullable=True)
    age_group = db.Column(db.String(50), nullable=True)
    
    # NEW: Registration fee tracking
    registration_fee = db.Column(db.Float, default=0)
    amount_paid = db.Column(db.Float, default=0)
    is_paid = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def update_payment_status(self):
        self.is_paid = self.amount_paid >= self.registration_fee
        return self.is_paid
    
    def update_quota_status(self):
        self.has_reached_quota = self.quota_achieved >= self.quota_target
        return self.has_reached_quota

# ==================== NEW: EVENT EXPENSE MODEL ====================
class EventExpense(db.Model):
    __tablename__ = 'event_expenses'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('sport_events.id'), nullable=False)
    expense_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, default=datetime.utcnow)
    reference_no = db.Column(db.String(100))
    category = db.Column(db.String(100), nullable=True)
    deduct_from = db.Column(db.String(50), default='general')  # NEW: Track which fund source
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<EventExpense {self.expense_type} - {self.amount}>'


class SportTransaction(db.Model):
    __tablename__ = 'sport_transactions'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('sport_events.id'), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey('sport_teams.id'), nullable=True)
    participant_id = db.Column(db.Integer, db.ForeignKey('sport_participants.id'), nullable=True)
    transaction_type = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(200))
    description = db.Column(db.Text)
    transaction_date = db.Column(db.Date, nullable=True)  # Allow NULL
    reference_no = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    participant = db.relationship('SportParticipant', backref='transactions')
    team = db.relationship('SportTeam', backref='transactions')


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    image_path = db.Column(db.String(500))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class DriveLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

class Accomplishment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    accomplishment_date = db.Column(db.Date)
    submitted_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    file_path = db.Column(db.String(500))
    status = db.Column(db.String(50), default='pending')
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # NEW: Social Media Links
    facebook_link = db.Column(db.String(500), nullable=True)
    instagram_link = db.Column(db.String(500), nullable=True)
    tiktok_link = db.Column(db.String(500), nullable=True)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(200))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True)
    setting_value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

class PublicSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True)
    setting_value = db.Column(db.Text)
    setting_type = db.Column(db.String(50), default='text')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== CONTACT MESSAGE MODEL ====================

class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ContactMessage {self.name} - {self.created_at}>'

# ==================== DATABASE INITIALIZATION ====================
# This runs automatically when the app starts (works with gunicorn)
with app.app_context():
    db.create_all()
    print("✅ All database tables created/verified!")
    
    # Create or update admin user
    admin = User.query.filter_by(username='admin').first()
    if admin:
        # Update existing admin with new password
        admin.set_password('1214f143l')
        admin.role = 'System Administrator'
        admin.full_name = 'System Administrator'
        admin.email = 'admin@svhyo.com'
        db.session.commit()
        print("✅ Admin password updated to: 1214f143l")
    else:
        # Create new admin
        admin = User(
            username='admin',
            role='System Administrator',
            full_name='System Administrator',
            email='admin@svhyo.com'
        )
        admin.set_password('1214f143l')
        db.session.add(admin)
        db.session.commit()
        print("✅ Default admin user created - Username: admin, Password: 1214f143l")
    
    # Create default public settings if they don't exist
    if not PublicSetting.query.first():
        default_settings = [
            {'setting_key': 'site_name', 'setting_value': 'Sitio Verdant Hills Youth Organization'},
            {'setting_key': 'site_logo', 'setting_value': ''},
            {'setting_key': 'about_content', 'setting_value': 'Welcome to Sitio Verdant Hills Youth Organization. We are committed to serving our community and developing future leaders.'},
            {'setting_key': 'mission', 'setting_value': 'To empower the youth through leadership development, community service, and excellence.'},
            {'setting_key': 'vision', 'setting_value': 'A community of empowered youth leaders building a better future.'},
            {'setting_key': 'contact_email', 'setting_value': 'contact@svhyo.com'},
            {'setting_key': 'contact_phone', 'setting_value': '+63 912 345 6789'},
            {'setting_key': 'contact_address', 'setting_value': 'Sitio Verdant Hills, Brgy. Pasong Tamo, Quezon City'},
            {'setting_key': 'social_facebook', 'setting_value': ''},
            {'setting_key': 'social_tiktok', 'setting_value': ''},
            {'setting_key': 'social_instagram', 'setting_value': ''},
        ]
        for setting in default_settings:
            new_setting = PublicSetting(
                setting_key=setting['setting_key'],
                setting_value=setting['setting_value'],
                setting_type='text'
            )
            db.session.add(new_setting)
        db.session.commit()
        print("✅ Default public settings created!")
    else:
        print("✅ Public settings already exist!")

# ==================== AUTH & HELPERS ====================

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please login to access this page.', 'warning')
                return redirect(url_for('login'))
            if current_user.role not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_audit(action, details):
    db.session.add(AuditLog(
        user_id=current_user.id if current_user.is_authenticated else None,
        action=action, details=details, ip_address=request.remote_addr
    ))
    db.session.commit()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'jpg', 'jpeg', 'png', 'gif'}

def update_net_balances():
    running_balance = 0
    for trans in Transaction.query.order_by(Transaction.date, Transaction.id).all():
        running_balance += trans.amount if trans.transaction_type == 'income' else -trans.amount
        trans.net_balance = running_balance
    db.session.commit()

# ==================== AUTH ROUTES ====================

@app.route('/svhyo-admin-panel', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            log_audit('Login', f'User {user.username} logged in')
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html')

# ==================== ADD THIS NEW ROUTE ====================
@app.route('/clear-flash', methods=['POST'])
def clear_flash():
    """Clear all flash messages from the session"""
    from flask import get_flashed_messages
    get_flashed_messages()
    return '', 204

@app.route('/logout')
@login_required
def logout():
    log_audit('Logout', f'User {current_user.username} logged out')
    logout_user()
    session.clear()  # ← ADD THIS LINE
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/check-session')
def check_session():
    """Check if user is authenticated for back button prevention"""
    return jsonify({'authenticated': current_user.is_authenticated})

@app.route('/dashboard')
@login_required
def dashboard():
    # Get all data for accurate calculations
    sport_transactions = SportTransaction.query.all()
    regular_transactions = Transaction.query.all()
    event_expenses = EventExpense.query.all()
    
    total_fund = 0
    total_expenses = 0
    
    # 1. Calculate from SportTransactions (primary source)
    for trans in sport_transactions:
        if trans.transaction_type in ['donation', 'solicitation', 'registration_fee', 'quota_contribution']:
            total_fund += trans.amount
        elif trans.transaction_type == 'expense':
            total_expenses += trans.amount
    
    # 2. Calculate from Regular Transactions (only non-duplicate)
    for trans in regular_transactions:
        trans_desc = trans.description.lower() if trans.description else ''
        
        # Skip if it's a sport-related transaction (already counted)
        is_sport_related = False
        sport_keywords = ['payment from', 'quota payment', 'registration fee', 'chess', 'basketball', 'sports', 'tournament']
        for keyword in sport_keywords:
            if keyword in trans_desc:
                is_sport_related = True
                break
        
        if not is_sport_related:
            # Check for exact match with sport transactions
            for st in sport_transactions:
                if st.description and st.description.lower() == trans_desc and abs(st.amount - trans.amount) < 0.01:
                    is_sport_related = True
                    break
        
        if not is_sport_related:
            if trans.transaction_type == 'income':
                total_fund += trans.amount
            elif trans.transaction_type == 'expense':
                total_expenses += trans.amount
    
    # ========== FIX: DON'T RESET total_expenses ==========
    # Instead, ADD to the existing total_expenses from event expenses
    # 3. Calculate from EventExpense (additional expenses)
    for expense in event_expenses:
        total_expenses += expense.amount
    
    # 4. Add Seminar participant payments (that don't have SportTransactions)
    seminar_events = SportEvent.query.filter_by(event_type='Seminar').all()
    for event in seminar_events:
        for participant in event.participants:
            if participant.amount_paid and participant.amount_paid > 0:
                # Check if already has a SportTransaction
                existing_trans = SportTransaction.query.filter_by(
                    participant_id=participant.id,
                    transaction_type='registration_fee'
                ).first()
                if not existing_trans:
                    total_fund += participant.amount_paid
    
    # Net Balance
    net_balance = total_fund - total_expenses
    
    # ========== BIRTHDAY CELEBRANTS (FIXED WITH PH TIMEZONE) ==========
    # Use Philippine timezone for today's date
    from datetime import timezone, timedelta
    
    # Philippine Timezone (UTC+8)
    PH_TIMEZONE = timezone(timedelta(hours=8))
    today = datetime.now(PH_TIMEZONE).date()
    
    birthday_celebrants = []
    
    # Get all persons with birthdays
    all_persons = Person.query.filter(Person.birthday.isnot(None)).all()
    
    for person in all_persons:
        if person.birthday:
            # Check if month and day match today (Philippine time)
            if person.birthday.month == today.month and person.birthday.day == today.day:
                birthday_celebrants.append(person)
    
    # ========== CHART DATA ==========
    import calendar
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    monthly_income = [0] * 12
    monthly_expenses = [0] * 12
    
    # Process sport transactions for chart
    for trans in sport_transactions:
        if trans.transaction_date and trans.transaction_date.year == today.year:
            month_idx = trans.transaction_date.month - 1
            if trans.transaction_type in ['donation', 'solicitation', 'registration_fee', 'quota_contribution']:
                monthly_income[month_idx] += trans.amount
            elif trans.transaction_type == 'expense':
                monthly_expenses[month_idx] += trans.amount
    
    # Process regular transactions for chart (non-duplicate)
    for trans in regular_transactions:
        if trans.date and trans.date.year == today.year:
            month_idx = trans.date.month - 1
            trans_desc = trans.description.lower() if trans.description else ''
            is_sport_related = False
            for st in sport_transactions:
                if st.description and st.description.lower() == trans_desc and abs(st.amount - trans.amount) < 0.01:
                    is_sport_related = True
                    break
            if not is_sport_related:
                if trans.transaction_type == 'income':
                    monthly_income[month_idx] += trans.amount
                elif trans.transaction_type == 'expense':
                    monthly_expenses[month_idx] += trans.amount
    
    # Process event expenses for chart
    for expense in event_expenses:
        if expense.date and expense.date.year == today.year:
            month_idx = expense.date.month - 1
            monthly_expenses[month_idx] += expense.amount
    
    chart_data = {
        'labels': months,
        'income': monthly_income,
        'expenses': monthly_expenses
    }
    
    return render_template('dashboard.html',
        total_officers=Officer.query.filter_by(is_current=True).count(),
        total_members=Person.query.count(),
        total_fund=total_fund,
        total_expenses=total_expenses,
        net_balance=net_balance,
        birthday_celebrants=birthday_celebrants,
        chart_data=chart_data
    )

# ==================== ADMIN ROUTES (ALL MOVED TO /admin/ PREFIX) ====================

# Helper function for file uploads - MUST BE DEFINED BEFORE ROUTES THAT USE IT
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'jpg', 'jpeg', 'png'}

@app.route('/admin/officers')
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def admin_officers():
    return render_template('officers.html',
        current_officers=Officer.query.filter_by(is_current=True).order_by(Officer.order_rank).all(),
        previous_officers=Officer.query.filter_by(is_current=False).order_by(Officer.term_end.desc()).all()
    )

@app.route('/admin/officers/add', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def add_officer():
    try:
        db.session.add(Officer(
            position=request.form['position'],
            full_name=request.form['full_name'],
            term_start=datetime.strptime(request.form['term_start'], '%Y-%m-%d').date() if request.form['term_start'] else None,
            term_end=datetime.strptime(request.form['term_end'], '%Y-%m-%d').date() if request.form['term_end'] else None,
            order_rank=int(request.form['order_rank']) if request.form['order_rank'] else None,
            email=request.form['email'],
            contact=request.form['contact'],
            is_current=True
        ))
        db.session.commit()
        log_audit('Add Officer', f'Added officer')
        flash('Officer added successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('admin_officers'))

@app.route('/api/officer/<int:id>')
@login_required
def get_officer(id):
    officer = Officer.query.get_or_404(id)
    return jsonify({
        'id': officer.id,
        'position': officer.position,
        'full_name': officer.full_name,
        'term_start': officer.term_start.strftime('%Y-%m-%d') if officer.term_start else None,
        'term_end': officer.term_end.strftime('%Y-%m-%d') if officer.term_end else None,
        'order_rank': officer.order_rank,
        'email': officer.email,
        'contact': officer.contact,
        'photo': officer.photo if hasattr(officer, 'photo') else None
    })

@app.route('/api/officers/next-board-member')
@login_required
def get_next_board_member():
    officers = Officer.query.filter_by(is_current=True).all()
    
    # Get all board member numbers
    board_numbers = []
    for officer in officers:
        if officer.position and officer.position.startswith('Board Member'):
            try:
                num = int(officer.position.replace('Board Member', '').strip())
                board_numbers.append(num)
            except:
                pass
    
    # Find next board number
    if board_numbers:
        next_number = max(board_numbers) + 1
    else:
        next_number = 1
    
    # Get next order rank
    max_rank = max([o.order_rank for o in officers if o.order_rank] or [0])
    next_rank = max_rank + 1
    
    return jsonify({
        'next_board_number': next_number,
        'next_order_rank': next_rank,
        'next_position': f'Board Member {next_number}'
    })

@app.route('/api/officers/check-name', methods=['POST'])
@login_required
def check_officer_name():
    data = request.get_json()
    full_name = data.get('full_name', '').strip()
    
    # Check if name exists in current officers
    existing = Officer.query.filter(
        Officer.is_current == True,
        Officer.full_name.ilike(full_name)
    ).first()
    
    return jsonify({
        'exists': existing is not None,
        'message': f'Officer with name "{full_name}" already exists!' if existing else None
    })

@app.route('/api/officers/next-order-rank')
@login_required
def get_next_order_rank():
    officers = Officer.query.filter_by(is_current=True).all()
    if officers:
        max_rank = max([o.order_rank for o in officers if o.order_rank] or [0])
        next_rank = max_rank + 1
    else:
        next_rank = 1
    return jsonify({'next_order_rank': next_rank})

# Working AJAX update route
@app.route('/admin/officers/update/<int:id>', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def update_officer(id):
    officer = Officer.query.get_or_404(id)
    try:
        officer.position = request.form['position']
        officer.full_name = request.form['full_name']
        officer.term_start = datetime.strptime(request.form['term_start'], '%Y-%m-%d').date() if request.form['term_start'] else None
        officer.term_end = datetime.strptime(request.form['term_end'], '%Y-%m-%d').date() if request.form['term_end'] else None
        officer.order_rank = int(request.form['order_rank']) if request.form['order_rank'] else None
        officer.email = request.form['email']
        officer.contact = request.form['contact']
        db.session.commit()
        log_audit('Update Officer', f'Updated officer: {officer.full_name}')
        
        # Check if AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Officer updated successfully!'})
        
        flash('Officer updated successfully!', 'success')
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)})
        flash(f'Error updating officer: {str(e)}', 'danger')
    
    return redirect(url_for('admin_officers'))

# ==================== OFFICER PHOTO UPLOAD ROUTES ====================

@app.route('/admin/officers/upload-photo/<int:id>', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def upload_officer_photo(id):
    officer = Officer.query.get_or_404(id)
    
    if 'photo' not in request.files:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'No file selected'})
        flash('No file selected', 'danger')
        return redirect(url_for('admin_officers'))
    
    file = request.files['photo']
    if file.filename == '':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'No file selected'})
        flash('No file selected', 'danger')
        return redirect(url_for('admin_officers'))
    
    if file and allowed_file(file.filename):
        import os
        from datetime import datetime
        
        # Create directory if not exists
        upload_dir = os.path.join('static', 'uploads', 'officers')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Generate unique filename
        extension = file.filename.rsplit('.', 1)[1].lower()
        filename = f"officer_{id}_{int(datetime.now().timestamp())}.{extension}"
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        
        # Delete old photo if exists
        if hasattr(officer, 'photo') and officer.photo:
            old_path = os.path.join(upload_dir, officer.photo)
            if os.path.exists(old_path):
                os.remove(old_path)
        
        officer.photo = filename
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'filename': filename})
        
        flash('Photo uploaded successfully!', 'success')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Invalid file type. Please upload JPG or PNG.'})
        flash('Invalid file type. Please upload JPG or PNG.', 'danger')
    
    return redirect(url_for('admin_officers'))

@app.route('/admin/officers/delete-photo/<int:id>', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def delete_officer_photo(id):
    officer = Officer.query.get_or_404(id)
    
    import os
    if hasattr(officer, 'photo') and officer.photo:
        upload_dir = os.path.join('static', 'uploads', 'officers')
        file_path = os.path.join(upload_dir, officer.photo)
        if os.path.exists(file_path):
            os.remove(file_path)
        officer.photo = None
        db.session.commit()
        log_audit('Delete Photo', f'Deleted photo for officer: {officer.full_name}')
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'No photo to delete'})

# ==================== OFFICER DELETE ROUTES ====================

@app.route('/admin/officers/delete/<int:id>')
@login_required
@role_required('President', 'System Administrator')
def delete_officer(id):
    officer = Officer.query.get_or_404(id)
    
    # Delete associated photo if exists
    import os
    if hasattr(officer, 'photo') and officer.photo:
        upload_dir = os.path.join('static', 'uploads', 'officers')
        file_path = os.path.join(upload_dir, officer.photo)
        if os.path.exists(file_path):
            os.remove(file_path)
    
    db.session.delete(officer)
    db.session.commit()
    log_audit('Delete Officer', f'Deleted officer: {officer.full_name}')
    flash('Officer deleted successfully!', 'success')
    return redirect(url_for('admin_officers'))

@app.route('/admin/officers/upload', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def upload_officers():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('admin_officers'))
    if file and file.filename.endswith(('.xlsx', '.xls')):
        try:
            df = pd.read_excel(file)
            for _, row in df.iterrows():
                db.session.add(Officer(
                    position=row['position'],
                    full_name=row['full_name'],
                    term_start=pd.to_datetime(row['term_start']).date() if pd.notna(row['term_start']) else None,
                    term_end=pd.to_datetime(row['term_end']).date() if pd.notna(row['term_end']) else None,
                    order_rank=int(row['order_rank']) if pd.notna(row['order_rank']) else None,
                    email=row['email'] if pd.notna(row['email']) else '',
                    contact=str(row['contact']) if pd.notna(row['contact']) else '',
                    is_current=True
                ))
            db.session.commit()
            flash(f'Successfully uploaded {len(df)} officers!', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    else:
        flash('Please upload an Excel file (.xlsx or .xls)', 'danger')
    return redirect(url_for('admin_officers'))

@app.route('/admin/officers/bulk-delete', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def bulk_delete_officers():
    try:
        import json
        ids = json.loads(request.form.get('ids', '[]'))
        
        if not ids:
            flash('No items selected for deletion.', 'warning')
            return redirect(url_for('admin_officers'))
        
        # Delete associated photos first
        import os
        officers_to_delete = Officer.query.filter(Officer.id.in_(ids)).all()
        for officer in officers_to_delete:
            if hasattr(officer, 'photo') and officer.photo:
                upload_dir = os.path.join('static', 'uploads', 'officers')
                file_path = os.path.join(upload_dir, officer.photo)
                if os.path.exists(file_path):
                    os.remove(file_path)
        
        # Delete all selected officers
        deleted_count = Officer.query.filter(Officer.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        
        # Log the action
        log_audit('Bulk Delete Officers', f'Deleted {deleted_count} officers')
        
        flash(f'Successfully deleted {deleted_count} officer(s).', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting records: {str(e)}', 'danger')
    
    return redirect(url_for('admin_officers'))

# ==================== DIRECTORY (ADMIN) ====================

@app.route('/admin/directory')
@login_required
def directory():
    return render_template('directory.html', persons=Person.query.order_by(Person.name).all())

@app.route('/admin/directory/add', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'Treasurer', 'System Administrator')
def add_person():
    try:
        birthday = datetime.strptime(request.form['birthday'], '%Y-%m-%d').date() if request.form['birthday'] else None
        person = Person(
            name=request.form['name'],
            position=request.form['position'],
            hs_no=request.form['hs_no'],
            address=request.form['address'],
            contact_no=request.form['contact_no'],
            birthday=birthday
        )
        person.age = person.calculate_age()
        db.session.add(person)
        db.session.commit()
        flash('Person added successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('directory'))

@app.route('/api/person/<int:id>')
@login_required
def get_person(id):
    person = Person.query.get_or_404(id)
    return jsonify({
        'id': person.id,
        'name': person.name,
        'position': person.position,
        'hs_no': person.hs_no,
        'address': person.address,
        'contact_no': person.contact_no,
        'birthday': person.birthday.strftime('%Y-%m-%d') if person.birthday else None,
        'age': person.age
    })

@app.route('/admin/directory/update/<int:id>', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def update_person(id):
    person = Person.query.get_or_404(id)
    try:
        person.name = request.form['name']
        person.position = request.form['position']
        person.hs_no = request.form['hs_no']
        person.address = request.form['address']
        person.contact_no = request.form['contact_no']
        person.birthday = datetime.strptime(request.form['birthday'], '%Y-%m-%d').date() if request.form['birthday'] else None
        person.age = person.calculate_age()
        db.session.commit()
        flash('Person updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating person: {str(e)}', 'danger')
    return redirect(url_for('directory'))

@app.route('/admin/directory/delete/<int:id>')
@login_required
@role_required('President', 'System Administrator')
def delete_person(id):
    person = Person.query.get_or_404(id)
    db.session.delete(person)
    db.session.commit()
    flash('Person deleted successfully!', 'success')
    return redirect(url_for('directory'))

@app.route('/admin/directory/upload', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def upload_directory():
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('directory'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('directory'))
    if file and (file.filename.endswith('.xlsx') or file.filename.endswith('.xls') or file.filename.endswith('.csv')):
        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            for _, row in df.iterrows():
                birthday = pd.to_datetime(row['Birthday']).date() if pd.notna(row['Birthday']) else None
                person = Person(
                    name=row['Name'],
                    position=row['Position'] if pd.notna(row['Position']) else '',
                    hs_no=str(row['HS NO']) if pd.notna(row['HS NO']) else '',
                    address=row['Address'] if pd.notna(row['Address']) else '',
                    contact_no=str(row['Contact No.']) if pd.notna(row['Contact No.']) else '',
                    birthday=birthday
                )
                person.age = person.calculate_age()
                db.session.add(person)
            db.session.commit()
            flash(f'Successfully uploaded {len(df)} persons!', 'success')
        except Exception as e:
            flash(f'Error uploading file: {str(e)}', 'danger')
    else:
        flash('Please upload an Excel or CSV file', 'danger')
    return redirect(url_for('directory'))

@app.route('/admin/directory/bulk-delete', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def bulk_delete_persons():
    try:
        import json
        ids = json.loads(request.form.get('ids', '[]'))
        
        if not ids:
            flash('No items selected for deletion.', 'warning')
            return redirect(url_for('directory'))
        
        # Delete all selected persons
        deleted_count = Person.query.filter(Person.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        
        # Log the action
        log_audit('Bulk Delete Persons', f'Deleted {deleted_count} persons')
        
        flash(f'Successfully deleted {deleted_count} person(s).', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting records: {str(e)}', 'danger')
    
    return redirect(url_for('directory'))

# ==================== FINANCES (ADMIN) - ENHANCED WITH SPORTS EVENTS ====================
def update_net_balances():
    """Update net balances for all transactions"""
    running_balance = 0
    for trans in Transaction.query.order_by(Transaction.date, Transaction.id).all():
        if trans.transaction_type == 'income':
            running_balance += trans.amount
        else:
            running_balance -= trans.amount
        trans.net_balance = running_balance
    db.session.commit()

@app.route('/admin/finances')
@login_required
def finances():
    # Get active event (first upcoming or ongoing event)
    active_event = SportEvent.query.filter(
        SportEvent.status.in_(['upcoming', 'ongoing'])
    ).first()
    
    # Get all events for dropdown
    all_events = SportEvent.query.all()
    
    # Calculate fund sources
    fund_sources = {
        'donations': 0,
        'donation_count': 0,
        'solicitation': 0,
        'solicitation_count': 0,
        'registration_fees': 0,
        'registration_count': 0,
        'other_income': 0,
        'other_income_count': 0
    }
    
    # Get all data
    sport_transactions = SportTransaction.query.all()
    regular_transactions = Transaction.query.all()
    event_expenses = EventExpense.query.all()
    
    all_transactions = []
    total_fund = 0
    total_expenses = 0
    
    # ========== 1. Calculate Income from SportTransactions ==========
    for trans in sport_transactions:
        all_transactions.append(trans)
        if trans.transaction_type in ['donation', 'solicitation', 'registration_fee', 'quota_contribution']:
            total_fund += trans.amount
            if trans.transaction_type == 'donation':
                fund_sources['donations'] += trans.amount
                fund_sources['donation_count'] += 1
            elif trans.transaction_type == 'solicitation':
                fund_sources['solicitation'] += trans.amount
                fund_sources['solicitation_count'] += 1
            elif trans.transaction_type == 'registration_fee':
                fund_sources['registration_fees'] += trans.amount
                fund_sources['registration_count'] += 1
            elif trans.transaction_type == 'quota_contribution':
                fund_sources['other_income'] += trans.amount
                fund_sources['other_income_count'] += 1
        elif trans.transaction_type == 'expense':
            # Count expenses from SportTransactions
            total_expenses += trans.amount
            # Still add to all_transactions for display
            all_transactions.append(trans)
    
    # ========== 2. Calculate Income from Regular Transactions (ONLY non-sport) ==========
    for trans in regular_transactions:
        trans_desc = trans.description.lower() if trans.description else ''
        
        # Skip if it's a sport-related transaction (already counted via SportTransaction)
        is_sport_related = False
        sport_keywords = ['payment from', 'quota payment', 'registration fee', 'chess', 'basketball', 'sports', 'tournament']
        for keyword in sport_keywords:
            if keyword in trans_desc:
                is_sport_related = True
                break
        
        # Check if there's a matching SportTransaction
        if not is_sport_related:
            for st in sport_transactions:
                if st.description and st.description.lower() == trans_desc and abs(st.amount - trans.amount) < 0.01:
                    is_sport_related = True
                    break
        
        # Add to all_transactions
        all_transactions.append(trans)
        
        # ========== FIX: Count income and expenses from regular transactions ==========
        if not is_sport_related:
            if trans.transaction_type == 'income':
                total_fund += trans.amount
                if trans.category:
                    cat_lower = trans.category.lower()
                    if 'registration' in cat_lower or 'fee' in cat_lower:
                        fund_sources['registration_fees'] += trans.amount
                        fund_sources['registration_count'] += 1
                    elif 'donation' in cat_lower:
                        fund_sources['donations'] += trans.amount
                        fund_sources['donation_count'] += 1
                    elif 'solicitation' in cat_lower:
                        fund_sources['solicitation'] += trans.amount
                        fund_sources['solicitation_count'] += 1
                    else:
                        fund_sources['other_income'] += trans.amount
                        fund_sources['other_income_count'] += 1
                else:
                    fund_sources['other_income'] += trans.amount
                    fund_sources['other_income_count'] += 1
            elif trans.transaction_type == 'expense':
                # ========== FIX: Count expenses from regular transactions ==========
                total_expenses += trans.amount
                print(f"Expense from regular transaction: ₱{trans.amount:,.2f} - {trans.description}")
    
    # ========== 3. Add Expenses from EventExpense (additional expenses) ==========
    for expense in event_expenses:
        total_expenses += expense.amount
        all_transactions.append({
            'transaction_date': expense.date,
            'transaction_type': 'expense',
            'amount': expense.amount,
            'source': expense.expense_type,
            'description': f"{expense.expense_type} - {expense.description}",
            'date': expense.date,
            'is_expense': True,
            'id': expense.id,
            'is_event_expense': True
        })
    
    # ========== 4. Calculate Seminar Participant Payments ==========
    seminar_events = SportEvent.query.filter_by(event_type='Seminar').all()
    for event in seminar_events:
        for participant in event.participants:
            if participant.amount_paid and participant.amount_paid > 0:
                existing_trans = SportTransaction.query.filter_by(
                    participant_id=participant.id,
                    transaction_type='registration_fee'
                ).first()
                
                if not existing_trans:
                    total_fund += participant.amount_paid
                    fund_sources['registration_fees'] += participant.amount_paid
                    fund_sources['registration_count'] += 1
                    
                    new_trans = SportTransaction(
                        event_id=participant.event_id,
                        participant_id=participant.id,
                        transaction_type='registration_fee',
                        amount=participant.amount_paid,
                        source='Payment',
                        description=f'Payment from {participant.name}',
                        transaction_date=datetime.now().date(),
                        created_by=1
                    )
                    db.session.add(new_trans)
                    db.session.commit()
    
    # ========== 5. Calculate Event Fund (Collected - Expenses) ==========
    event_fund = 0
    if active_event:
        # Calculate collected from SportTransactions
        event_transactions = SportTransaction.query.filter_by(event_id=active_event.id).all()
        for t in event_transactions:
            if t.transaction_type in ['donation', 'solicitation', 'registration_fee', 'quota_contribution']:
                event_fund += t.amount
        
        # For Seminar events, add participant amount_paid
        if active_event.event_type == 'Seminar':
            for p in active_event.participants:
                if p.amount_paid and p.amount_paid > 0:
                    existing_trans = SportTransaction.query.filter_by(
                        participant_id=p.id,
                        transaction_type='registration_fee'
                    ).first()
                    if not existing_trans:
                        event_fund += p.amount_paid
        
        # Subtract expenses for this event
        event_expenses_for_event = EventExpense.query.filter_by(event_id=active_event.id).all()
        for e in event_expenses_for_event:
            event_fund -= e.amount
    
    # Sort all transactions by date
    def get_date(obj):
        if hasattr(obj, 'transaction_date'):
            return obj.transaction_date or datetime.now().date()
        if isinstance(obj, dict) and 'date' in obj:
            return obj['date'] or datetime.now().date()
        if hasattr(obj, 'date'):
            return obj.date or datetime.now().date()
        return datetime.now().date()
    
    all_transactions.sort(key=get_date, reverse=True)
    
    # ========== 6. QUOTA STATISTICS ==========
    sports_events = SportEvent.query.filter_by(event_type='Sports').all()
    all_sports_team_members = []
    for event in sports_events:
        for team in event.teams:
            for member in team.members:
                all_sports_team_members.append(member)
    
    total_members = len(all_sports_team_members)
    reached_members = len([m for m in all_sports_team_members if m.has_reached_quota])
    
    quota_stats = {
        'total': total_members,
        'reached': reached_members
    }
    
    net_balance = total_fund - total_expenses
    
    print(f"💰 Total Fund: ₱{total_fund:,.2f}")
    print(f"💸 Total Expenses: ₱{total_expenses:,.2f}")
    print(f"📊 Net Balance: ₱{net_balance:,.2f}")
    
    return render_template('finances.html',
        total_fund=total_fund,
        total_expenses=total_expenses,
        net_balance=net_balance,
        all_transactions=all_transactions,
        active_event=active_event,
        event_fund=event_fund,
        fund_sources=fund_sources,
        quota_stats=quota_stats,
        all_events=all_events,
        datetime=datetime
    )

@app.route('/admin/finances/add', methods=['POST'])
@login_required
@role_required('President', 'Treasurer', 'System Administrator')
def add_transaction():
    try:
        transaction = Transaction(
            date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
            account=request.form.get('account', 'Cash'),
            description=request.form['description'],
            transaction_type=request.form['transaction_type'],
            amount=float(request.form['amount']),
            category=request.form.get('category', ''),
            reference_no=request.form.get('reference_no', ''),
            created_by=current_user.id
        )
        last = Transaction.query.order_by(Transaction.date.desc()).first()
        if last:
            transaction.net_balance = last.net_balance + (transaction.amount if transaction.transaction_type == 'income' else -transaction.amount)
        else:
            transaction.net_balance = transaction.amount if transaction.transaction_type == 'income' else -transaction.amount
        db.session.add(transaction)
        db.session.commit()
        update_net_balances()
        flash('Transaction added successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))

@app.route('/admin/finances/delete/<int:id>')
@login_required
@role_required('President', 'Treasurer', 'System Administrator')
def delete_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    try:
        # Only delete the transaction record, don't update net balances
        db.session.delete(transaction)
        db.session.commit()
        # DO NOT call update_net_balances() here - this preserves the fund balance
        flash('Transaction deleted from history successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))

@app.route('/admin/finances/clear-history', methods=['POST'])
@login_required
@role_required('President', 'Treasurer', 'System Administrator')
def clear_transaction_history():
    try:
        # Get the current net balance from the last transaction
        last_transaction = Transaction.query.order_by(Transaction.date.desc()).first()
        current_balance = last_transaction.net_balance if last_transaction else 0
        
        # Delete ALL regular transactions
        Transaction.query.delete()
        db.session.commit()
        
        # If there was a balance, create an opening balance entry
        if current_balance != 0:
            opening_balance = Transaction(
                date=datetime.now().date(),
                description='Opening balance after history clear',
                category='Opening Balance',
                transaction_type='income' if current_balance > 0 else 'expense',
                amount=abs(current_balance),
                net_balance=current_balance,
                created_by=current_user.id
            )
            db.session.add(opening_balance)
            db.session.commit()
            flash('✅ All transaction history cleared! Opening balance created.', 'success')
        else:
            # If balance is 0, ensure net_balances are correct
            update_net_balances()
            flash('✅ All transaction history cleared! Balance is zero.', 'success')
        
        # Check if AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'All transaction history cleared! Fund balance remains intact.'})
            
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': str(e)})
        flash(f'Error clearing history: {str(e)}', 'danger')
    
    return redirect(url_for('finances'))

# ==================== FINANCE TRANSACTION EDIT ROUTES ====================

@app.route('/api/transaction/<int:id>')
@login_required
def get_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    return jsonify({
        'id': transaction.id,
        'date': transaction.date.strftime('%Y-%m-%d'),
        'transaction_type': transaction.transaction_type,
        'amount': transaction.amount,
        'account': transaction.account,
        'description': transaction.description,
        'reference_no': transaction.reference_no,
        'category': transaction.category
    })

@app.route('/admin/finances/update/<int:id>', methods=['POST'])
@login_required
@role_required('President', 'Treasurer', 'System Administrator')
def update_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    try:
        transaction.date = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        transaction.account = request.form.get('account', 'Cash')
        transaction.description = request.form['description']
        transaction.transaction_type = request.form['transaction_type']
        transaction.amount = float(request.form['amount'])
        transaction.category = request.form.get('category', '')
        transaction.reference_no = request.form.get('reference_no', '')
        db.session.commit()
        update_net_balances()
        flash('Transaction updated successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))

# ==================== PARTICIPANT TRANSACTION ROUTES ====================

@app.route('/api/participant/<int:participant_id>/transactions')
@login_required
def get_participant_transactions(participant_id):
    participant = SportParticipant.query.get_or_404(participant_id)
    transactions = SportTransaction.query.filter_by(participant_id=participant_id).all()
    return jsonify({
        'transactions': [{
            'id': t.id,
            'amount': t.amount,
            'source': t.source,
            'transaction_date': t.transaction_date.strftime('%Y-%m-%d') if t.transaction_date else None,
            'description': t.description,
            'transaction_type': t.transaction_type
        } for t in transactions]
    })

@app.route('/api/participant/<int:id>')
@login_required
def get_participant_api(id):
    participant = SportParticipant.query.get_or_404(id)
    return jsonify({
        'id': participant.id,
        'name': participant.name,
        'quota_target': participant.quota_target,
        'quota_achieved': participant.quota_achieved,
        'has_reached_quota': participant.has_reached_quota,
        'team_id': participant.team_id,
        'team_name': participant.team.team_name if participant.team else None,
        'age': participant.age,
        'bracket': participant.bracket,
        'age_group': participant.age_group
    })

@app.route('/admin/transactions/update/<int:id>', methods=['POST'])
@login_required
@role_required('President', 'Treasurer', 'System Administrator')
def update_sport_transaction(id):
    transaction = SportTransaction.query.get_or_404(id)
    try:
        old_amount = transaction.amount
        old_description = transaction.description
        
        transaction.amount = float(request.form['amount'])
        transaction.source = request.form['source']
        transaction.transaction_date = datetime.strptime(request.form['transaction_date'], '%Y-%m-%d').date()
        transaction.description = request.form.get('description', '')
        db.session.commit()
        
        # Update participant quota
        if transaction.participant:
            # Recalculate quota achieved from all transactions
            total_achieved = sum(t.amount for t in SportTransaction.query.filter_by(participant_id=transaction.participant_id).all())
            transaction.participant.quota_achieved = total_achieved
            transaction.participant.update_quota_status()
            
            # Also update the regular transaction record
            regular_trans = Transaction.query.filter_by(
                description=old_description,
                amount=old_amount
            ).first()
            if regular_trans:
                regular_trans.amount = transaction.amount
                regular_trans.date = transaction.transaction_date
                regular_trans.description = transaction.description
                regular_trans.category = transaction.transaction_type
        
        db.session.commit()
        update_net_balances()
        
        if transaction.participant and transaction.participant.has_reached_quota:
            flash(f'🎉 {transaction.participant.name} has reached their quota target!', 'success')
        else:
            flash('Transaction updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))

@app.route('/admin/participants/delete/<int:id>')
@login_required
@role_required('President', 'System Administrator')
def delete_participant(id):
    participant = SportParticipant.query.get_or_404(id)
    try:
        # Delete all associated transactions first
        SportTransaction.query.filter_by(participant_id=id).delete()
        db.session.delete(participant)
        db.session.commit()
        flash(f'Participant "{participant.name}" deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))

@app.route('/admin/participants/edit/<int:id>', methods=['POST'])
@login_required
@role_required('President', 'Treasurer', 'System Administrator')
def edit_participant(id):
    participant = SportParticipant.query.get_or_404(id)
    try:
        participant.name = request.form['name']
        participant.quota_target = float(request.form['quota_target']) if request.form['quota_target'] else 0
        db.session.commit()
        flash(f'Participant "{participant.name}" updated successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))

# ==================== SPORTS EVENT MANAGEMENT ROUTES ====================

@app.route('/admin/sports/event/add', methods=['POST'])
@login_required
@role_required('President', 'Treasurer', 'System Administrator')
def add_sport_event():
    try:
        sport_type_value = request.form.get('sport_type', 'Seminar')
        registration_fee = float(request.form.get('registration_fee', 0))
        
        # ===== FIX: For Seminars, determine quota type based on registration fee =====
        if sport_type_value == 'Seminar':
            # If there's a registration fee → Individual quota, otherwise → None
            if registration_fee > 0:
                quota_type = 'individual'
                individual_quota_target = registration_fee
            else:
                quota_type = 'none'
                individual_quota_target = 0
            team_quota_target = 0
            brackets = 'N/A'
            age_groups = ''
            bracket_quotas = {}
            bracket_quotas_json_final = None
        else:
            # For Sports, use the form values
            quota_type = request.form.get('quota_type', 'team')
            team_quota_target = float(request.form.get('team_quota_target', 0))
            individual_quota_target = float(request.form.get('individual_quota_target', 0))
            brackets = request.form.get('brackets', 'Open')
            age_groups = request.form.get('age_groups', '')
            
            # IMPORTANT FIX: Get bracket_quotas from the JSON sent by frontend
            bracket_quotas_json = request.form.get('bracket_quotas', '{}')
            bracket_quotas = {}
            
            try:
                if bracket_quotas_json and bracket_quotas_json != '{}':
                    bracket_quotas = json.loads(bracket_quotas_json)
                    print(f"✅ Loaded bracket_quotas from JSON: {bracket_quotas}")
                else:
                    # Fallback: Try to get from individual quota fields
                    bracket_list = [b.strip() for b in brackets.split(',') if b.strip()]
                    for bracket in bracket_list:
                        quota_key = f'quota_{bracket.replace(" ", "_")}'
                        quota_value = float(request.form.get(quota_key, team_quota_target))
                        bracket_quotas[bracket] = quota_value
                    print(f"⚠️ Built bracket_quotas from fallback: {bracket_quotas}")
            except Exception as e:
                print(f"❌ Error parsing bracket_quotas: {e}")
                bracket_quotas = {}
            
            # If individual_quota_target is 0 but we have bracket quotas, use the first bracket's quota
            if individual_quota_target == 0 and bracket_quotas:
                first_quota = list(bracket_quotas.values())[0] if bracket_quotas.values() else 0
                individual_quota_target = first_quota
                print(f"📊 Set individual_quota_target to: {individual_quota_target}")
            
            # Convert to JSON for storage
            bracket_quotas_json_final = json.dumps(bracket_quotas) if bracket_quotas else None
        
        event = SportEvent(
            name=request.form['name'],
            event_type=sport_type_value,
            sport_type=sport_type_value,
            event_date=datetime.strptime(request.form['event_date'], '%Y-%m-%d').date(),
            location=request.form.get('location', ''),
            court_fee=float(request.form.get('court_fee', 0)),
            other_expenses=float(request.form.get('other_expenses', 0)),
            registration_fee=registration_fee,
            quota_type=quota_type,
            team_quota_target=team_quota_target,
            individual_quota_target=individual_quota_target,
            brackets=brackets,
            age_groups=age_groups,
            bracket_quotas=bracket_quotas_json_final,
            created_by=current_user.id
        )
        event.calculate_total_expenses()
        db.session.add(event)
        db.session.commit()
        
        # Add venue and other expenses as transactions (only for Sports)
        if sport_type_value == 'Sports':
            if event.court_fee > 0:
                expense_trans = Transaction(
                    date=datetime.now().date(),
                    description=f"{event.name} - Venue Fee",
                    category=f"Event - {event.event_type}",
                    transaction_type='expense',
                    amount=event.court_fee,
                    net_balance=0,
                    created_by=current_user.id
                )
                db.session.add(expense_trans)
            if event.other_expenses > 0:
                expense_trans2 = Transaction(
                    date=datetime.now().date(),
                    description=f"{event.name} - Other Expenses",
                    category=f"Event - {event.event_type}",
                    transaction_type='expense',
                    amount=event.other_expenses,
                    net_balance=0,
                    created_by=current_user.id
                )
                db.session.add(expense_trans2)
        
        db.session.commit()
        update_net_balances()
        
        print(f"✅ Event created with quota_type: {quota_type}, registration_fee: {registration_fee}")
        
        return jsonify({'success': True, 'message': f'✅ Event "{event.name}" created successfully!'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/sports/event/<int:id>/add-team', methods=['POST'])
@login_required
@role_required('President', 'Treasurer', 'System Administrator')
def add_sport_team(id):
    event = SportEvent.query.get_or_404(id)
    try:
        team_name = request.form.get('team_name', '').strip()
        captain_name = request.form.get('captain_name', '').strip()
        contact_number = request.form.get('contact_number', '')
        registration_fee = float(request.form.get('registration_fee', 0))
        bracket = request.form.get('bracket', 'Open')
        
        if not team_name or not captain_name:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Team name and captain name are required!'})
            flash('Team name and captain name are required!', 'danger')
            return redirect(url_for('finances'))
        
        # Get quota for this bracket from event
        quota_target = event.get_bracket_quota(bracket)
        
        team = SportTeam(
            event_id=id,
            team_name=team_name,
            captain_name=captain_name,
            contact_number=contact_number,
            registration_fee=registration_fee,
            quota_target=quota_target,
            bracket=bracket,
            age_group=request.form.get('age_group', '')
        )
        db.session.add(team)
        db.session.commit()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': f'Team "{team_name}" added successfully! Quota: ₱{quota_target:,.2f}'})
        
        flash(f'Team "{team.team_name}" added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': str(e)})
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))

@app.route('/admin/sports/event/<int:id>/add-participant', methods=['POST'])
@login_required
@role_required('President', 'Treasurer','System Administrator')
def add_sport_participant(id):
    event = SportEvent.query.get_or_404(id)
    try:
        team_id = request.form.get('team_id')
        bracket = request.form.get('bracket', 'Open')
        
        # Get individual quota for this bracket
        quota_target = event.get_individual_bracket_quota(bracket)
        
        # If quota_target is 0, try to get from bracket_quotas directly
        if quota_target == 0 and event.bracket_quotas:
            import json
            try:
                quotas = json.loads(event.bracket_quotas)
                quota_target = quotas.get(bracket, 0)
            except:
                pass
        
        participant = SportParticipant(
            event_id=id,
            team_id=int(team_id) if team_id and team_id != '0' else None,
            name=request.form['name'],
            quota_target=quota_target,
            age=int(request.form.get('age')) if request.form.get('age') else None,
            bracket=bracket,
            age_group=request.form.get('age_group', ''),
            registration_fee=event.registration_fee
        )
        db.session.add(participant)
        db.session.commit()
        flash(f'Participant "{participant.name}" added successfully! Quota: ₱{quota_target:,.2f}', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"Error: {str(e)}")
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))

# ==================== ADD MEMBER TO TEAM ====================
@app.route('/admin/sports/event/<int:id>/add-team-member', methods=['POST'])
@login_required
def add_sport_team_member(id):
    try:
        team_id = request.form.get('team_id')
        name = request.form.get('name', '').strip()
        
        if not name:
            return jsonify({'success': False, 'message': 'Member name is required!'})
        
        event = SportEvent.query.get(id)
        participant = SportParticipant(
            event_id=id,
            team_id=team_id,
            name=name,
            quota_target=event.individual_quota_target if event else 0,
            registration_fee=event.registration_fee if event else 0,
            amount_paid=0,
            is_paid=False,
            quota_achieved=0,
            has_reached_quota=False
        )
        db.session.add(participant)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Member "{name}" added to team successfully!'})
    except Exception as e:
        db.session.rollback()
        print(f"Error adding member: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

# ==================== RECORD TEAM QUOTA PAYMENT ====================
@app.route('/admin/finances/record-team-quota-payment', methods=['POST'])
@login_required
def record_team_quota_payment():
    try:
        team_id = request.form.get('team_id')
        amount = float(request.form.get('amount'))
        payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date()
        description = request.form.get('description', 'Quota contribution')
        
        if not team_id:
            return jsonify({'success': False, 'message': 'Team ID is required'})
        
        if amount <= 0:
            return jsonify({'success': False, 'message': 'Amount must be greater than 0'})
        
        team = SportTeam.query.get_or_404(int(team_id))
        
        # Calculate current quota achieved
        existing_payments = SportTransaction.query.filter_by(team_id=team_id, transaction_type='quota_contribution').all()
        current_achieved = sum(p.amount for p in existing_payments)
        
        # Check if amount exceeds remaining quota
        remaining = team.quota_target - current_achieved
        if amount > remaining:
            return jsonify({'success': False, 'message': f'Amount exceeds remaining quota of ₱{remaining:,.2f}'})
        
        # Create sport transaction
        transaction = SportTransaction(
            event_id=team.event_id,
            team_id=team_id,
            transaction_type='quota_contribution',
            amount=amount,
            source=team.team_name,
            description=description,
            transaction_date=payment_date,
            created_by=current_user.id
        )
        db.session.add(transaction)
        
        # Update team quota
        team.quota_achieved = current_achieved + amount
        team.has_reached_quota = team.quota_achieved >= team.quota_target
        
        # Also add to regular transactions
        regular_trans = Transaction(
            date=payment_date,
            description=f'Quota payment - {team.team_name} - {description}',
            category='Quota Contribution',
            transaction_type='income',
            amount=amount,
            net_balance=0,
            created_by=current_user.id
        )
        db.session.add(regular_trans)
        
        db.session.commit()
        update_net_balances()
        
        # Calculate new totals
        new_total = current_achieved + amount
        remaining_after = team.quota_target - new_total
        
        message = f'₱{amount:,.2f} quota payment recorded for {team.team_name}! '
        if remaining_after <= 0:
            message += '🎉 Team has reached their quota target!'
        else:
            message += f'₱{remaining_after:,.2f} remaining.'
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error recording quota payment: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

# ==================== GET TEAM PAYMENT HISTORY ====================
@app.route('/api/team/<int:team_id>/payments')
@login_required
def get_team_payments(team_id):
    transactions = SportTransaction.query.filter_by(team_id=team_id, transaction_type='quota_contribution').order_by(SportTransaction.transaction_date.desc()).all()
    return jsonify({
        'payments': [{
            'id': t.id,
            'amount': t.amount,
            'date': t.transaction_date.strftime('%Y-%m-%d'),
            'description': t.description,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M') if t.created_at else None
        } for t in transactions]
    })

@app.route('/admin/finances/record-team-payment', methods=['POST'])
@login_required
def record_team_payment():
    try:
        team_id = request.form['team_id']
        team = SportTeam.query.get_or_404(team_id)
        amount = float(request.form['amount'])
        payment_date = datetime.strptime(request.form['payment_date'], '%Y-%m-%d').date()
        
        team.is_paid = True
        team.registration_fee = amount
        
        transaction = SportTransaction(
            event_id=team.event_id,
            transaction_type='registration_fee',
            amount=amount,
            source=team.team_name,
            description=f'Registration fee for team {team.team_name}',
            transaction_date=payment_date,
            created_by=current_user.id
        )
        db.session.add(transaction)
        
        regular_trans = Transaction(
            date=payment_date,
            description=f'Registration fee - {team.team_name}',
            category='Registration Fee',
            transaction_type='income',
            amount=amount,
            net_balance=0,
            created_by=current_user.id
        )
        db.session.add(regular_trans)
        
        db.session.commit()
        update_net_balances()
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': f'Registration fee for {team.team_name} recorded successfully!'})
        
        flash(f'Registration fee for {team.team_name} recorded successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': str(e)})
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))
    
@app.route('/admin/finances/add-transaction', methods=['POST'])
@login_required
def add_finance_transaction():
    try:
        transaction_type = request.form.get('transaction_type')
        amount = float(request.form.get('amount'))
        description = request.form.get('description')
        transaction_date_str = request.form.get('date')
        event_id = request.form.get('event_id') if request.form.get('event_id') else None
        
        print(f"=== ADDING TRANSACTION ===")
        print(f"Type: {transaction_type}")
        print(f"Amount: {amount}")
        print(f"Description: {description}")
        print(f"Date: {transaction_date_str}")
        print(f"Event ID: {event_id}")
        
        # Handle date - if not provided, use today
        if transaction_date_str and transaction_date_str.strip():
            transaction_date = datetime.strptime(transaction_date_str, '%Y-%m-%d').date()
        else:
            transaction_date = datetime.now().date()
        
        # Determine if this is income or expense
        is_income = transaction_type != 'expense'
        
        # Create sport transaction (event_id can be None)
        sport_trans = SportTransaction(
            event_id=event_id,
            participant_id=None,
            team_id=None,
            transaction_type=transaction_type,  # Keep original type (donation, solicitation, etc.)
            amount=amount,
            source='Manual Entry',
            description=description,
            transaction_date=transaction_date,
            reference_no='',
            created_by=current_user.id
        )
        db.session.add(sport_trans)
        
        # Determine category for regular transaction
        category = ''
        if transaction_type == 'donation':
            category = 'Donation'
        elif transaction_type == 'solicitation':
            category = 'Solicitation'
        elif transaction_type == 'registration_fee':
            category = 'Registration Fee'
        elif transaction_type == 'expense':
            category = 'Expense'
        else:
            category = transaction_type.replace('_', ' ').title()
        
        # ========== FIX: Create regular transaction with correct type ==========
        # For regular transactions, use 'income' for all non-expense types
        reg_transaction_type = 'income' if is_income else 'expense'
        
        # Get the last transaction to calculate running balance
        last_trans = Transaction.query.order_by(Transaction.date.desc(), Transaction.id.desc()).first()
        
        # Calculate new net balance
        if last_trans:
            if is_income:
                new_net_balance = last_trans.net_balance + amount
            else:
                new_net_balance = last_trans.net_balance - amount
        else:
            new_net_balance = amount if is_income else -amount
        
        regular_trans = Transaction(
            date=transaction_date,
            description=description,
            category=category,
            transaction_type=reg_transaction_type,  # 'income' or 'expense'
            amount=amount,
            reference_no='',
            net_balance=new_net_balance,
            created_by=current_user.id
        )
        db.session.add(regular_trans)
        
        db.session.commit()
        update_net_balances()
        
        print(f"✅ Transaction added successfully! Amount: ₱{amount:,.2f}, Type: {transaction_type}")
        flash('Transaction added successfully!', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('finances'))

@app.route('/api/team/<int:team_id>/players')
@login_required
def get_team_players(team_id):
    players = SportParticipant.query.filter_by(team_id=team_id).all()
    return jsonify({
        'players': [{
            'id': p.id,
            'name': p.name,
            'quota_target': p.quota_target,
            'quota_achieved': p.quota_achieved,
            'has_reached_quota': p.has_reached_quota,
            'age': p.age,
            'bracket': p.bracket,
            'age_group': p.age_group
        } for p in players]
    })

# Get all participants for an event (for Seminars)
@app.route('/api/event/<int:event_id>/participants')
@login_required
def get_event_participants(event_id):
    event = SportEvent.query.get_or_404(event_id)
    participants_data = []
    
    # Load bracket quotas
    bracket_quotas = {}
    if event.bracket_quotas:
        import json
        try:
            bracket_quotas = json.loads(event.bracket_quotas)
            print(f"Loaded bracket quotas: {bracket_quotas}")
        except:
            pass
    
    for participant in event.participants:
        # Get quota from bracket_quotas
        quota = participant.quota_target
        if quota == 0 and participant.bracket and participant.bracket in bracket_quotas:
            quota = bracket_quotas[participant.bracket]
            # Update the participant's quota in the database
            if participant.quota_target != quota:
                participant.quota_target = quota
                db.session.commit()
        
        participants_data.append({
            'id': participant.id,
            'name': participant.name,
            'registration_fee': participant.registration_fee if hasattr(participant, 'registration_fee') else 0,
            'amount_paid': participant.amount_paid if hasattr(participant, 'amount_paid') else 0,
            'is_paid': participant.is_paid if hasattr(participant, 'is_paid') else False,
            'age': participant.age,
            'bracket': participant.bracket,
            'age_group': participant.age_group,
            'quota_target': quota
        })
    return jsonify({'participants': participants_data})

# ==================== EVENT EXPENSES ROUTES ====================

@app.route('/api/event/<int:event_id>/expenses')
@login_required
def get_event_expenses(event_id):
    """Get all expenses for an event"""
    expenses = EventExpense.query.filter_by(event_id=event_id).order_by(EventExpense.date.desc()).all()
    return jsonify({
        'expenses': [{
            'id': e.id,
            'expense_type': e.expense_type,
            'category': e.category,
            'description': e.description,
            'amount': e.amount,
            'date': e.date.strftime('%Y-%m-%d') if e.date else None,
            'reference_no': e.reference_no
        } for e in expenses]
    })

@app.route('/admin/event/<int:event_id>/add-expense', methods=['POST'])
@login_required
@role_required('President', 'Treasurer','System Administrator')
def add_event_expense(event_id):
    """Add an expense to an event"""
    try:
        expense = EventExpense(
            event_id=event_id,
            expense_type=request.form['expense_type'],
            category=request.form.get('category', 'other'),
            description=request.form['description'],
            amount=float(request.form['amount']),
            date=datetime.strptime(request.form['expense_date'], '%Y-%m-%d').date(),
            deduct_from=request.form.get('deduct_from', 'general'),
            created_by=current_user.id
        )
        db.session.add(expense)
        db.session.commit()
        
        # Update the event's total expenses
        event = SportEvent.query.get(event_id)
        if event:
            event.total_expenses = event.calculate_total_expenses()
            db.session.commit()
        
        return jsonify({'success': True, 'message': 'Expense added successfully!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/event-expenses/delete/<int:expense_id>')
@login_required
@role_required('President', 'Treasurer','System Administrator')
def delete_event_expense(expense_id):
    """Delete an event expense"""
    expense = EventExpense.query.get_or_404(expense_id)
    try:
        # Delete the corresponding regular transaction
        trans = Transaction.query.filter_by(
            description=f"{expense.expense_type} - {expense.description}",
            amount=expense.amount
        ).first()
        if trans:
            db.session.delete(trans)
        
        db.session.delete(expense)
        db.session.commit()
        update_net_balances()
        
        return jsonify({'success': True, 'message': 'Expense deleted successfully!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

# Add participant directly to event (no team - for Seminars)
@app.route('/admin/sports/event/<int:id>/add-participant-direct', methods=['POST'])
@login_required
def add_sport_participant_direct(id):
    event = SportEvent.query.get_or_404(id)
    try:
        name = request.form.get('name', '').strip()
        registration_fee = float(request.form.get('registration_fee', 0))
        bracket = request.form.get('bracket', 'Open')
        age = request.form.get('age')
        
        # Get quota from the event's bracket_quotas
        quota_target = 0
        if event.bracket_quotas:
            import json
            try:
                quotas = json.loads(event.bracket_quotas)
                quota_target = quotas.get(bracket, 0)
                print(f"✅ Got quota for bracket '{bracket}': {quota_target}")
            except Exception as e:
                print(f"Error parsing bracket quotas: {e}")
        
        # Fallback to individual_quota_target if bracket not found
        if quota_target == 0:
            quota_target = event.individual_quota_target or 0
        
        # Also check the database column directly
        if quota_target == 0:
            # Try to get from team_quota_target if set
            quota_target = event.team_quota_target or 0
        
        participant = SportParticipant(
            event_id=id,
            team_id=None,
            name=name,
            registration_fee=registration_fee,
            amount_paid=0,
            is_paid=False,
            quota_target=quota_target,
            bracket=bracket,
            age=int(age) if age and age.isdigit() else None
        )
        db.session.add(participant)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Participant "{name}" added! Quota: ₱{quota_target:,.2f}'})
    except Exception as e:
        db.session.rollback()
        print(f"Error adding participant: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/debug/event/<int:event_id>/participants')
@login_required
def debug_event_participants(event_id):
    event = SportEvent.query.get_or_404(event_id)
    participants = SportParticipant.query.filter_by(event_id=event_id, team_id=None).all()
    return jsonify({
        'event_id': event.id,
        'event_name': event.name,
        'participant_count': len(participants),
        'participants': [{'id': p.id, 'name': p.name, 'quota_target': p.quota_target} for p in participants]
    })

# Upload Excel participants
@app.route('/admin/sports/event/<int:id>/upload-participants', methods=['POST'])
@login_required
@role_required('President', 'Treasurer','System Administrator')
def upload_participants_excel(id):
    event = SportEvent.query.get_or_404(id)
    
    try:
        if 'excel_file' not in request.files:
            return jsonify({'success': False, 'message': 'No file uploaded'})
        
        file = request.files['excel_file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No file selected'})
        
        if not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
            return jsonify({'success': False, 'message': 'Please upload an Excel file (.xlsx or .xls)'})
        
        import pandas as pd
        df = pd.read_excel(file)
        
        # Find columns
        name_col = df.columns[0]  # First column for names
        paid_col = df.columns[1] if len(df.columns) > 1 else None  # Second column for amount paid
        bracket_col = df.columns[2] if len(df.columns) > 2 else None  # Third column for bracket
        
        registration_fee = getattr(event, 'registration_fee', 0)
        
        # Load bracket quotas from event
        bracket_quotas = {}
        if event.bracket_quotas:
            import json
            try:
                bracket_quotas = json.loads(event.bracket_quotas)
                print(f"Loaded bracket quotas: {bracket_quotas}")
            except:
                pass
        
        new_count = 0
        updated_count = 0
        total_collected = 0
        
        for index, row in df.iterrows():
            name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ''
            if not name or name.lower() in ['name', 'participant', 'nan']:
                continue
            
            amount_paid = 0
            if paid_col and pd.notna(row[paid_col]):
                try:
                    amount_paid = float(row[paid_col])
                except:
                    amount_paid = 0
            
            bracket = str(row[bracket_col]).strip() if bracket_col and pd.notna(row[bracket_col]) else 'Teen'
            
            # Get quota from bracket_quotas
            quota_target = bracket_quotas.get(bracket, 0)
            if quota_target == 0:
                # Fallback to individual_quota_target
                quota_target = event.individual_quota_target or 0
            
            existing = SportParticipant.query.filter_by(
                event_id=id, name=name, team_id=None
            ).first()
            
            if existing:
                existing.amount_paid = amount_paid
                existing.is_paid = amount_paid >= registration_fee
                existing.bracket = bracket
                existing.quota_target = quota_target
                existing.has_reached_quota = amount_paid >= quota_target if quota_target > 0 else False
                updated_count += 1
            else:
                participant = SportParticipant(
                    event_id=id,
                    team_id=None,
                    name=name,
                    registration_fee=registration_fee,
                    amount_paid=amount_paid,
                    is_paid=(amount_paid >= registration_fee),
                    bracket=bracket,
                    quota_target=quota_target,
                    has_reached_quota=(amount_paid >= quota_target if quota_target > 0 else False)
                )
                db.session.add(participant)
                new_count += 1
            
            total_collected += amount_paid
        
        db.session.commit()
        
        fully_paid = SportParticipant.query.filter_by(event_id=id, team_id=None, is_paid=True).count()
        total_participants = SportParticipant.query.filter_by(event_id=id, team_id=None).count()
        
        return jsonify({
            'success': True,
            'message': f'✅ Processed {new_count + updated_count} participants! New: {new_count}, Updated: {updated_count}, Fully Paid: {fully_paid}/{total_participants}, Total Collected: ₱{total_collected:,.2f}'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})
    

@app.route('/admin/finances/add-player-fund', methods=['POST'])
@login_required
def add_player_fund():
    try:
        participant_id = request.form['participant_id']
        participant = SportParticipant.query.get_or_404(participant_id)
        amount = float(request.form['amount'])
        transaction_date = datetime.strptime(request.form['transaction_date'], '%Y-%m-%d').date()
        
        # Update participant payment
        participant.amount_paid += amount
        participant.is_paid = participant.amount_paid >= participant.registration_fee
        
        # Create sport transaction
        transaction = SportTransaction(
            event_id=participant.event_id,
            participant_id=participant_id,
            transaction_type='registration_fee',
            amount=amount,
            source=request.form.get('source', 'Payment'),
            description=f'Payment from {participant.name}',
            transaction_date=transaction_date,
            created_by=current_user.id
        )
        db.session.add(transaction)
        
        # Create regular transaction (for general ledger)
        regular_trans = Transaction(
            date=transaction_date,
            description=f'Payment from {participant.name}',
            category='Registration Fee',
            transaction_type='income',
            amount=amount,
            net_balance=0,
            created_by=current_user.id
        )
        db.session.add(regular_trans)
        
        db.session.commit()
        update_net_balances()
        
        if participant.is_paid:
            return jsonify({'success': True, 'message': f'✅ {participant.name} fully paid ₱{participant.registration_fee:,.2f}!'})
        else:
            remaining = participant.registration_fee - participant.amount_paid
            return jsonify({'success': True, 'message': f'✅ ₱{amount:,.2f} received! Needs ₱{remaining:,.2f} more.'})
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/admin/sports/event/<int:id>/update-expenses', methods=['POST'])
@login_required
@role_required('President', 'Treasurer','System Administrator')
def update_sport_expenses(id):
    event = SportEvent.query.get_or_404(id)
    try:
        old_court_fee = event.court_fee
        old_other_expenses = event.other_expenses
        
        event.court_fee = float(request.form['court_fee']) if request.form['court_fee'] else 0
        event.other_expenses = float(request.form['other_expenses']) if request.form['other_expenses'] else 0
        event.calculate_total_expenses()
        db.session.commit()
        
        # Add expense transactions to financial records for new expenses
        if event.court_fee > old_court_fee:
            expense_trans = Transaction(
                date=datetime.now().date(),
                description=f"{event.name} - Additional Court Fee",
                category=f"Event - {event.event_type}",
                transaction_type='expense',
                amount=event.court_fee - old_court_fee,
                net_balance=0,
                created_by=current_user.id
            )
            db.session.add(expense_trans)
        if event.other_expenses > old_other_expenses:
            expense_trans2 = Transaction(
                date=datetime.now().date(),
                description=f"{event.name} - Additional Other Expenses",
                category=f"Event - {event.event_type}",
                transaction_type='expense',
                amount=event.other_expenses - old_other_expenses,
                net_balance=0,
                created_by=current_user.id
            )
            db.session.add(expense_trans2)
        
        db.session.commit()
        update_net_balances()
        flash('Expenses updated successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('finances'))

@app.route('/admin/sports/event/<int:id>/complete')
@login_required
@role_required('President', 'System Administrator')
def complete_sport_event(id):
    event = SportEvent.query.get_or_404(id)
    event.status = 'completed'
    db.session.commit()
    
    # Create accomplishment record
    accomplishment = Accomplishment(
        title=f"{event.name} - Event",
        description=f"Successfully completed {event.name} on {event.event_date.strftime('%B %d, %Y')} at {event.location}. "
                    f"Participated by {len(event.participants)} participants.",
        accomplishment_date=event.event_date,
        status='approved',
        submitted_by=current_user.id,
        approved_by=current_user.id
    )
    db.session.add(accomplishment)
    db.session.commit()
    
    log_audit('Complete Event', f'Completed event: {event.name}')
    flash(f'🎉 Event "{event.name}" completed and added to accomplishments!', 'success')
    return redirect(url_for('finances'))

@app.route('/admin/sports/event/<int:event_id>/complete-status', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def complete_event_status(event_id):
    event = SportEvent.query.get_or_404(event_id)
    try:
        data = request.get_json()
        event.status = 'completed'
        
        # Handle completed_date properly
        if 'completed_date' in data and data['completed_date']:
            completed_date_value = data['completed_date']
            if isinstance(completed_date_value, str):
                try:
                    # Try ISO format
                    if 'T' in completed_date_value:
                        event.completed_date = datetime.fromisoformat(completed_date_value.replace('Z', '+00:00'))
                    else:
                        # Try date format
                        event.completed_date = datetime.strptime(completed_date_value, '%Y-%m-%d')
                except ValueError:
                    # If all fails, use current time
                    event.completed_date = datetime.now()
            else:
                event.completed_date = datetime.now()
        else:
            event.completed_date = datetime.now()
            
        event.facebook_link = data.get('facebook_link', '')
        event.instagram_link = data.get('instagram_link', '')
        event.tiktok_link = data.get('tiktok_link', '')
        
        db.session.commit()
        print(f"Event {event.name} completed at: {event.completed_date}")
        
        return jsonify({'success': True, 'message': f'Event "{event.name}" marked as completed!'})
    except Exception as e:
        db.session.rollback()
        print(f"Error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})
    
@app.route('/admin/finances/export')
@login_required
def export_financial_report():
    sport_transactions = SportTransaction.query.all()
    regular_transactions = Transaction.query.all()
    event_expenses = EventExpense.query.all()
    
    import csv
    from io import StringIO
    from flask import make_response
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['FINANCIAL REPORT'])
    writer.writerow([f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
    writer.writerow([])
    
    # Calculate totals from all sources (with deduplication)
    total_fund = sum(t.amount for t in sport_transactions if t.transaction_type in ['donation', 'solicitation', 'registration_fee', 'quota_contribution'])
    
    # ========== DEDUPLICATE EXPENSES ==========
    # Use a set to track unique expenses by (description, amount, date)
    unique_expenses = set()
    expense_entries = []
    
    # 1. From EventExpense (Primary source - keep these)
    for e in event_expenses:
        key = (e.description, e.amount, e.date.isoformat())
        if key not in unique_expenses:
            unique_expenses.add(key)
            expense_entries.append({
                'date': e.date,
                'source': 'Event Expense',
                'category': e.category or 'N/A',
                'description': f"{e.expense_type} - {e.description}",
                'amount': e.amount,
                'is_primary': True
            })
    
    # 2. From regular Transactions with type 'expense' (only if not already in EventExpense)
    for t in regular_transactions:
        if t.transaction_type == 'expense':
            # Check if this matches an event expense
            is_duplicate = False
            for e in event_expenses:
                if (e.description in t.description or t.description in e.description) and abs(e.amount - t.amount) < 0.01:
                    # Check if dates are close
                    if abs((e.date - t.date).days) <= 1:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                key = (t.description, t.amount, t.date.isoformat())
                if key not in unique_expenses:
                    unique_expenses.add(key)
                    expense_entries.append({
                        'date': t.date,
                        'source': 'Regular Transaction',
                        'category': t.category or 'Expense',
                        'description': t.description or 'N/A',
                        'amount': t.amount,
                        'is_primary': False
                    })
    
    # 3. From SportTransactions with type 'expense' (only if not already counted)
    for t in sport_transactions:
        if t.transaction_type == 'expense':
            is_duplicate = False
            for e in expense_entries:
                if (e['description'] in t.description or (t.description and t.description in e['description'])) and abs(e['amount'] - t.amount) < 0.01:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                key = (t.description, t.amount, t.transaction_date.isoformat())
                if key not in unique_expenses:
                    unique_expenses.add(key)
                    expense_entries.append({
                        'date': t.transaction_date,
                        'source': 'Sport Transaction',
                        'category': 'Expense',
                        'description': t.description or 'N/A',
                        'amount': t.amount,
                        'is_primary': False
                    })
    
    # Calculate total expenses from deduplicated entries
    total_expenses = sum(e['amount'] for e in expense_entries)
    
    writer.writerow(['SUMMARY'])
    writer.writerow(['Total Fund', f'PHP {total_fund:,.2f}'])
    writer.writerow(['Total Expenses', f'PHP {total_expenses:,.2f}'])
    writer.writerow(['Net Balance', f'PHP {(total_fund - total_expenses):,.2f}'])
    writer.writerow([])
    
    # ========== Donations ==========
    donations = [t for t in sport_transactions if t.transaction_type == 'donation']
    if donations:
        writer.writerow(['DONATIONS'])
        writer.writerow(['Date', 'Donor', 'Amount', 'Description'])
        for d in donations:
            writer.writerow([d.transaction_date, d.source or '', f'PHP {d.amount:,.2f}', d.description])
        writer.writerow([])
    
    # ========== Solicitation ==========
    solicitations = [t for t in sport_transactions if t.transaction_type == 'solicitation']
    if solicitations:
        writer.writerow(['SOLICITATIONS'])
        writer.writerow(['Date', 'Sponsor', 'Amount', 'Description'])
        for s in solicitations:
            writer.writerow([s.transaction_date, s.source or '', f'PHP {s.amount:,.2f}', s.description])
        writer.writerow([])
    
    # ========== Registration Fees ==========
    registrations = [t for t in sport_transactions if t.transaction_type == 'registration_fee']
    if registrations:
        writer.writerow(['REGISTRATION FEES'])
        writer.writerow(['Date', 'Team/Participant', 'Amount'])
        for r in registrations:
            writer.writerow([r.transaction_date, r.source or '', f'PHP {r.amount:,.2f}'])
        writer.writerow([])
    
    # ========== Quota Contributions ==========
    quota_contributions = [t for t in sport_transactions if t.transaction_type == 'quota_contribution']
    if quota_contributions:
        writer.writerow(['QUOTA CONTRIBUTIONS'])
        writer.writerow(['Date', 'Participant', 'Amount', 'Source'])
        for q in quota_contributions:
            participant_name = q.participant.name if q.participant else 'N/A'
            writer.writerow([q.transaction_date, participant_name, f'PHP {q.amount:,.2f}', q.source or ''])
        writer.writerow([])
    
    # ========== Expenses (Deduplicated) ==========
    writer.writerow(['EXPENSES (Deduplicated)'])
    writer.writerow(['Date', 'Source', 'Category', 'Description', 'Amount'])
    
    if expense_entries:
        # Sort by date
        expense_entries.sort(key=lambda x: x['date'])
        for e in expense_entries:
            writer.writerow([
                e['date'].strftime('%Y-%m-%d'),
                e['source'],
                e['category'],
                e['description'],
                f'PHP {e["amount"]:,.2f}'
            ])
    else:
        writer.writerow(['No expenses recorded'])
    
    writer.writerow([])
    
    # ========== Regular Transactions (Non-expense) ==========
    non_expense_transactions = [t for t in regular_transactions if t.transaction_type != 'expense']
    if non_expense_transactions:
        writer.writerow(['REGULAR TRANSACTIONS (Income)'])
        writer.writerow(['Date', 'Type', 'Category', 'Description', 'Amount'])
        for t in non_expense_transactions[:50]:
            writer.writerow([
                t.date,
                t.transaction_type.upper(),
                t.category or 'N/A',
                t.description or 'N/A',
                f'PHP {t.amount:,.2f}'
            ])
        writer.writerow([])
    
    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=financial_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response.headers['Content-Type'] = 'text/csv'
    return response

@app.route('/admin/finances/export-event-management')
@login_required
@role_required('President', 'Treasurer', 'System Administrator')
def export_event_management():
    """Export the Event Management table data with financial details"""
    try:
        import csv
        from io import StringIO
        from flask import make_response
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Get all events
        events = SportEvent.query.order_by(SportEvent.event_date.desc()).all()
        
        # Write header
        writer.writerow(['EVENT MANAGEMENT REPORT'])
        writer.writerow([f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
        writer.writerow([])
        
        if not events:
            writer.writerow(['No events found.'])
            response = make_response(output.getvalue())
            response.headers['Content-Disposition'] = 'attachment; filename=event_management_export.csv'
            response.headers['Content-Type'] = 'text/csv'
            return response
        
        # ========== EVENT MANAGEMENT TABLE DATA WITH FINANCIALS ==========
        writer.writerow(['#', 'Event Name', 'Type', 'Quota Type', 'Date', 'Location', 'Status', 'Brackets', 
                        'Total Amount Paid', 'Total Quota Target', 'Quota Achieved', 'Participants/Teams'])
        
        total_overall_paid = 0
        total_overall_quota = 0
        total_overall_achieved = 0
        
        for idx, event in enumerate(events, 1):
            # Format brackets
            brackets = ''
            if event.brackets:
                bracket_list = [b.strip() for b in event.brackets.split(',')]
                brackets = ', '.join(bracket_list)
            else:
                brackets = 'N/A'
            
            # Calculate financials for this event
            total_paid = 0
            total_quota_target = 0
            total_quota_achieved = 0
            participant_count = 0
            
            # For Sports events with teams
            if event.event_type == 'Sports':
                for team in event.teams:
                    total_paid += team.registration_fee or 0
                    total_quota_target += team.quota_target or 0
                    total_quota_achieved += team.quota_achieved or 0
                    participant_count += len(team.members)
                    
                    # Add individual member payments
                    for member in team.members:
                        total_paid += member.amount_paid or 0
            
            # For Seminar/Individual events
            for participant in event.participants:
                if not participant.team_id:  # Independent participants
                    total_paid += participant.amount_paid or 0
                    total_quota_target += participant.quota_target or 0
                    total_quota_achieved += participant.quota_achieved or 0
                    participant_count += 1
            
            # If no participants yet, show 0
            if participant_count == 0:
                participant_count = len(event.participants) if event.participants else 0
            
            total_overall_paid += total_paid
            total_overall_quota += total_quota_target
            total_overall_achieved += total_quota_achieved
            
            writer.writerow([
                idx,
                event.name,
                event.event_type,
                event.quota_type.title() if event.quota_type and event.quota_type != 'none' else 'N/A',
                event.event_date.strftime('%b %d, %Y') if event.event_date else 'N/A',
                event.location or 'Not specified',
                event.status.title(),
                brackets,
                f"₱{total_paid:,.2f}",
                f"₱{total_quota_target:,.2f}",
                f"₱{total_quota_achieved:,.2f}",
                participant_count
            ])
        
        writer.writerow([])
        writer.writerow(['Total Events:', len(events)])
        writer.writerow(['Total Amount Paid Overall:', f"₱{total_overall_paid:,.2f}"])
        writer.writerow(['Total Quota Target Overall:', f"₱{total_overall_quota:,.2f}"])
        writer.writerow(['Total Quota Achieved Overall:', f"₱{total_overall_achieved:,.2f}"])
        
        # ========== COUNT BY TYPE ==========
        writer.writerow([])
        writer.writerow(['COUNT BY TYPE:'])
        seminar_count = len([e for e in events if e.event_type == 'Seminar'])
        sports_count = len([e for e in events if e.event_type == 'Sports'])
        other_count = len([e for e in events if e.event_type not in ['Seminar', 'Sports']])
        
        writer.writerow(['Seminar:', seminar_count])
        writer.writerow(['Sports:', sports_count])
        writer.writerow(['Other:', other_count])
        
        # ========== COUNT BY STATUS ==========
        writer.writerow([])
        writer.writerow(['COUNT BY STATUS:'])
        upcoming_count = len([e for e in events if e.status == 'upcoming'])
        ongoing_count = len([e for e in events if e.status == 'ongoing'])
        completed_count = len([e for e in events if e.status == 'completed'])
        
        writer.writerow(['Upcoming:', upcoming_count])
        writer.writerow(['Ongoing:', ongoing_count])
        writer.writerow(['Completed:', completed_count])
        
        # ========== COUNT BY QUOTA TYPE ==========
        writer.writerow([])
        writer.writerow(['COUNT BY QUOTA TYPE:'])
        team_count = len([e for e in events if e.quota_type == 'team'])
        individual_count = len([e for e in events if e.quota_type == 'individual'])
        both_count = len([e for e in events if e.quota_type == 'both'])
        none_count = len([e for e in events if e.quota_type == 'none' or not e.quota_type])
        
        writer.writerow(['Team:', team_count])
        writer.writerow(['Individual:', individual_count])
        writer.writerow(['Both:', both_count])
        writer.writerow(['N/A:', none_count])
        
        # ========== FINANCIAL SUMMARY BY TYPE ==========
        writer.writerow([])
        writer.writerow(['FINANCIAL SUMMARY BY TYPE:'])
        
        seminar_paid = 0
        seminar_quota = 0
        seminar_achieved = 0
        sports_paid = 0
        sports_quota = 0
        sports_achieved = 0
        
        for event in events:
            if event.event_type == 'Seminar':
                for participant in event.participants:
                    if not participant.team_id:
                        seminar_paid += participant.amount_paid or 0
                        seminar_quota += participant.quota_target or 0
                        seminar_achieved += participant.quota_achieved or 0
            elif event.event_type == 'Sports':
                for team in event.teams:
                    sports_paid += team.registration_fee or 0
                    sports_quota += team.quota_target or 0
                    sports_achieved += team.quota_achieved or 0
                    for member in team.members:
                        sports_paid += member.amount_paid or 0
                for participant in event.participants:
                    if not participant.team_id:
                        sports_paid += participant.amount_paid or 0
                        sports_quota += participant.quota_target or 0
                        sports_achieved += participant.quota_achieved or 0
        
        writer.writerow(['Seminar - Total Paid:', f"₱{seminar_paid:,.2f}"])
        writer.writerow(['Seminar - Total Quota Target:', f"₱{seminar_quota:,.2f}"])
        writer.writerow(['Seminar - Total Quota Achieved:', f"₱{seminar_achieved:,.2f}"])
        writer.writerow([])
        writer.writerow(['Sports - Total Paid:', f"₱{sports_paid:,.2f}"])
        writer.writerow(['Sports - Total Quota Target:', f"₱{sports_quota:,.2f}"])
        writer.writerow(['Sports - Total Quota Achieved:', f"₱{sports_achieved:,.2f}"])
        
        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = f'attachment; filename=event_management_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        response.headers['Content-Type'] = 'text/csv'
        return response
        
    except Exception as e:
        print(f"Error exporting event management: {str(e)}")
        flash(f'Error exporting: {str(e)}', 'danger')
        return redirect(url_for('finances'))    

# ==================== SPORTS EVENT MANAGEMENT ROUTES (continued) ====================

# Set Active Event
@app.route('/admin/sports/event/set-active/<int:event_id>')
@login_required
@role_required('President', 'Treasurer','System Administrator')
def set_active_event(event_id):
    event = SportEvent.query.get_or_404(event_id)
    
    # Set all events to upcoming
    SportEvent.query.update({'status': 'upcoming'})
    
    # Set selected event to ongoing
    event.status = 'ongoing'
    db.session.commit()
    
    flash(f'Event "{event.name}" is now active!', 'success')
    return redirect(url_for('finances'))

# Get Sport Event API
@app.route('/api/sport-event/<int:event_id>')
@login_required
def get_sport_event_api(event_id):
    event = SportEvent.query.get_or_404(event_id)
    return jsonify({
        'id': event.id,
        'name': event.name,
        'event_type': event.event_type or event.sport_type,
        'event_date': event.event_date.strftime('%Y-%m-%d'),
        'location': event.location,
        'court_fee': event.court_fee,
        'other_expenses': event.other_expenses,
        'registration_fee': getattr(event, 'registration_fee', 0),
        'status': event.status,
        'completed_date': event.completed_date.isoformat() if event.completed_date else None,
        'facebook_link': event.facebook_link,
        'instagram_link': event.instagram_link,
        'tiktok_link': event.tiktok_link,
        'event_image': event.event_image,
        'completed_description': event.completed_description,
        # NEW fields
        'quota_type': event.quota_type,
        'team_quota_target': event.team_quota_target,
        'individual_quota_target': event.individual_quota_target,
        'brackets': event.brackets,
        'age_groups': event.age_groups,
        'bracket_quotas': event.get_all_bracket_quotas()
    })

# ==================== ADD THIS NEW ROUTE HERE ====================
@app.route('/api/event/<int:event_id>/teams')
@login_required
def get_event_teams(event_id):
    """Get all teams with their members and transactions for a specific event"""
    try:
        event = SportEvent.query.get_or_404(event_id)
        teams_data = []
        
        for team in event.teams:
            members_data = []
            for member in team.members:
                members_data.append({
                    'id': member.id,
                    'name': member.name,
                    'quota_target': member.quota_target,
                    'quota_achieved': member.quota_achieved,
                    'has_reached_quota': member.has_reached_quota,
                    'age': member.age,
                    'bracket': member.bracket,
                    'age_group': member.age_group
                })
            
            # Get transactions for this team
            transactions_data = []
            for trans in team.transactions:
                transactions_data.append({
                    'id': trans.id,
                    'amount': trans.amount,
                    'transaction_type': trans.transaction_type,
                    'transaction_date': trans.transaction_date.strftime('%Y-%m-%d') if trans.transaction_date else None,
                    'description': trans.description
                })
            
            teams_data.append({
                'id': team.id,
                'team_name': team.team_name,
                'captain_name': team.captain_name,
                'contact_number': team.contact_number,
                'registration_fee': team.registration_fee,
                'is_paid': team.is_paid,
                'quota_target': team.quota_target,
                'quota_achieved': team.quota_achieved,
                'has_reached_quota': team.has_reached_quota,
                'bracket': team.bracket,
                'age_group': team.age_group,
                'members': members_data,
                'transactions': transactions_data
            })
        
        return jsonify({'teams': teams_data})
    except Exception as e:
        print(f"Error in get_event_teams: {str(e)}")
        return jsonify({'teams': [], 'error': str(e)})

@app.route('/admin/sport-events/update/<int:event_id>', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def update_sport_event(event_id):
    event = SportEvent.query.get_or_404(event_id)
    try:
        # Update basic fields
        if request.form.get('name'):
            event.name = request.form['name']
        if request.form.get('sport_type'):
            event.event_type = request.form['sport_type']
            event.sport_type = request.form['sport_type']
        if request.form.get('event_date'):
            event.event_date = datetime.strptime(request.form['event_date'], '%Y-%m-%d').date()
        if request.form.get('location'):
            event.location = request.form['location']
        if request.form.get('court_fee'):
            event.court_fee = float(request.form['court_fee'])
        if request.form.get('other_expenses'):
            event.other_expenses = float(request.form['other_expenses'])
        if request.form.get('registration_fee'):
            event.registration_fee = float(request.form['registration_fee'])
        if request.form.get('quota_type'):
            event.quota_type = request.form['quota_type']
        if request.form.get('brackets'):
            event.brackets = request.form['brackets']
        if request.form.get('bracket_quotas'):
            import json
            event.bracket_quotas = request.form['bracket_quotas']
            try:
                quotas = json.loads(request.form['bracket_quotas'])
                if quotas and event.quota_type in ['individual', 'both']:
                    event.individual_quota_target = list(quotas.values())[0]
            except:
                pass
        
        # ========== FIX: Update social media links ==========
        if 'facebook_link' in request.form:
            event.facebook_link = request.form['facebook_link'] or None
        if 'instagram_link' in request.form:
            event.instagram_link = request.form['instagram_link'] or None
        if 'tiktok_link' in request.form:
            event.tiktok_link = request.form['tiktok_link'] or None
        
        # Update description
        if 'completed_description' in request.form:
            event.completed_description = request.form['completed_description'] or None
        
        # ========== Handle image upload ==========
        if 'event_image' in request.files:
            file = request.files['event_image']
            if file and file.filename != '':
                # Create upload folder if it doesn't exist
                upload_folder = os.path.join('static', 'uploads', 'events')
                os.makedirs(upload_folder, exist_ok=True)
                
                # Secure the filename and save
                filename = secure_filename(f"event_{event.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                
                # Delete old image if exists
                if event.event_image:
                    old_path = event.event_image.replace('/static/', 'static/')
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except:
                            pass
                
                # Update the event with new image path
                event.event_image = f'/static/uploads/events/{filename}'
                print(f"✅ Image uploaded: {event.event_image}")
        
        event.calculate_total_expenses()
        db.session.commit()
        
        log_audit('Update Event', f'Updated event: {event.name}')
        return jsonify({'success': True, 'message': f'Event "{event.name}" updated successfully!'})
    except Exception as e:
        db.session.rollback()
        print(f"Error updating event: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})
    
# Add Manual Event (for events.html)
@app.route('/admin/sport-events/add-manual', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def add_manual_sport_event():
    try:
        name = request.form.get('name')
        event_type = request.form.get('event_type', 'Seminar')
        event_date = datetime.strptime(request.form['event_date'], '%Y-%m-%d').date()
        location = request.form.get('location', '')
        completed_description = request.form.get('completed_description', '')
        facebook_link = request.form.get('facebook_link', '')
        instagram_link = request.form.get('instagram_link', '')
        tiktok_link = request.form.get('tiktok_link', '')
        
        # Create event with completed status
        event = SportEvent(
            name=name,
            event_type=event_type,
            sport_type=event_type,
            event_date=event_date,
            location=location,
            status='completed',
            completed_date=datetime.now(),
            completed_description=completed_description,
            facebook_link=facebook_link,
            instagram_link=instagram_link,
            tiktok_link=tiktok_link,
            created_by=current_user.id
        )
        
        # ========== Handle image upload ==========
        if 'event_image' in request.files:
            file = request.files['event_image']
            if file and file.filename != '':
                upload_folder = os.path.join('static', 'uploads', 'events')
                os.makedirs(upload_folder, exist_ok=True)
                
                filename = secure_filename(f"event_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                event.event_image = f'/static/uploads/events/{filename}'
                print(f"✅ Image uploaded for manual event: {event.event_image}")
        
        db.session.add(event)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Event "{name}" created successfully!'})
    except Exception as e:
        db.session.rollback()
        print(f"Error creating manual event: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

# ==================== SPORTS TEAM DELETE ROUTE ====================

@app.route('/admin/sport-teams/delete/<int:team_id>')
@login_required
@role_required('President', 'System Administrator')
def delete_sport_team(team_id):
    """Delete a sports team and all associated players and their transactions"""
    team = SportTeam.query.get_or_404(team_id)
    team_name = team.team_name
    
    try:
        # Delete all sport transactions for players in this team
        for player in team.members:
            SportTransaction.query.filter_by(participant_id=player.id).delete()
        
        # Delete all players in the team
        for player in team.members:
            db.session.delete(player)
        
        # Delete the team
        db.session.delete(team)
        db.session.commit()
        
        flash(f'✅ Team "{team_name}" and all its players have been deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error deleting team: {str(e)}', 'danger')
    
    return redirect(url_for('finances'))


# ==================== SPORTS EVENT DELETE ROUTE ====================

@app.route('/admin/sport-events/delete/<int:event_id>')
@login_required
@role_required('President', 'System Administrator')
def delete_sport_event(event_id):
    event = SportEvent.query.get_or_404(event_id)
    event_name = event.name
    
    try:
        # Get all participant names to delete their transactions
        participants = SportParticipant.query.filter_by(event_id=event_id).all()
        participant_names = [p.name for p in participants]
        
        # Get all sport transactions for this event
        sport_transactions = SportTransaction.query.filter_by(event_id=event_id).all()
        
        # Delete SportTransactions
        SportTransaction.query.filter_by(event_id=event_id).delete()
        
        # Delete regular Transaction records that reference this event
        trans_to_delete = []
        
        # Pattern 1: Event name in description
        trans_to_delete.extend(Transaction.query.filter(
            Transaction.description.like(f'%{event_name}%')
        ).all())
        
        # Pattern 2: Participant names in description
        for name in participant_names:
            if name:
                trans_to_delete.extend(Transaction.query.filter(
                    Transaction.description.like(f'%{name}%')
                ).all())
        
        # Pattern 3: SportTransaction descriptions
        for st in sport_transactions:
            if st.description:
                trans_to_delete.extend(Transaction.query.filter(
                    Transaction.description.like(f'%{st.description}%')
                ).all())
        
        # Remove duplicates and delete
        seen_ids = set()
        for t in trans_to_delete:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                db.session.delete(t)
        
        # Delete all participants
        SportParticipant.query.filter_by(event_id=event_id).delete()
        
        # Delete all teams
        SportTeam.query.filter_by(event_id=event_id).delete()
        
        # Delete all event expenses
        EventExpense.query.filter_by(event_id=event_id).delete()
        
        # Delete the event
        db.session.delete(event)
        
        db.session.commit()
        
        # Recalculate net balances (this updates the card metrics)
        update_net_balances()
        
        flash(f'✅ Sports Event "{event_name}" and all associated data have been deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error deleting sports event: {str(e)}', 'danger')
    
    return redirect(url_for('finances'))

# ==================== EVENTS (ADMIN) - UPDATED ====================

@app.route('/admin/events')
@login_required
def admin_events():
    # Get all completed events (including manually added ones)
    completed_sport_events = SportEvent.query.filter_by(status='completed').order_by(SportEvent.completed_date.desc()).all()
    return render_template('events.html', completed_sport_events=completed_sport_events)

@app.route('/admin/events/add', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def add_event():
    try:
        event = Event(
            title=request.form['title'],
            description=request.form['description'],
            start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%dT%H:%M') if request.form['start_date'] else None,
            end_date=datetime.strptime(request.form['end_date'], '%Y-%m-%dT%H:%M') if request.form['end_date'] else None,
            created_by=current_user.id
        )
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                event.image_path = f'/static/uploads/events/{filename}'
        db.session.add(event)
        db.session.commit()
        flash('Event added successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('admin_events'))

@app.route('/admin/events/delete/<int:id>')
@login_required
@role_required('President', 'System Administrator')
def delete_event(id):
    event = Event.query.get_or_404(id)
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted successfully!', 'success')
    return redirect(url_for('admin_events'))

@app.route('/api/event/<int:id>')
@login_required
def get_event(id):
    event = Event.query.get_or_404(id)
    return jsonify({
        'id': event.id,
        'title': event.title,
        'description': event.description,
        'start_date': event.start_date.strftime('%Y-%m-%dT%H:%M') if event.start_date else None,
        'end_date': event.end_date.strftime('%Y-%m-%dT%H:%M') if event.end_date else None,
        'image_path': event.image_path
    })

@app.route('/admin/events/edit/<int:id>', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def edit_event(id):
    event = Event.query.get_or_404(id)
    try:
        event.title = request.form['title']
        event.description = request.form['description']
        event.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%dT%H:%M') if request.form['start_date'] else None
        event.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%dT%H:%M') if request.form['end_date'] else None
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                if event.image_path:
                    old = event.image_path.replace('/static/', 'static/')
                    if os.path.exists(old):
                        os.remove(old)
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                event.image_path = f'/static/uploads/events/{filename}'
        db.session.commit()
        flash('Event updated successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('admin_events'))

# ==================== DRIVE LINKS (ADMIN) ====================

@app.route('/admin/links')
@login_required
def links():
    return render_template('links.html', links=DriveLink.query.order_by(DriveLink.category, DriveLink.name).all())

@app.route('/admin/links/add', methods=['POST'])
@login_required
def add_link():
    try:
        db.session.add(DriveLink(
            name=request.form['name'],
            url=request.form['url'],
            description=request.form['description'],
            category=request.form['category'],
            created_by=current_user.id
        ))
        db.session.commit()
        flash('Link added successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('links'))

@app.route('/admin/links/delete/<int:id>')
@login_required
def delete_link(id):
    link = DriveLink.query.get_or_404(id)
    try:
        db.session.delete(link)
        db.session.commit()
        flash('Link deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('links'))

# ==================== ACCOMPLISHMENTS (ADMIN) - UPDATED ====================
@app.route('/admin/accomplishments')
@login_required
def admin_accomplishments():
    # Get completed sport events
    completed_sport_events = SportEvent.query.filter_by(status='completed').order_by(SportEvent.completed_date.desc()).all()
    
    # Get regular events
    regular_events = Event.query.order_by(Event.start_date.desc()).all()
    
    # Combine both lists for the dropdown
    combined_events = []
    
    # Add sport events (with 'sport' type)
    for event in completed_sport_events:
        # Get participant count for this event
        participant_count = SportParticipant.query.filter_by(event_id=event.id).count()
        
        combined_events.append({
            'id': event.id,
            'title': event.name,
            'type': 'sport',
            'date': event.completed_date or event.event_date,
            'image': event.event_image,
            'description': event.completed_description or '',
            'participant_count': participant_count,
            'facebook_link': event.facebook_link,
            'instagram_link': event.instagram_link,
            'tiktok_link': event.tiktok_link
        })
    
    # Add regular events (with 'regular' type)
    for event in regular_events:
        combined_events.append({
            'id': event.id,
            'title': event.title,
            'type': 'regular',
            'date': event.start_date,
            'image': event.image_path,
            'description': event.description or '',
            'participant_count': 0,
            'facebook_link': None,
            'instagram_link': None,
            'tiktok_link': None
        })
    
    # ========== GET ACCOMPLISHMENTS WITH PARTICIPANT COUNT ==========
    accomplishments = Accomplishment.query.order_by(Accomplishment.accomplishment_date.desc()).all()
    
    # Enrich accomplishments with event data and participant count
    enriched_accomplishments = []
    for acc in accomplishments:
        participant_count = 0
        event_facebook = None
        event_instagram = None
        event_tiktok = None
        
        # Get participant count from event if linked
        if acc.event_id:
            sport_event = db.session.get(SportEvent, acc.event_id)
            if sport_event:
                participant_count = SportParticipant.query.filter_by(event_id=acc.event_id).count()
                event_facebook = sport_event.facebook_link
                event_instagram = sport_event.instagram_link
                event_tiktok = sport_event.tiktok_link
        
        acc_data = {
            'id': acc.id,
            'event_id': acc.event_id,
            'title': acc.title,
            'description': acc.description,
            'accomplishment_date': acc.accomplishment_date,
            'file_path': acc.file_path,
            'status': acc.status,
            'submitted_by': acc.submitted_by,
            'approved_by': acc.approved_by,
            'participant_count': participant_count,
            # Use accomplishment's links, fallback to event links
            'facebook_link': acc.facebook_link or event_facebook,
            'instagram_link': acc.instagram_link or event_instagram,
            'tiktok_link': acc.tiktok_link or event_tiktok
        }
        
        enriched_accomplishments.append(acc_data)
    
    return render_template('accomplishments.html',
        accomplishments=enriched_accomplishments,
        events=combined_events
    )

@app.route('/admin/accomplishments/add', methods=['POST'])
@login_required
def add_accomplishment():
    try:
        event_id = int(request.form['event_id']) if request.form['event_id'] else None
        
        # Get user-provided links
        user_facebook = request.form.get('facebook_link') or None
        user_instagram = request.form.get('instagram_link') or None
        user_tiktok = request.form.get('tiktok_link') or None
        
        # Auto-copy social media links from event
        facebook_link = user_facebook
        instagram_link = user_instagram
        tiktok_link = user_tiktok
        file_path = None
        
        if event_id:
            sport_event = db.session.get(SportEvent, event_id)
            if sport_event:
                # Copy image
                if sport_event.event_image:
                    file_path = sport_event.event_image
                # Copy social media links if user didn't provide their own
                if not facebook_link and sport_event.facebook_link:
                    facebook_link = sport_event.facebook_link
                if not instagram_link and sport_event.instagram_link:
                    instagram_link = sport_event.instagram_link
                if not tiktok_link and sport_event.tiktok_link:
                    tiktok_link = sport_event.tiktok_link
        
        accomplishment = Accomplishment(
            event_id=event_id,
            title=request.form['title'],
            description=request.form['description'],
            accomplishment_date=datetime.strptime(request.form['accomplishment_date'], '%Y-%m-%d').date() if request.form['accomplishment_date'] else None,
            submitted_by=current_user.id,
            status='pending',
            facebook_link=facebook_link,
            instagram_link=instagram_link,
            tiktok_link=tiktok_link,
            file_path=file_path
        )
        
        # If user uploaded a file, override the event image
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                accomplishment.file_path = f'/static/uploads/events/{filename}'
        
        db.session.add(accomplishment)
        db.session.commit()
        log_audit('Add Accomplishment', f'Added accomplishment: {accomplishment.title}')
        flash('Accomplishment submitted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'danger')
    return redirect(url_for('admin_accomplishments'))

@app.route('/admin/accomplishments/approve/<int:id>')
@login_required
@role_required('President', 'System Administrator')
def approve_accomplishment(id):
    accomplishment = Accomplishment.query.get_or_404(id)
    accomplishment.status = 'approved'
    accomplishment.approved_by = current_user.id
    db.session.commit()
    log_audit('Approve Accomplishment', f'Approved accomplishment: {accomplishment.title}')
    flash('Accomplishment approved!', 'success')
    return redirect(url_for('admin_accomplishments'))

@app.route('/api/accomplishment/<int:id>')
@login_required
def get_accomplishment(id):
    accomplishment = Accomplishment.query.get_or_404(id)
    
    # Get event details if exists
    event_name = None
    event_image = None
    event_facebook = None
    event_instagram = None
    event_tiktok = None
    participant_count = 0
    
    if accomplishment.event_id:
        sport_event = db.session.get(SportEvent, accomplishment.event_id)
        if sport_event:
            event_name = sport_event.name
            event_image = sport_event.event_image
            event_facebook = sport_event.facebook_link
            event_instagram = sport_event.instagram_link
            event_tiktok = sport_event.tiktok_link
            participant_count = SportParticipant.query.filter_by(event_id=accomplishment.event_id).count()
        else:
            regular_event = db.session.get(Event, accomplishment.event_id)
            if regular_event:
                event_name = regular_event.title
                event_image = regular_event.image_path
    
    # Use accomplishment's links, fallback to event links
    return jsonify({
        'id': accomplishment.id,
        'title': accomplishment.title,
        'description': accomplishment.description,
        'accomplishment_date': accomplishment.accomplishment_date.strftime('%Y-%m-%d') if accomplishment.accomplishment_date else None,
        'event_id': accomplishment.event_id,
        'file_path': accomplishment.file_path,
        'status': accomplishment.status,
        'submitted_by': accomplishment.submitted_by,
        'event_name': event_name,
        'event_image': event_image,
        'facebook_link': accomplishment.facebook_link or event_facebook or '',
        'instagram_link': accomplishment.instagram_link or event_instagram or '',
        'tiktok_link': accomplishment.tiktok_link or event_tiktok or '',
        'participant_count': participant_count
    })

@app.route('/api/event-details/<int:event_id>')
@login_required
def get_event_details(event_id):
    """Get event details from either SportEvent or Event table"""
    # FIXED: Use db.session.get()
    sport_event = db.session.get(SportEvent, event_id)
    if sport_event:
        return jsonify({
            'id': sport_event.id,
            'name': sport_event.name,
            'event_date': sport_event.event_date.strftime('%Y-%m-%d') if sport_event.event_date else None,
            'completed_date': sport_event.completed_date.strftime('%Y-%m-%d') if sport_event.completed_date else None,
            'image': sport_event.event_image,
            'description': sport_event.completed_description or '',
            'type': 'sport'
        })
    
    regular_event = db.session.get(Event, event_id)
    if regular_event:
        return jsonify({
            'id': regular_event.id,
            'name': regular_event.title,
            'event_date': regular_event.start_date.strftime('%Y-%m-%d') if regular_event.start_date else None,
            'completed_date': None,
            'image': regular_event.image_path,
            'description': regular_event.description or '',
            'type': 'regular'
        })
    
    return jsonify({'error': 'Event not found'}), 404

@app.route('/admin/accomplishments/update/<int:id>', methods=['POST'])
@login_required
def update_accomplishment(id):
    accomplishment = Accomplishment.query.get_or_404(id)
    if current_user.role != 'President' and current_user.id != accomplishment.submitted_by:
        flash('You do not have permission to edit this accomplishment.', 'danger')
        return redirect(url_for('admin_accomplishments'))
    try:
        event_id = int(request.form['event_id']) if request.form['event_id'] else None
        
        accomplishment.title = request.form['title']
        accomplishment.description = request.form['description']
        accomplishment.accomplishment_date = datetime.strptime(request.form['accomplishment_date'], '%Y-%m-%d').date() if request.form['accomplishment_date'] else None
        accomplishment.event_id = event_id
        
        # Check if user provided links, otherwise use event links
        user_facebook = request.form.get('facebook_link')
        user_instagram = request.form.get('instagram_link')
        user_tiktok = request.form.get('tiktok_link')
        
        # Auto-copy social media links from event
        if event_id:
            sport_event = db.session.get(SportEvent, event_id)
            if sport_event:
                # Copy image if no file uploaded
                if 'file' not in request.files or request.files['file'].filename == '':
                    if sport_event.event_image:
                        accomplishment.file_path = sport_event.event_image
                
                # Copy social media links if user didn't provide their own
                if not user_facebook and sport_event.facebook_link:
                    accomplishment.facebook_link = sport_event.facebook_link
                else:
                    accomplishment.facebook_link = user_facebook or None
                    
                if not user_instagram and sport_event.instagram_link:
                    accomplishment.instagram_link = sport_event.instagram_link
                else:
                    accomplishment.instagram_link = user_instagram or None
                    
                if not user_tiktok and sport_event.tiktok_link:
                    accomplishment.tiktok_link = sport_event.tiktok_link
                else:
                    accomplishment.tiktok_link = user_tiktok or None
            else:
                regular_event = db.session.get(Event, event_id)
                if regular_event:
                    if 'file' not in request.files or request.files['file'].filename == '':
                        if regular_event.image_path:
                            accomplishment.file_path = regular_event.image_path
                
                # For regular events, use user-provided links or None
                accomplishment.facebook_link = user_facebook or None
                accomplishment.instagram_link = user_instagram or None
                accomplishment.tiktok_link = user_tiktok or None
        else:
            # No event selected, use user-provided links or None
            accomplishment.facebook_link = user_facebook or None
            accomplishment.instagram_link = user_instagram or None
            accomplishment.tiktok_link = user_tiktok or None
        
        if accomplishment.status == 'approved' and current_user.role != 'President':
            accomplishment.status = 'pending'
            accomplishment.approved_by = None
            flash('Accomplishment reverted to pending for re-review.', 'warning')
        
        # Handle file upload
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '' and allowed_file(file.filename):
                if accomplishment.file_path:
                    old_path = accomplishment.file_path.replace('/static/', 'static/')
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                accomplishment.file_path = f'/static/uploads/events/{filename}'
        
        db.session.commit()
        log_audit('Update Accomplishment', f'Updated accomplishment: {accomplishment.title}')
        flash('Accomplishment updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating accomplishment: {str(e)}', 'danger')
    return redirect(url_for('admin_accomplishments'))

@app.route('/admin/accomplishments/delete/<int:id>')
@login_required
def delete_accomplishment(id):
    accomplishment = Accomplishment.query.get_or_404(id)
    if current_user.role != 'President':
        flash('Only the President can delete accomplishments.', 'danger')
        return redirect(url_for('admin_accomplishments'))
    try:
        if accomplishment.file_path:
            file_path = accomplishment.file_path.replace('/static/', 'static/')
            if os.path.exists(file_path):
                os.remove(file_path)
        db.session.delete(accomplishment)
        db.session.commit()
        log_audit('Delete Accomplishment', f'Deleted accomplishment: {accomplishment.title}')
        flash('Accomplishment deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting accomplishment: {str(e)}', 'danger')
    return redirect(url_for('admin_accomplishments'))

@app.route('/admin/accomplishments/update-social-links/<int:id>', methods=['POST'])
@login_required
def update_accomplishment_social_links(id):
    """Update only the social media links for an accomplishment"""
    accomplishment = Accomplishment.query.get_or_404(id)
    
    try:
        accomplishment.facebook_link = request.form.get('facebook_link') or None
        accomplishment.instagram_link = request.form.get('instagram_link') or None
        accomplishment.tiktok_link = request.form.get('tiktok_link') or None
        
        db.session.commit()
        log_audit('Update Accomplishment Social Links', f'Updated social links for accomplishment: {accomplishment.title}')
        
        return jsonify({'success': True, 'message': 'Social media links updated successfully!'})
    except Exception as e:
        db.session.rollback()
        print(f"Error updating social links: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})
    
# ==================== AUDIT TRAIL (ADMIN) ====================

@app.route('/admin/audit')
@login_required
@role_required('President', 'Auditor', 'System Administrator')
def audit_trail():
    return render_template('audit_trail.html', logs=AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all())

# ==================== CONTACT MESSAGES (ADMIN) ====================

@app.route('/admin/contact-messages')
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def contact_messages():
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return render_template('contact_messages.html', messages=messages)

@app.route('/admin/contact-messages/mark-read/<int:id>')
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def mark_message_read(id):
    message = ContactMessage.query.get_or_404(id)
    message.is_read = True
    db.session.commit()
    flash('Message marked as read', 'success')
    return redirect(url_for('contact_messages'))

@app.route('/admin/contact-messages/delete/<int:id>')
@login_required
@role_required('President', 'System Administrator')
def delete_message(id):
    message = ContactMessage.query.get_or_404(id)
    db.session.delete(message)
    db.session.commit()
    flash('Message deleted successfully', 'success')
    return redirect(url_for('contact_messages'))

@app.route('/admin/contact-messages/mark-all-read', methods=['POST'])
@login_required
@role_required('President', 'Secretary', 'System Administrator')
def mark_all_messages_read():
    ContactMessage.query.filter_by(is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

# ==================== USER MANAGEMENT API (ADMIN) ====================

@app.route('/api/generated-officer-users')
@login_required
@role_required('President', 'System Administrator')
def api_generated_officer_users():
    users = User.query.filter(User.username != 'admin').all()
    accounts = [{
        'username': u.username,
        'full_name': u.full_name,
        'role': u.role,
        'email': u.email
    } for u in users]
    return jsonify({'accounts': accounts})

@app.route('/api/generate-officer-accounts', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def generate_officer_accounts():
    try:
        # Get current officers
        officers = Officer.query.filter_by(is_current=True).all()
        if not officers:
            return jsonify({'success': False, 'message': 'No officers found. Please add officers first.', 'accounts': []})
        
        # Role mapping
        role_map = {
            'President': 'President',
            'Vice President': 'Vice President', 
            'Secretary': 'Secretary',
            'Treasurer': 'Treasurer',
            'Auditor': 'Auditor'
        }
        
        created = []
        updated = []
        deleted = []
        
        # Get existing users (excluding admin)
        existing_users = User.query.filter(User.username != 'admin').all()
        
        # Generate usernames from current officers
        current_usernames = []
        officer_map = {}
        for officer in officers:
            username = officer.full_name.lower().replace(' ', '_').replace('.', '').replace(',', '')
            current_usernames.append(username)
            officer_map[username] = officer
        
        # ========== DELETE old accounts ==========
        for user in existing_users:
            if user.username not in current_usernames:
                db.session.delete(user)
                deleted.append(user.username)
                print(f"🗑️ Deleted old account: {user.username}")
        
        # ========== CREATE/UPDATE accounts for current officers ==========
        for username, officer in officer_map.items():
            role = role_map.get(officer.position, 'Member')
            
            # Check if user already exists
            existing_user = User.query.filter_by(username=username).first()
            
            if existing_user:
                # Update existing user
                existing_user.full_name = officer.full_name
                existing_user.role = role
                existing_user.email = officer.email if officer.email else ''
                db.session.commit()
                updated.append(username)
                print(f"🔄 Updated account for: {officer.full_name} ({username})")
            else:
                # Create new user
                user = User(
                    username=username, 
                    role=role, 
                    full_name=officer.full_name, 
                    email=officer.email if officer.email else ''
                )
                user.set_password('password123')
                db.session.add(user)
                created.append({
                    'username': username, 
                    'full_name': officer.full_name, 
                    'role': role, 
                    'email': officer.email if officer.email else ''
                })
                print(f"✅ Created account for: {officer.full_name} ({username})")
        
        db.session.commit()
        
        # Build message
        message_parts = []
        if created:
            message_parts.append(f'Created {len(created)} new accounts')
        if updated:
            message_parts.append(f'Updated {len(updated)} existing accounts')
        if deleted:
            message_parts.append(f'Deleted {len(deleted)} old accounts')
        
        message = ', '.join(message_parts) if message_parts else 'No changes made'
        
        return jsonify({
            'success': True, 
            'message': message, 
            'accounts': created,
            'deleted_count': len(deleted),
            'updated_count': len(updated)
        })
    except Exception as e:
        db.session.rollback()
        print(f"Error: {str(e)}")
        return jsonify({'success': False, 'message': str(e), 'accounts': []})

@app.route('/api/delete-user-account', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def delete_user_account():
    try:
        data = request.get_json()
        username = data.get('username')
        
        if not username:
            return jsonify({'success': False, 'message': 'Username is required'})
        
        # Prevent deleting admin
        if username == 'admin':
            return jsonify({'success': False, 'message': 'Cannot delete admin account'})
        
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'})
        
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'User "{username}" deleted successfully!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})
    
@app.route('/api/delete-old-accounts', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def delete_old_accounts():
    try:
        # Get current officer usernames
        officers = Officer.query.filter_by(is_current=True).all()
        current_usernames = []
        for officer in officers:
            username = officer.full_name.lower().replace(' ', '_').replace('.', '').replace(',', '')
            current_usernames.append(username)
        
        # Delete users not in current officers list
        users = User.query.filter(User.username != 'admin').all()
        deleted_count = 0
        deleted_usernames = []
        
        for user in users:
            if user.username not in current_usernames:
                deleted_usernames.append(user.username)
                db.session.delete(user)
                deleted_count += 1
        
        db.session.commit()
        
        if deleted_count > 0:
            message = f'Deleted {deleted_count} old accounts: {", ".join(deleted_usernames)}'
        else:
            message = 'No old accounts to delete. All accounts match current officers.'
        
        return jsonify({'success': True, 'message': message, 'deleted_count': deleted_count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})
    
@app.route('/api/settings/theme', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def save_theme_setting():
    try:
        data = request.get_json()
        theme = data.get('theme', 'light')
        primary_color = data.get('primary_color')
        
        # Save theme
        theme_setting = SystemSetting.query.filter_by(setting_key='theme').first()
        if not theme_setting:
            theme_setting = SystemSetting(setting_key='theme')
            db.session.add(theme_setting)
        theme_setting.setting_value = theme
        theme_setting.updated_at = datetime.now()
        
        # Save primary color if provided
        if primary_color:
            color_setting = SystemSetting.query.filter_by(setting_key='primary_color').first()
            if not color_setting:
                color_setting = SystemSetting(setting_key='primary_color')
                db.session.add(color_setting)
            color_setting.setting_value = primary_color
            color_setting.updated_at = datetime.now()
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Theme settings saved!'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/reset-password-by-username', methods=['POST'])
@login_required
@role_required('President', 'System Administrator')
def api_reset_password_by_username():
    data = request.get_json()
    user = User.query.filter_by(username=data.get('username')).first()
    if user:
        user.set_password(data.get('new_password'))
        db.session.commit()
        return jsonify({'success': True, 'message': 'Password updated successfully!'})
    return jsonify({'success': False, 'message': 'User not found'})

# ==================== SETTINGS (ADMIN) ====================
@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@role_required('President', 'System Administrator')
def settings():
    if request.method == 'POST':
        # Save organization settings
        for key, value in [
            ('org_name', request.form.get('org_name')),
            ('theme', request.form.get('theme', 'light')),
            ('primary_color', request.form.get('primary_color', '#4CAF50'))
        ]:
            setting = SystemSetting.query.filter_by(setting_key=key).first() or SystemSetting(setting_key=key)
            setting.setting_value = value
            setting.updated_at = datetime.now()
            db.session.add(setting)
        
        # Handle logo upload
        if 'logo' in request.files:
            file = request.files['logo']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"logo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['LOGO_UPLOAD_FOLDER'], filename))
                logo = SystemSetting.query.filter_by(setting_key='logo_url').first() or SystemSetting(setting_key='logo_url')
                logo.setting_value = f'/static/uploads/logos/{filename}'
                db.session.add(logo)
        
        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('settings'))
    
    # GET request - display form
    org_name = SystemSetting.query.filter_by(setting_key='org_name').first()
    theme = SystemSetting.query.filter_by(setting_key='theme').first()
    primary_color = SystemSetting.query.filter_by(setting_key='primary_color').first()
    logo_url = SystemSetting.query.filter_by(setting_key='logo_url').first()
    
    return render_template('settings.html',
        org_name=org_name.setting_value if org_name else 'Sitio Verdant Hills Youth Organization',
        theme=theme.setting_value if theme else 'light',
        primary_color=primary_color.setting_value if primary_color else '#4CAF50',
        logo_url=logo_url.setting_value if logo_url else None
    )

# ==================== ADMIN PUBLIC CONTENT MANAGEMENT ====================

@app.route('/admin/public-content', methods=['GET', 'POST'])
@login_required
@role_required('President', 'System Administrator')
def admin_public_content():
    if request.method == 'POST':
        form_type = request.form.get('form_type', 'site_settings')
        
        if form_type == 'site_settings':
            # Save Site Settings
            about_content = request.form.get('about_content')
            mission = request.form.get('mission')
            vision = request.form.get('vision')
            site_name = request.form.get('site_name')
            founded_year = request.form.get('founded_year')
            
            # Save text settings
            for key, value in [('about_content', about_content), ('mission', mission), ('vision', vision), ('site_name', site_name), ('founded_year', founded_year)]:
                setting = PublicSetting.query.filter_by(setting_key=key).first()
                if not setting:
                    setting = PublicSetting(setting_key=key)
                    db.session.add(setting)
                setting.setting_value = value
            
            # Handle logo upload
            if 'site_logo' in request.files:
                file = request.files['site_logo']
                if file and allowed_file(file.filename):
                    # Delete old logo if exists
                    old_logo = PublicSetting.query.filter_by(setting_key='site_logo').first()
                    if old_logo and old_logo.setting_value:
                        old_path = old_logo.setting_value.replace('/static/', 'static/')
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    
                    filename = secure_filename(f"public_logo_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
                    file.save(os.path.join(app.config['LOGO_UPLOAD_FOLDER'], filename))
                    logo_setting = PublicSetting.query.filter_by(setting_key='site_logo').first()
                    if not logo_setting:
                        logo_setting = PublicSetting(setting_key='site_logo')
                        db.session.add(logo_setting)
                    logo_setting.setting_value = f'/static/uploads/logos/{filename}'
            
            db.session.commit()
            flash('Site settings updated successfully!', 'success')
            
        # In admin_public_content route, change:
        elif form_type == 'contact_info':
            contact_email = request.form.get('contact_email')
            contact_phone = request.form.get('contact_phone')
            contact_address = request.form.get('contact_address')
            social_facebook = request.form.get('social_facebook')
            social_tiktok = request.form.get('social_tiktok')  # CHANGED from social_tiktok
            social_instagram = request.form.get('social_instagram')
            
            for key, value in [('contact_email', contact_email), ('contact_phone', contact_phone), 
                            ('contact_address', contact_address), ('social_facebook', social_facebook),
                            ('social_tiktok', social_tiktok), ('social_instagram', social_instagram)]:  # CHANGED
                setting = PublicSetting.query.filter_by(setting_key=key).first()
                if not setting:
                    setting = PublicSetting(setting_key=key)
                    db.session.add(setting)
                setting.setting_value = value
            
            db.session.commit()
            flash('Contact information updated successfully!', 'success')
        
        return redirect(url_for('admin_public_content'))
    
    # GET request - display form
    site_name = PublicSetting.query.filter_by(setting_key='site_name').first()
    site_logo = PublicSetting.query.filter_by(setting_key='site_logo').first()
    about_content = PublicSetting.query.filter_by(setting_key='about_content').first()
    mission = PublicSetting.query.filter_by(setting_key='mission').first()
    vision = PublicSetting.query.filter_by(setting_key='vision').first()
    founded_year = PublicSetting.query.filter_by(setting_key='founded_year').first()
    contact_email = PublicSetting.query.filter_by(setting_key='contact_email').first()
    contact_phone = PublicSetting.query.filter_by(setting_key='contact_phone').first()
    contact_address = PublicSetting.query.filter_by(setting_key='contact_address').first()
    social_facebook = PublicSetting.query.filter_by(setting_key='social_facebook').first()
    social_tiktok = PublicSetting.query.filter_by(setting_key='social_tiktok').first()
    social_instagram = PublicSetting.query.filter_by(setting_key='social_instagram').first()
    
    # ========== FETCH EVENTS - EXCLUDING COMPLETED SPORT EVENTS ==========
    # Regular events from Event table (all)
    regular_events = Event.query.order_by(Event.start_date.desc()).all()
    
    # Sports events - ONLY UPCOMING OR ONGOING (exclude completed)
    sport_events = SportEvent.query.filter(
        SportEvent.status.in_(['upcoming', 'ongoing'])
    ).order_by(SportEvent.event_date.desc()).all()
    
    # Combine both lists for the dropdown
    combined_events = []
    
    # Add regular events (with 'regular' type)
    for event in regular_events:
        combined_events.append({
            'id': event.id,
            'title': event.title,
            'type': 'regular',
            'date': event.start_date,
            'image': event.image_path,
            'description': event.description or '',
            'participant_count': 0,
            'facebook_link': None,
            'instagram_link': None,
            'tiktok_link': None,
            'status': 'active'
        })
    
    # Add sport events (with 'sport' type) - ONLY upcoming/ongoing
    for event in sport_events:
        participant_count = SportParticipant.query.filter_by(event_id=event.id).count()
        combined_events.append({
            'id': event.id,
            'title': event.name,
            'type': 'sport',
            'date': event.event_date,
            'image': event.event_image,
            'description': event.completed_description or '',
            'participant_count': participant_count,
            'facebook_link': event.facebook_link,
            'instagram_link': event.instagram_link,
            'tiktok_link': event.tiktok_link,
            'status': event.status
        })
    
    # ========== ACCOMPLISHMENTS WITH PARTICIPANT COUNT ==========
    accomplishments = Accomplishment.query.order_by(Accomplishment.accomplishment_date.desc()).all()
    
    # Enrich accomplishments with event data and participant count
    enriched_accomplishments = []
    for acc in accomplishments:
        participant_count = 0
        event_facebook = None
        event_instagram = None
        event_tiktok = None
        
        if acc.event_id:
            sport_event = db.session.get(SportEvent, acc.event_id)
            if sport_event:
                participant_count = SportParticipant.query.filter_by(event_id=acc.event_id).count()
                event_facebook = sport_event.facebook_link
                event_instagram = sport_event.instagram_link
                event_tiktok = sport_event.tiktok_link
        
        acc_data = {
            'id': acc.id,
            'event_id': acc.event_id,
            'title': acc.title,
            'description': acc.description,
            'accomplishment_date': acc.accomplishment_date,
            'file_path': acc.file_path,
            'status': acc.status,
            'submitted_by': acc.submitted_by,
            'approved_by': acc.approved_by,
            'participant_count': participant_count,
            'facebook_link': acc.facebook_link or event_facebook,
            'instagram_link': acc.instagram_link or event_instagram,
            'tiktok_link': acc.tiktok_link or event_tiktok
        }
        enriched_accomplishments.append(acc_data)
    
    return render_template('admin_public_content.html',
        site_name=site_name.setting_value if site_name else '',
        site_logo=site_logo.setting_value if site_logo else None,
        about_content=about_content.setting_value if about_content else '',
        mission=mission.setting_value if mission else '',
        vision=vision.setting_value if vision else '',
        founded_year=founded_year.setting_value if founded_year else '',
        contact_email=contact_email.setting_value if contact_email else '',
        contact_phone=contact_phone.setting_value if contact_phone else '',
        contact_address=contact_address.setting_value if contact_address else '',
        social_facebook=social_facebook.setting_value if social_facebook else '',
        social_tiktok=social_tiktok.setting_value if social_tiktok else '',
        social_instagram=social_instagram.setting_value if social_instagram else '',
        events=combined_events,  # Only upcoming/ongoing sport events + all regular events
        accomplishments=enriched_accomplishments
    )

# ==================== PUBLIC WEBSITE ROUTES ====================

@app.route('/')
def public_home():
    from datetime import datetime
    
    site_name = PublicSetting.query.filter_by(setting_key='site_name').first()
    site_logo = PublicSetting.query.filter_by(setting_key='site_logo').first()
    about_content = PublicSetting.query.filter_by(setting_key='about_content').first()
    mission = PublicSetting.query.filter_by(setting_key='mission').first()
    vision = PublicSetting.query.filter_by(setting_key='vision').first()
    contact_email = PublicSetting.query.filter_by(setting_key='contact_email').first()
    contact_phone = PublicSetting.query.filter_by(setting_key='contact_phone').first()
    contact_address = PublicSetting.query.filter_by(setting_key='contact_address').first()
    social_facebook = PublicSetting.query.filter_by(setting_key='social_facebook').first()
    social_tiktok = PublicSetting.query.filter_by(setting_key='social_tiktok').first()
    social_instagram = PublicSetting.query.filter_by(setting_key='social_instagram').first()
    
    # ========== UPCOMING EVENTS (FROM BOTH TABLES) ==========
    # Regular events
    regular_upcoming = Event.query.filter(Event.start_date >= datetime.now()).order_by(Event.start_date).limit(3).all()
    
    # Sport events (upcoming or ongoing)
    sport_upcoming = SportEvent.query.filter(
        SportEvent.status.in_(['upcoming', 'ongoing'])
    ).order_by(SportEvent.event_date).limit(3).all()
    
    # Combine and sort
    upcoming_events = []
    for event in regular_upcoming:
        upcoming_events.append({
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'date': event.start_date,
            'image': event.image_path,
            'type': 'regular'
        })
    
    for event in sport_upcoming:
        upcoming_events.append({
            'id': event.id,
            'title': event.name,
            'description': event.completed_description or 'Join us for this exciting event!',
            'date': event.event_date,
            'image': event.event_image,
            'type': 'sport'
        })
    
    # Sort by date
    upcoming_events.sort(key=lambda x: x['date'] if x['date'] else datetime.now())
    upcoming_events = upcoming_events[:3]  # Limit to 3
    
    # ========== RECENT ACCOMPLISHMENTS ==========
    recent_accomplishments_raw = Accomplishment.query.filter_by(status='approved').order_by(
        Accomplishment.accomplishment_date.desc()
    ).limit(3).all()
    
    recent_accomplishments = []
    for acc in recent_accomplishments_raw:
        participant_count = 0
        event_image = None
        
        if acc.event_id:
            sport_event = db.session.get(SportEvent, acc.event_id)
            if sport_event:
                participant_count = SportParticipant.query.filter_by(event_id=acc.event_id).count()
                event_image = sport_event.event_image
        
        recent_accomplishments.append({
            'id': acc.id,
            'title': acc.title,
            'description': acc.description,
            'accomplishment_date': acc.accomplishment_date,
            'file_path': acc.file_path,
            'event_image': event_image or acc.file_path,
            'participant_count': participant_count,
            'facebook_link': acc.facebook_link,
            'instagram_link': acc.instagram_link,
            'tiktok_link': acc.tiktok_link
        })
    
    current_officers = Officer.query.filter_by(is_current=True).order_by(Officer.order_rank).all()
    
    return render_template('public/index.html',
        site_name=site_name.setting_value if site_name else 'Our Organization',
        site_logo=site_logo.setting_value if site_logo else None,
        about_content=about_content.setting_value if about_content else '',
        mission=mission.setting_value if mission else '',
        vision=vision.setting_value if vision else '',
        contact_email=contact_email.setting_value if contact_email else None,
        contact_phone=contact_phone.setting_value if contact_phone else None,
        contact_address=contact_address.setting_value if contact_address else None,
        social_facebook=social_facebook.setting_value if social_facebook else None,
        social_tiktok=social_tiktok.setting_value if social_tiktok else None,
        social_instagram=social_instagram.setting_value if social_instagram else None,
        upcoming_events=upcoming_events,
        recent_accomplishments=recent_accomplishments,
        current_officers=current_officers
    )

@app.route('/about')
def public_about():
    about_content = PublicSetting.query.filter_by(setting_key='about_content').first()
    mission = PublicSetting.query.filter_by(setting_key='mission').first()
    vision = PublicSetting.query.filter_by(setting_key='vision').first()
    site_name = PublicSetting.query.filter_by(setting_key='site_name').first()
    contact_email = PublicSetting.query.filter_by(setting_key='contact_email').first()
    contact_phone = PublicSetting.query.filter_by(setting_key='contact_phone').first()
    contact_address = PublicSetting.query.filter_by(setting_key='contact_address').first()
    social_facebook = PublicSetting.query.filter_by(setting_key='social_facebook').first()
    social_tiktok = PublicSetting.query.filter_by(setting_key='social_tiktok').first()
    social_instagram = PublicSetting.query.filter_by(setting_key='social_instagram').first()
    
    return render_template('public/about.html',
        about_content=about_content.setting_value if about_content else '',
        mission=mission.setting_value if mission else '',
        vision=vision.setting_value if vision else '',
        site_name=site_name.setting_value if site_name else 'Our Organization',
        contact_email=contact_email.setting_value if contact_email else None,
        contact_phone=contact_phone.setting_value if contact_phone else None,
        contact_address=contact_address.setting_value if contact_address else None,
        social_facebook=social_facebook.setting_value if social_facebook else None,
        social_tiktok=social_tiktok.setting_value if social_tiktok else None,
        social_instagram=social_instagram.setting_value if social_instagram else None
    )

@app.route('/contact')
def public_contact():
    contact_email = PublicSetting.query.filter_by(setting_key='contact_email').first()
    contact_phone = PublicSetting.query.filter_by(setting_key='contact_phone').first()
    contact_address = PublicSetting.query.filter_by(setting_key='contact_address').first()
    social_facebook = PublicSetting.query.filter_by(setting_key='social_facebook').first()
    social_tiktok = PublicSetting.query.filter_by(setting_key='social_tiktok').first()  # CHANGED from social_tiktok
    social_instagram = PublicSetting.query.filter_by(setting_key='social_instagram').first()
    site_name = PublicSetting.query.filter_by(setting_key='site_name').first()
    
    return render_template('public/contact.html',
        contact_email=contact_email.setting_value if contact_email else None,
        contact_phone=contact_phone.setting_value if contact_phone else None,
        contact_address=contact_address.setting_value if contact_address else None,
        social_facebook=social_facebook.setting_value if social_facebook else None,
        social_tiktok=social_tiktok.setting_value if social_tiktok else None,  # CHANGED
        social_instagram=social_instagram.setting_value if social_instagram else None,
        site_name=site_name.setting_value if site_name else 'Our Organization'
    )

@app.route('/officers')
def public_officers():
    current_officers = Officer.query.filter_by(is_current=True).order_by(Officer.order_rank).all()
    previous_officers = Officer.query.filter_by(is_current=False).order_by(Officer.term_end.desc()).all()
    
    site_name = PublicSetting.query.filter_by(setting_key='site_name').first()
    contact_email = PublicSetting.query.filter_by(setting_key='contact_email').first()
    contact_phone = PublicSetting.query.filter_by(setting_key='contact_phone').first()
    contact_address = PublicSetting.query.filter_by(setting_key='contact_address').first()
    social_facebook = PublicSetting.query.filter_by(setting_key='social_facebook').first()
    social_tiktok = PublicSetting.query.filter_by(setting_key='social_tiktok').first()
    social_instagram = PublicSetting.query.filter_by(setting_key='social_instagram').first()
    
    return render_template('public/officers.html', 
        current_officers=current_officers,
        previous_officers=previous_officers,
        site_name=site_name.setting_value if site_name else 'Our Organization',
        contact_email=contact_email.setting_value if contact_email else None,
        contact_phone=contact_phone.setting_value if contact_phone else None,
        contact_address=contact_address.setting_value if contact_address else None,
        social_facebook=social_facebook.setting_value if social_facebook else None,
        social_tiktok=social_tiktok.setting_value if social_tiktok else None,
        social_instagram=social_instagram.setting_value if social_instagram else None
    )

@app.route('/events')
def public_events():
    from datetime import datetime
    
    # Regular events
    regular_upcoming = Event.query.filter(Event.start_date >= datetime.now()).order_by(Event.start_date).all()
    regular_past = Event.query.filter(Event.start_date < datetime.now()).order_by(Event.start_date.desc()).all()
    
    # Sport events
    sport_upcoming = SportEvent.query.filter(
        SportEvent.status.in_(['upcoming', 'ongoing'])
    ).order_by(SportEvent.event_date).all()
    
    sport_past = SportEvent.query.filter_by(status='completed').order_by(SportEvent.event_date.desc()).all()
    
    # Combine upcoming events
    upcoming_events = []
    for event in regular_upcoming:
        upcoming_events.append({
            'id': event.id,
            'title': event.title,
            'description': event.description or 'Join us for this exciting event!',
            'date': event.start_date,
            'image': event.image_path,
            'type': 'regular'
        })
    
    for event in sport_upcoming:
        upcoming_events.append({
            'id': event.id,
            'title': event.name,
            'description': event.completed_description or 'Join us for this exciting event!',
            'date': event.event_date,
            'image': event.event_image,
            'type': 'sport'
        })
    
    upcoming_events.sort(key=lambda x: x['date'] if x['date'] else datetime.now())
    
    # Combine past events
    past_events = []
    for event in regular_past:
        past_events.append({
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'date': event.start_date,
            'image': event.image_path,
            'type': 'regular'
        })
    
    for event in sport_past:
        past_events.append({
            'id': event.id,
            'title': event.name,
            'description': event.completed_description or 'Completed event',
            'date': event.event_date,
            'image': event.event_image,
            'type': 'sport'
        })
    
    past_events.sort(key=lambda x: x['date'] if x['date'] else datetime.now(), reverse=True)
    
    site_name = PublicSetting.query.filter_by(setting_key='site_name').first()
    contact_email = PublicSetting.query.filter_by(setting_key='contact_email').first()
    contact_phone = PublicSetting.query.filter_by(setting_key='contact_phone').first()
    contact_address = PublicSetting.query.filter_by(setting_key='contact_address').first()
    social_facebook = PublicSetting.query.filter_by(setting_key='social_facebook').first()
    social_tiktok = PublicSetting.query.filter_by(setting_key='social_tiktok').first()
    social_instagram = PublicSetting.query.filter_by(setting_key='social_instagram').first()
    
    return render_template('public/events.html', 
        upcoming_events=upcoming_events,
        past_events=past_events,
        site_name=site_name.setting_value if site_name else 'Our Organization',
        contact_email=contact_email.setting_value if contact_email else None,
        contact_phone=contact_phone.setting_value if contact_phone else None,
        contact_address=contact_address.setting_value if contact_address else None,
        social_facebook=social_facebook.setting_value if social_facebook else None,
        social_tiktok=social_tiktok.setting_value if social_tiktok else None,
        social_instagram=social_instagram.setting_value if social_instagram else None
    )

@app.route('/event/<int:id>')
def public_event_detail(id):
    # Try to find in regular events first
    event = Event.query.get(id)
    if event:
        return render_template('public/event_detail.html',
            event=event,
            event_type='regular',
            site_name=PublicSetting.query.filter_by(setting_key='site_name').first().setting_value if PublicSetting.query.filter_by(setting_key='site_name').first() else 'Our Organization'
        )
    
    # Try to find in sport events
    sport_event = SportEvent.query.get(id)
    if sport_event:
        return render_template('public/event_detail.html',
            event=sport_event,
            event_type='sport',
            site_name=PublicSetting.query.filter_by(setting_key='site_name').first().setting_value if PublicSetting.query.filter_by(setting_key='site_name').first() else 'Our Organization'
        )
    
    flash('Event not found.', 'danger')
    return redirect(url_for('public_events'))

@app.route('/accomplishments')
def public_accomplishments():
    # Get approved accomplishments
    accomplishments = Accomplishment.query.filter_by(status='approved').order_by(
        Accomplishment.accomplishment_date.desc()
    ).all()
    
    # Enrich accomplishments with event data
    enriched_accomplishments = []
    for acc in accomplishments:
        participant_count = 0
        event_image = None
        event_facebook = None
        event_instagram = None
        event_tiktok = None
        
        if acc.event_id:
            sport_event = db.session.get(SportEvent, acc.event_id)
            if sport_event:
                participant_count = SportParticipant.query.filter_by(event_id=acc.event_id).count()
                event_image = sport_event.event_image
                event_facebook = sport_event.facebook_link
                event_instagram = sport_event.instagram_link
                event_tiktok = sport_event.tiktok_link
        
        acc_data = {
            'id': acc.id,
            'title': acc.title,
            'description': acc.description,
            'accomplishment_date': acc.accomplishment_date,
            'file_path': acc.file_path,
            'event_image': event_image or acc.file_path,
            'participant_count': participant_count,
            'facebook_link': acc.facebook_link or event_facebook,
            'instagram_link': acc.instagram_link or event_instagram,
            'tiktok_link': acc.tiktok_link or event_tiktok
        }
        enriched_accomplishments.append(acc_data)
    
    # Get site settings
    site_name = PublicSetting.query.filter_by(setting_key='site_name').first()
    contact_email = PublicSetting.query.filter_by(setting_key='contact_email').first()
    contact_phone = PublicSetting.query.filter_by(setting_key='contact_phone').first()
    contact_address = PublicSetting.query.filter_by(setting_key='contact_address').first()
    social_facebook = PublicSetting.query.filter_by(setting_key='social_facebook').first()
    social_tiktok = PublicSetting.query.filter_by(setting_key='social_tiktok').first()
    social_instagram = PublicSetting.query.filter_by(setting_key='social_instagram').first()
    
    return render_template('public/accomplishments.html',
        accomplishments=enriched_accomplishments,
        site_name=site_name.setting_value if site_name else 'Our Organization',
        contact_email=contact_email.setting_value if contact_email else None,
        contact_phone=contact_phone.setting_value if contact_phone else None,
        contact_address=contact_address.setting_value if contact_address else None,
        social_facebook=social_facebook.setting_value if social_facebook else None,
        social_tiktok=social_tiktok.setting_value if social_tiktok else None,
        social_instagram=social_instagram.setting_value if social_instagram else None
    )

@app.route('/accomplishment/<int:id>')
def public_accomplishment_detail(id):
    accomplishment = Accomplishment.query.get_or_404(id)
    
    # Get event details if exists
    participant_count = 0
    event_image = None
    event_facebook = None
    event_instagram = None
    event_tiktok = None
    
    if accomplishment.event_id:
        sport_event = db.session.get(SportEvent, accomplishment.event_id)
        if sport_event:
            participant_count = SportParticipant.query.filter_by(event_id=accomplishment.event_id).count()
            event_image = sport_event.event_image
            event_facebook = sport_event.facebook_link
            event_instagram = sport_event.instagram_link
            event_tiktok = sport_event.tiktok_link
    
    site_name = PublicSetting.query.filter_by(setting_key='site_name').first()
    contact_email = PublicSetting.query.filter_by(setting_key='contact_email').first()
    contact_phone = PublicSetting.query.filter_by(setting_key='contact_phone').first()
    contact_address = PublicSetting.query.filter_by(setting_key='contact_address').first()
    social_facebook = PublicSetting.query.filter_by(setting_key='social_facebook').first()
    social_tiktok = PublicSetting.query.filter_by(setting_key='social_tiktok').first()
    social_instagram = PublicSetting.query.filter_by(setting_key='social_instagram').first()
    
    return render_template('public/accomplishment_detail.html',
        accomplishment=accomplishment,
        participant_count=participant_count,
        event_image=event_image,
        facebook_link=accomplishment.facebook_link or event_facebook,
        instagram_link=accomplishment.instagram_link or event_instagram,
        tiktok_link=accomplishment.tiktok_link or event_tiktok,
        site_name=site_name.setting_value if site_name else 'Our Organization',
        contact_email=contact_email.setting_value if contact_email else None,
        contact_phone=contact_phone.setting_value if contact_phone else None,
        contact_address=contact_address.setting_value if contact_address else None,
        social_facebook=social_facebook.setting_value if social_facebook else None,
        social_tiktok=social_tiktok.setting_value if social_tiktok else None,
        social_instagram=social_instagram.setting_value if social_instagram else None
    )

@app.route('/contact/submit', methods=['POST'])
def public_contact_submit():
    name = request.form.get('name')
    email = request.form.get('email')
    subject = request.form.get('subject')
    message = request.form.get('message')
    
    # Save to database
    contact = ContactMessage(
        name=name,
        email=email,
        subject=subject,
        message=message
    )
    db.session.add(contact)
    db.session.commit()
    
    flash('Thank you for your message! We will get back to you soon.', 'success')
    return redirect(url_for('public_contact'))

# ==================== CONTEXT PROCESSORS ====================

@app.context_processor
def inject_settings():
    return {
        'org_name': (SystemSetting.query.filter_by(setting_key='org_name').first().setting_value if SystemSetting.query.filter_by(setting_key='org_name').first() else 'Sitio Verdant Hills Youth Organization'),
        'logo_url': (SystemSetting.query.filter_by(setting_key='logo_url').first().setting_value if SystemSetting.query.filter_by(setting_key='logo_url').first() else None),
        'theme': (SystemSetting.query.filter_by(setting_key='theme').first().setting_value if SystemSetting.query.filter_by(setting_key='theme').first() else 'light'),
        'primary_color': (SystemSetting.query.filter_by(setting_key='primary_color').first().setting_value if SystemSetting.query.filter_by(setting_key='primary_color').first() else '#4CAF50')
    }

@app.context_processor
def inject_unread_count():
    if current_user.is_authenticated and current_user.role in ['President', 'Secretary']:
        unread_count = ContactMessage.query.filter_by(is_read=False).count()
        return {'unread_messages_count': unread_count}
    return {'unread_messages_count': 0}

# ==================== INIT ====================
def init_db():
    with app.app_context():
        db.create_all()
        print("✅ All database tables created/verified!")
        
        # Create or update admin user
        admin = User.query.filter_by(username='admin').first()
        if admin:
            # Update existing admin password
            admin.set_password('1214f143l')
            admin.role = 'System Administrator'
            admin.full_name = 'System Administrator'
            admin.email = 'admin@svhyo.com'
            db.session.commit()
            print("✅ Admin password updated to: 1214f143l")
        else:
            # Create new admin
            admin = User(
                username='admin',
                role='System Administrator',
                full_name='System Administrator',
                email='admin@svhyo.com'
            )
            admin.set_password('1214f143l')
            db.session.add(admin)
            db.session.commit()
            print("✅ Default admin user created - Username: admin, Password: 1214f143l")
        
        # Create default public settings if they don't exist
        if not PublicSetting.query.first():
            default_settings = [
                {'setting_key': 'site_name', 'setting_value': 'Sitio Verdant Hills Youth Organization'},
                {'setting_key': 'site_logo', 'setting_value': ''},
                {'setting_key': 'about_content', 'setting_value': 'Welcome to Sitio Verdant Hills Youth Organization. We are committed to serving our community and developing future leaders.'},
                {'setting_key': 'mission', 'setting_value': 'To empower the youth through leadership development, community service, and excellence.'},
                {'setting_key': 'vision', 'setting_value': 'A community of empowered youth leaders building a better future.'},
                {'setting_key': 'contact_email', 'setting_value': 'contact@svhyo.com'},
                {'setting_key': 'contact_phone', 'setting_value': '+63 912 345 6789'},
                {'setting_key': 'contact_address', 'setting_value': 'Sitio Verdant Hills, Brgy. Pasong Tamo, Quezon City'},
                {'setting_key': 'social_facebook', 'setting_value': ''},
                {'setting_key': 'social_tiktok', 'setting_value': ''},
                {'setting_key': 'social_instagram', 'setting_value': ''},
            ]
            for setting in default_settings:
                new_setting = PublicSetting(
                    setting_key=setting['setting_key'],
                    setting_value=setting['setting_value'],
                    setting_type='text'
                )
                db.session.add(new_setting)
            db.session.commit()
            print("✅ Default public settings created!")
        else:
            print("✅ Public settings already exist!")
            
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)