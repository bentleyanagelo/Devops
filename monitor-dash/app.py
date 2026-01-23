# app.py
from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import pandas as pd
import plotly
import plotly.express as px
import json
import threading
import time
import os
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Data Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='user')  # admin, user, viewer
    
class Computer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(15), nullable=False)
    mac_address = db.Column(db.String(17))
    location = db.Column(db.String(200))
    department = db.Column(db.String(100))
    owner = db.Column(db.String(100))
    status = db.Column(db.String(20), default='unknown')  # online, offline, warning
    last_seen = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class DowntimeEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    computer_id = db.Column(db.Integer, db.ForeignKey('computer.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime)
    duration_minutes = db.Column(db.Float)
    reason = db.Column(db.String(200))
    resolved_by = db.Column(db.String(100))
    notes = db.Column(db.Text)
    
    computer = db.relationship('Computer', backref=db.backref('downtime_events', lazy=True))

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    computer_id = db.Column(db.Integer, db.ForeignKey('computer.id'), nullable=False)
    alert_type = db.Column(db.String(50))  # downtime, performance, security
    severity = db.Column(db.String(20))  # critical, high, medium, low
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    acknowledged = db.Column(db.Boolean, default=False)
    acknowledged_by = db.Column(db.String(100))
    acknowledged_at = db.Column(db.DateTime)
    
    computer = db.relationship('Computer', backref=db.backref('alerts', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Monitoring System
class ComputerMonitor:
    def __init__(self):
        self.running = False
        self.thread = None
   
    def ping_computer(self, computer):
        """Check computer status using ping"""
        try:
            import subprocess
            import platform
            
            # Ping parameters based on OS
            system = platform.system().lower()
            if system == 'windows':
                # Windows: ping -n 1 -w 3000 <IP>
                # Increased to 3 seconds (3000ms)
                command = ['ping', '-n', '1', '-w', '1000', computer.ip_address]
            else:
                # Linux/Mac: ping -c 1 -W 3 <IP>
                # Increased to 3 seconds
                command = ['ping', '-c', '1', '-W', '3', computer.ip_address]
            
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            
            if system == 'windows':
                # Windows ping returns 0 for "Destination host unreachable"
                # We need to check for "TTL=" to confirm successful reply
                output = result.stdout.decode('utf-8', errors='ignore')
                is_online = result.returncode == 0 and 'TTL=' in output.upper()
            else:
                is_online = result.returncode == 0
            
            # Enhanced logging
            if is_online:
                print(f"[DEBUG] Ping {computer.ip_address} ({computer.name}): SUCCESS")
            else:
                print(f"[DEBUG] Ping {computer.ip_address} ({computer.name}): FAILED (return code: {result.returncode})")
                print(f"[DEBUG] stderr: {result.stderr.decode()}")
            
            return is_online
        except subprocess.TimeoutExpired:
            print(f"[DEBUG] Ping {computer.ip_address} ({computer.name}): TIMEOUT - subprocess exceeded 5 seconds")
            return False
        except Exception as e:
            print(f"[DEBUG] Ping {computer.ip_address} ({computer.name}): ERROR - {str(e)}")
            return False


   
            
 
    
    def check_all_computers(self):
        """Check all computers"""
        with app.app_context():
            computers = Computer.query.all()
            print(f"[MONITORING] Checking {len(computers)} computers...")
            
            for computer in computers:
                try:
                    was_online = computer.status == 'online'
                    is_online = self.ping_computer(computer)
                    
                    if was_online != is_online:
                        print(f"[STATUS CHANGE] {computer.name} ({computer.ip_address}): {computer.status} -> {'online' if is_online else 'offline'}")
                    
                    computer.last_seen = datetime.utcnow() if is_online else computer.last_seen
                    computer.status = 'online' if is_online else 'offline'
                    
                    # Record downtime event
                    if was_online and not is_online:
                        # Downtime started
                        downtime = DowntimeEvent(
                            computer_id=computer.id,
                            start_time=datetime.utcnow(),
                            reason='Connection lost'
                        )
                        db.session.add(downtime)
                        
                        # Create alert
                        alert = Alert(
                            computer_id=computer.id,
                            alert_type='downtime',
                            severity='high',
                            message=f'Computer {computer.name} is offline'
                        )
                        db.session.add(alert)
                        
                    elif not was_online and is_online:
                        # Downtime ended
                        downtime = DowntimeEvent.query.filter_by(
                            computer_id=computer.id,
                            end_time=None
                        ).first()
                        if downtime:
                            downtime.end_time = datetime.utcnow()
                            duration = (downtime.end_time - downtime.start_time).total_seconds() / 60
                            downtime.duration_minutes = duration
                            
                            # Update alert
                            alert = Alert.query.filter_by(
                                computer_id=computer.id,
                                acknowledged=False
                            ).first()
                            if alert:
                                alert.acknowledged = True
                                alert.acknowledged_at = datetime.utcnow()
                    
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    print(f"[MONITORING ERROR] Error updating {computer.name}: {str(e)}")
    
    def start_monitoring(self):
        """Start monitoring system"""
        self.running = True
        def monitor_loop():
            while self.running:
                with app.app_context():
                    self.check_all_computers()
                time.sleep(app.config['PING_INTERVAL'])
        
        self.thread = threading.Thread(target=monitor_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def stop_monitoring(self):
        """Stop monitoring system"""
        self.running = False
        if self.thread:
            self.thread.join()

monitor = ComputerMonitor()

# Application Routes
@app.route('/')
@login_required
def dashboard():
    """Main dashboard page"""
    total_computers = Computer.query.count()
    online_computers = Computer.query.filter_by(status='online').count()
    offline_computers = Computer.query.filter_by(status='offline').count()
    
    # Recent downtimes
    recent_downtimes = DowntimeEvent.query.order_by(
        DowntimeEvent.start_time.desc()
    ).limit(10).all()
    
    # Active alerts
    active_alerts = Alert.query.filter_by(
        acknowledged=False
    ).order_by(Alert.created_at.desc()).limit(5).all()
    
    # Chart data
    downtime_data = calculate_downtime_stats()
    
    return render_template('dashboard.html',
                         total_computers=total_computers,
                         online_computers=online_computers,
                         offline_computers=offline_computers,
                         recent_downtimes=recent_downtimes,
                         active_alerts=active_alerts,
                         downtime_data=json.dumps(downtime_data))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/computers')
@login_required
def get_computers():
    """API to get computer data"""
    computers = Computer.query.all()
    result = []
    for computer in computers:
        result.append({
            'id': computer.id,
            'name': computer.name,
            'ip': computer.ip_address,
            'status': computer.status,
            'location': computer.location,
            'department': computer.department,
            'last_seen': computer.last_seen.isoformat() if computer.last_seen else None,
            'downtime_count': len(computer.downtime_events)
        })
    return jsonify(result)

def calculate_downtime_stats():
    """Calculate downtime statistics - utility function"""
    # Downtime by day (last 7 days)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)
    
    downtime_stats = db.session.query(
        db.func.date(DowntimeEvent.start_time).label('date'),
        db.func.count(DowntimeEvent.id).label('count'),
        db.func.sum(DowntimeEvent.duration_minutes).label('total_duration')
    ).filter(
        DowntimeEvent.start_time >= start_date,
        DowntimeEvent.end_time.isnot(None)
    ).group_by(
        db.func.date(DowntimeEvent.start_time)
    ).order_by('date').all()
    
    dates = [stat.date for stat in downtime_stats]
    counts = [stat.count for stat in downtime_stats]
    durations = [stat.total_duration or 0 for stat in downtime_stats]
    
    # Top 5 computers with most downtime
    top_downtime = db.session.query(
        Computer.name,
        db.func.count(DowntimeEvent.id).label('event_count'),
        db.func.sum(DowntimeEvent.duration_minutes).label('total_duration')
    ).join(DowntimeEvent).group_by(Computer.id).order_by(
        db.desc('total_duration')
    ).limit(5).all()
    
    return {
        'dates': dates,
        'counts': counts,
        'durations': durations,
        'top_downtime': [
            {
                'name': item[0],
                'events': item[1],
                'duration': item[2] or 0
            } for item in top_downtime
        ]
    }

@app.route('/api/downtime/stats')
@login_required
def get_downtime_stats():
    """API for downtime statistics"""
    return jsonify(calculate_downtime_stats())

@app.route('/api/downtime/export')
@login_required
def export_downtime():
    """Export downtime data"""
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = DowntimeEvent.query.join(Computer)
    
    if start_date:
        query = query.filter(DowntimeEvent.start_time >= start_date)
    if end_date:
        query = query.filter(DowntimeEvent.start_time <= end_date)
    
    downtime_data = query.all()
    
    # Create DataFrame
    data = []
    for event in downtime_data:
        data.append({
            'Computer': event.computer.name,
            'Start Time': event.start_time,
            'End Time': event.end_time,
            'Duration (minutes)': event.duration_minutes,
            'Reason': event.reason
        })
    
    df = pd.DataFrame(data)
    
    # Export to Excel in instance directory
    output_path = os.path.join(app.config.get('INSTANCE_DIR', 'instance'), 'downtime_report.xlsx')
    output = pd.ExcelWriter(output_path, engine='xlsxwriter')
    df.to_excel(output, sheet_name='Downtime Report', index=False)
    output.close()
    
    return jsonify({'message': 'Report exported successfully'})

@app.route('/add_computer', methods=['POST'])
@login_required
def add_computer():
    """Add a new computer"""
    data = request.json
    computer = Computer(
        name=data['name'],
        ip_address=data['ip_address'].strip(),
        mac_address=data.get('mac_address'),
        location=data.get('location'),
        department=data.get('department'),
        owner=data.get('owner'),
        status='unknown'
    )
    db.session.add(computer)
    db.session.commit()
    
    # Perform immediate ping check
    is_online = monitor.ping_computer(computer)
    computer.status = 'online' if is_online else 'offline'
    computer.last_seen = datetime.utcnow() if is_online else None
    db.session.commit()
    
    print(f"[ADD COMPUTER] {computer.name} ({computer.ip_address}): {computer.status}")
    
    return jsonify({'message': 'Computer added successfully', 'status': computer.status})

@app.route('/delete_computer/<int:computer_id>', methods=['POST', 'DELETE'])
@login_required
def delete_computer(computer_id):
    """Delete a computer and its associated records"""
    computer = Computer.query.get_or_404(computer_id)
    
    # Store info for logging
    computer_name = computer.name
    computer_ip = computer.ip_address
    
    try:
        # Delete all associated alerts
        Alert.query.filter_by(computer_id=computer_id).delete()
        
        # Delete all associated downtime events
        DowntimeEvent.query.filter_by(computer_id=computer_id).delete()
        
        # Delete the computer
        db.session.delete(computer)
        db.session.commit()
        
        print(f"[DELETE COMPUTER] Deleted {computer_name} ({computer_ip})")
        
        return jsonify({
            'message': f'Computer {computer_name} deleted successfully',
            'success': True
        })
    except Exception as e:
        db.session.rollback()
        print(f"[DELETE ERROR] Failed to delete computer {computer_name}: {str(e)}")
        return jsonify({
            'message': f'Error deleting computer: {str(e)}',
            'success': False
        }), 500

@app.route('/acknowledge_alert/<int:alert_id>', methods=['POST'])
@login_required
def acknowledge_alert(alert_id):
    """Acknowledge an alert"""
    alert = Alert.query.get_or_404(alert_id)
    alert.acknowledged = True
    alert.acknowledged_by = current_user.username
    alert.acknowledged_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': 'Alert acknowledged'})

# Initialization functions
def init_db():
    """Initialize database"""
    with app.app_context():
        db.create_all()
        
        # Create default admin user (development only)
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@example.com',
                password=generate_password_hash('admin123'),
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()

def start_monitoring():
    """Start monitoring system"""
    monitor.start_monitoring()
    
# Add these routes to app.py

@app.route('/api/computer/<int:computer_id>')
@login_required
def get_computer_details(computer_id):
    """Get detailed information about a specific computer"""
    computer = Computer.query.get_or_404(computer_id)
    return jsonify({
        'id': computer.id,
        'name': computer.name,
        'ip': computer.ip_address,
        'mac_address': computer.mac_address,
        'status': computer.status,
        'location': computer.location,
        'department': computer.department,
        'owner': computer.owner,
        'created_at': computer.created_at.isoformat(),
        'last_seen': computer.last_seen.isoformat() if computer.last_seen else None
    })

@app.route('/api/computer/<int:computer_id>/downtime')
@login_required
def get_computer_downtime(computer_id):
    """Get downtime history for a specific computer"""
    downtime_events = DowntimeEvent.query.filter_by(
        computer_id=computer_id
    ).order_by(DowntimeEvent.start_time.desc()).limit(20).all()
    
    result = []
    for event in downtime_events:
        result.append({
            'start_time': event.start_time.isoformat(),
            'end_time': event.end_time.isoformat() if event.end_time else None,
            'duration_minutes': event.duration_minutes,
            'reason': event.reason
        })
    
    return jsonify(result)

@app.route('/api/computer/<int:computer_id>/ping', methods=['POST'])
@login_required
def manual_ping_computer(computer_id):
    """Manually ping a computer"""
    computer = Computer.query.get_or_404(computer_id)
    monitor = ComputerMonitor()
    is_online = monitor.ping_computer(computer)
    
    # Update status in database
    computer.last_seen = datetime.utcnow() if is_online else computer.last_seen
    computer.status = 'online' if is_online else 'offline'
    db.session.commit()
    
    print(f"[MANUAL PING] {computer.name} ({computer.ip_address}): {'ONLINE' if is_online else 'OFFLINE'}")
    
    return jsonify({'success': is_online, 'status': computer.status})    

if __name__ == '__main__':
    init_db()
    start_monitoring()
    app.run(debug=True, host='0.0.0.0', port=5000)