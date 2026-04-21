from flask import Blueprint, request, jsonify
from utils.auth import AuthService
from werkzeug.utils import secure_filename
import os
from datetime import datetime

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/signup', methods=['POST'])
def signup():
    """User signup endpoint with full profile data"""
    try:
        # Handle both form-data and JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form
            file = request.files.get('photo')
        else:
            data = request.get_json()
            file = None
        
        # Validate required fields
        required_fields = ['full_name', 'email', 'password', 'phone']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {field}'
                }), 400
        
        # Handle profile photo upload
        photo_url = None
        if file:
            filename = secure_filename(file.filename)
            timestamp = datetime.now().timestamp()
            file_path = f"profile_photos/{timestamp}_{filename}"
            
            # Upload to Supabase storage
            from utils.db import db
            file_content = file.read()
            db.client.storage.from_('profiles').upload(file_path, file_content)
            
            # Get public URL
            photo_url = db.client.storage.from_('profiles').get_public_url(file_path)
        
        # Prepare user data according to your schema
        user_data = {
            'full_name': data.get('full_name'),
            'phone': data.get('phone'),
            'date_of_birth': data.get('date_of_birth'),  # Format: YYYY-MM-DD
            'faculty': data.get('faculty'),
            'department': data.get('department'),
            'photo_url': photo_url,
            'onboarding_completed': data.get('onboarding_completed', False)
        }
        
        user, message, referral_code = AuthService.signup_user(
            email=data.get('email'),
            password=data.get('password'),
            user_data=user_data
        )
        
        if user:
            return jsonify({
                'success': True,
                'message': message,
                'user_id': user.id,
                'email': user.email,
                'referral_code': referral_code
            }), 201
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """User login endpoint"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({
                'success': False,
                'message': 'Email and password are required'
            }), 400
        
        user, session, error = AuthService.login_user(email, password)
        
        if user:
            # Get full profile data
            profile, profile_error = AuthService.get_user_profile(user.id)
            
            return jsonify({
                'success': True,
                'message': 'Login successful',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'profile': profile
                },
                'access_token': session.access_token,
                'refresh_token': session.refresh_token,
                'expires_at': session.expires_at
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': error or 'Invalid credentials'
            }), 401
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """User logout endpoint"""
    try:
        auth_header = request.headers.get('Authorization')
        if auth_header:
            token = auth_header.split(' ')[1]
            from utils.db import db
            db.client.auth.sign_out()
        
        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@auth_bp.route('/refresh-token', methods=['POST'])
def refresh_token():
    """Refresh access token"""
    try:
        data = request.get_json()
        refresh_token = data.get('refresh_token')
        
        if not refresh_token:
            return jsonify({'success': False, 'message': 'Refresh token required'}), 400
        
        from utils.db import db
        session = db.client.auth.refresh_session(refresh_token)
        
        return jsonify({
            'success': True,
            'access_token': session.access_token,
            'refresh_token': session.refresh_token,
            'expires_at': session.expires_at
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 401

@auth_bp.route('/verify-email', methods=['POST'])
def verify_email():
    """Verify user email"""
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'message': 'Email required'}), 400
        
        from utils.db import db
        # Send email verification
        db.client.auth.reset_password_for_email(email)
        
        return jsonify({
            'success': True,
            'message': 'Verification email sent'
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Reset user password"""
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'message': 'Email required'}), 400
        
        from utils.db import db
        db.client.auth.reset_password_for_email(email)
        
        return jsonify({
            'success': True,
            'message': 'Password reset email sent'
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500