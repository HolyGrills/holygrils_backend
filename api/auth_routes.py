from flask import Blueprint, request, jsonify
from utils.auth import AuthService
from werkzeug.utils import secure_filename
from datetime import datetime

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/signup', methods=['POST'])
def signup():
    """
    User signup with full profile data
    ---
    tags:
      - Auth
    consumes:
      - multipart/form-data
      - application/json
    parameters:
      - in: formData
        name: full_name
        type: string
        required: true
      - in: formData
        name: email
        type: string
        required: true
      - in: formData
        name: password
        type: string
        required: true
      - in: formData
        name: phone
        type: string
        required: true
      - in: formData
        name: date_of_birth
        type: string
        description: Format YYYY-MM-DD
      - in: formData
        name: faculty
        type: string
      - in: formData
        name: department
        type: string
      - in: formData
        name: onboarding_completed
        type: boolean
      - in: formData
        name: photo
        type: file
        description: Profile photo upload
    responses:
      201:
        description: User created successfully
        schema:
          properties:
            success: {type: boolean}
            message: {type: string}
            user_id: {type: string}
            email: {type: string}
            referral_code: {type: string}
      400:
        description: Missing fields or signup error
      500:
        description: Server error
    """
    try:
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.form
            file = request.files.get('photo')
        else:
            data = request.get_json()
            file = None

        required_fields = ['full_name', 'email', 'password', 'phone']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400

        photo_url = None
        if file:
            filename = secure_filename(file.filename)
            timestamp = datetime.now().timestamp()
            file_path = f"profile_photos/{timestamp}_{filename}"
            from utils.db import db
            file_content = file.read()
            db.client.storage.from_('profiles').upload(file_path, file_content)
            photo_url = db.client.storage.from_('profiles').get_public_url(file_path)

        user_data = {
            'full_name': data.get('full_name'),
            'phone': data.get('phone'),
            'date_of_birth': data.get('date_of_birth'),
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
            return jsonify({'success': True, 'message': message, 'user_id': user.id,
                            'email': user.email, 'referral_code': referral_code}), 201
        return jsonify({'success': False, 'message': message}), 400

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    User login
    ---
    tags:
      - Auth
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email, password]
          properties:
            email: {type: string, example: user@example.com}
            password: {type: string, example: secret123}
    responses:
      200:
        description: Login successful
        schema:
          properties:
            success: {type: boolean}
            message: {type: string}
            user:
              type: object
              properties:
                id: {type: string}
                email: {type: string}
                profile: {type: object}
            access_token: {type: string}
            refresh_token: {type: string}
            expires_at: {type: integer}
      401:
        description: Invalid credentials
      500:
        description: Server error
    """
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'}), 400

        user, session, error = AuthService.login_user(email, password)

        if user:
            profile, _ = AuthService.get_user_profile(user.id)
            return jsonify({
                'success': True, 'message': 'Login successful',
                'user': {'id': user.id, 'email': user.email, 'profile': profile},
                'access_token': session.access_token,
                'refresh_token': session.refresh_token,
                'expires_at': session.expires_at
            }), 200

        return jsonify({'success': False, 'message': error or 'Invalid credentials'}), 401

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """
    Logout current user
    ---
    tags:
      - Auth
    security:
      - BearerAuth: []
    responses:
      200:
        description: Logged out successfully
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if auth_header:
            from utils.db import db
            db.client.auth.sign_out()
        return jsonify({'success': True, 'message': 'Logged out successfully'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/refresh-token', methods=['POST'])
def refresh_token():
    """
    Refresh access token
    ---
    tags:
      - Auth
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [refresh_token]
          properties:
            refresh_token: {type: string}
    responses:
      200:
        description: Token refreshed
        schema:
          properties:
            success: {type: boolean}
            access_token: {type: string}
            refresh_token: {type: string}
            expires_at: {type: integer}
      400:
        description: Refresh token missing
      401:
        description: Invalid or expired token
    """
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
    """
    Send email verification link
    ---
    tags:
      - Auth
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email]
          properties:
            email: {type: string, example: user@example.com}
    responses:
      200:
        description: Verification email sent
      400:
        description: Email missing
      500:
        description: Server error
    """
    try:
        data = request.get_json()
        email = data.get('email')
        if not email:
            return jsonify({'success': False, 'message': 'Email required'}), 400
        from utils.db import db
        db.client.auth.reset_password_for_email(email)
        return jsonify({'success': True, 'message': 'Verification email sent'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """
    Send password reset email
    ---
    tags:
      - Auth
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [email]
          properties:
            email: {type: string, example: user@example.com}
    responses:
      200:
        description: Password reset email sent
      400:
        description: Email missing
      500:
        description: Server error
    """
    try:
        data = request.get_json()
        email = data.get('email')
        if not email:
            return jsonify({'success': False, 'message': 'Email required'}), 400
        from utils.db import db
        db.client.auth.reset_password_for_email(email)
        return jsonify({'success': True, 'message': 'Password reset email sent'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500