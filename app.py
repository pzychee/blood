from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from geopy.distance import geodesic
import os
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blood_donation.db'
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # donor, recipient, admin
    name = db.Column(db.String(100), nullable=False)
    blood_type = db.Column(db.String(5))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    last_donation = db.Column(db.DateTime)
    is_available = db.Column(db.Boolean, default=True)
    health_conditions = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BloodRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    donor_email = db.Column(db.String(120))
    blood_type = db.Column(db.String(5), nullable=False)
    units_needed = db.Column(db.Integer, nullable=False)
    urgency = db.Column(db.String(20), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BloodBank(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    inventory = db.Column(db.JSON)
    contact = db.Column(db.String(100))

class Donation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    donor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blood_type = db.Column(db.String(5), nullable=False)
    units = db.Column(db.Integer, nullable=False)
    donation_date = db.Column(db.DateTime, default=datetime.utcnow)

    donor = db.relationship('User', backref='donations')


with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        name = request.form.get('name')
        blood_type = request.form.get('blood_type')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('register'))
        
        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            name=name,
            blood_type=blood_type
        )
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')  # Get the role from the form
        
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Verify the role matches
            if user.role == role:
                login_user(user)
                return redirect(url_for('dashboard'))
            else:
                flash(f'This email is not registered as a {role}')
                return redirect(url_for('login', error=f'This email is not registered as a {role}', role=role))
        
        flash('Invalid email or password')
        return redirect(url_for('login', error='Invalid email or password', role=role))
    
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'donor':
        nearby_requests = BloodRequest.query.filter_by(blood_type=current_user.blood_type, status='pending').all()
        donations = Donation.query.filter_by(donor_id=current_user.id).all()
        return render_template('donor_dashboard.html', current_user=current_user,
                               requests=nearby_requests, donations=donations,
                               current_time=datetime.utcnow())
    elif current_user.role == 'recipient':
        my_requests = BloodRequest.query.filter_by(recipient_id=current_user.id).all()
        return render_template('recipient_dashboard.html', requests=my_requests)
    elif current_user.role == 'admin':
        blood_banks = BloodBank.query.all()
        
        # Calculate total available stock
        total_stock = {
            'A+': 0, 'A-': 0, 'B+': 0, 'B-': 0, 
            'AB+': 0, 'AB-': 0, 'O+': 0, 'O-': 0
        }
        for bank in blood_banks:
            for blood_type, units in bank.inventory.items():
                total_stock[blood_type] += units
        
        donations = Donation.query.order_by(Donation.donation_date.desc()).all()
        blood_requests = BloodRequest.query.all()  # Fetch all blood requests
        return render_template('admin_dashboard.html', blood_banks=blood_banks, donations=donations, total_stock=total_stock, blood_requests=blood_requests)
    
@app.route('/create_request', methods=['GET', 'POST'])
@login_required
def create_request():
    if request.method == 'POST':
        blood_request = BloodRequest(
            recipient_id=current_user.id,
            blood_type=request.form.get('blood_type'),
            units_needed=request.form.get('units_needed'),
            urgency=request.form.get('urgency'),
            latitude=12.9716,
            longitude=77.5946
        )
        db.session.add(blood_request)
        db.session.commit()
        flash('Blood request created successfully')
        return redirect(url_for('dashboard'))
    
    return render_template('create_request.html')
@app.route('/add_dummy_bank')
def add_dummy_bank():
    bank = BloodBank(
        name="Red Cross Center",
        latitude=12.9716,
        longitude=77.5946,
        inventory={
            'A+': 12, 'A-': 3, 'B+': 8, 'B-': 4, 
            'AB+': 6, 'AB-': 1, 'O+': 20, 'O-': 5
        },
        contact="123-456-7890"
    )
    db.session.add(bank)
    db.session.commit()
    return "Dummy blood bank added!"

@app.route('/respond_to_request/<int:request_id>', methods=['POST'])
@login_required
def respond_to_request(request_id):
    request = BloodRequest.query.get_or_404(request_id)
    if request.status == 'pending':
        request.status = 'responded'
        request.donor_email = current_user.email  # Capture the donor's email
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Request is not pending'}), 400
    

@app.route('/fulfill_request/<int:request_id>', methods=['GET', 'POST'])
@login_required
def fulfill_request(request_id):
    if current_user.role != 'admin':
        flash('You are not authorized to access this page.')
        return redirect(url_for('dashboard'))

    blood_request = BloodRequest.query.get_or_404(request_id)
    blood_type = blood_request.blood_type
    units_needed = blood_request.units_needed

    # Check if the requested blood type and units are available in any bank
    blood_banks = BloodBank.query.all()
    for bank in blood_banks:
        if bank.inventory.get(blood_type, 0) >= units_needed:
            # Update the bank's inventory
            bank.inventory[blood_type] -= units_needed
            db.session.commit()

            # Update the request status and donor email
            blood_request.status = 'fulfilled'
            donor = User.query.filter_by(role='donor', blood_type=blood_type, is_available=True).first()
            if donor:
                blood_request.donor_email = donor.email
                db.session.commit()

                flash('Blood request fulfilled successfully')
                return redirect(url_for('dashboard'))
            else:
                flash('No available donor found for this blood type')
                return redirect(url_for('dashboard'))

    flash('Insufficient blood stock to fulfill the request')
    return redirect(url_for('dashboard'))

@app.route('/delete_request/<int:request_id>', methods=['POST'])
@login_required
def delete_request(request_id):
    request = BloodRequest.query.get_or_404(request_id)
    if request.recipient_id != current_user.id:
        flash('You are not authorized to delete this request.')
        return redirect(url_for('dashboard'))
    
    db.session.delete(request)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/update_bank_stock/<int:bank_id>', methods=['GET', 'POST'])
@login_required
def update_bank_stock(bank_id):
    if current_user.role != 'admin':
        flash('You are not authorized to access this page.')
        return redirect(url_for('dashboard'))

    blood_bank = BloodBank.query.get_or_404(bank_id)

    if request.method == 'POST':
        # Update the blood bank stock
        blood_bank.inventory = {
            'A+': int(request.form.get('A+')),
            'A-': int(request.form.get('A-')),
            'B+': int(request.form.get('B+')),
            'B-': int(request.form.get('B-')),
            'AB+': int(request.form.get('AB+')),
            'AB-': int(request.form.get('AB-')),
            'O+': int(request.form.get('O+')),
            'O-': int(request.form.get('O-'))
        }
        db.session.commit()
        flash('Blood bank stock updated successfully')
        return redirect(url_for('dashboard'))

    return render_template('update_bank_stock.html', blood_bank=blood_bank)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True,host="0.0.0.0",port=5000)