from flask import Blueprint, request, jsonify
from utils.db import db

user_bp = Blueprint('user', __name__)

def verify_token(token):
    """Verify JWT token and get user"""
    try:
        from utils.db import db
        user = db.client.auth.get_user(token)
        return user
    except:
        return None

@user_bp.route('/profile', methods=['GET'])
def get_profile():
    """Get user profile"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        response = db.client.table('profiles').select('*').eq('id', user.id).execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'profile': response.data[0]
            }), 200
        else:
            return jsonify({'success': False, 'message': 'Profile not found'}), 404
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@user_bp.route('/profile', methods=['PUT'])
def update_profile():
    """Update user profile"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        data = request.get_json()
        update_data = {}
        
        allowed_fields = ['name', 'phone_number', 'department']
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        if update_data:
            response = db.client.table('profiles').update(update_data).eq('id', user.id).execute()
            
            return jsonify({
                'success': True,
                'message': 'Profile updated successfully',
                'profile': response.data[0] if response.data else None
            }), 200
        else:
            return jsonify({'success': False, 'message': 'No valid fields to update'}), 400
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500