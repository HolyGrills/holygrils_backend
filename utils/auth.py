from utils.db import db
from datetime import datetime
import uuid

class AuthService:
    @staticmethod
    def signup_user(email, password, user_data):
        """Sign up a new user"""
        try:
            # Generate referral code
            referral_code = f"BACKEN{str(uuid.uuid4())[:6].upper()}"
            
            # Sign up with Supabase Auth
            auth_response = db.client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "full_name": user_data.get('full_name'),
                        "phone": user_data.get('phone')
                    }
                }
            })
            
            if not auth_response.user:
                return None, "Failed to create user"
            
            user_id = auth_response.user.id
            
            # Create profile in public.profiles table with your schema
            profile_data = {
                "id": user_id,
                "email": email,
                "full_name": user_data.get('full_name'),
                "phone": user_data.get('phone'),
                "date_of_birth": user_data.get('date_of_birth'),
                "faculty": user_data.get('faculty'),
                "department": user_data.get('department'),
                "photo_url": user_data.get('photo_url'),
                "role": "user",  # Default role
                "preferences": "{}",  # Empty JSON object
                "hp_balance": 0,  # Starting HP balance
                "wallet_balance": "0.00",  # Starting wallet balance
                "referral_code": referral_code,
                "is_active": True,
                "push_enabled": False,
                "email_notifications": True,
                "has_scheduled_order": False,
                "onboarding_completed_at": datetime.now().isoformat() if user_data.get('onboarding_completed') else None,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            # Remove None values
            profile_data = {k: v for k, v in profile_data.items() if v is not None}
            
            profile_response = db.client.table('profiles').insert(profile_data).execute()
            
            return auth_response.user, "User created successfully", referral_code
        
        except Exception as e:
            return None, str(e), None
    
    @staticmethod
    def login_user(email, password):
        """Login user"""
        try:
            response = db.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            # Update last_seen_at
            if response.user:
                db.client.table('profiles').update({
                    "last_seen_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }).eq('id', response.user.id).execute()
            
            return response.user, response.session, None
        except Exception as e:
            return None, None, str(e)
    
    @staticmethod
    def get_current_user(session_token):
        """Get current user from session token"""
        try:
            db.client.auth.set_session(session_token)
            user = db.client.auth.get_user()
            return user, None
        except Exception as e:
            return None, str(e)
    
    @staticmethod
    def get_user_profile(user_id):
        """Get user profile by ID"""
        try:
            response = db.client.table('profiles').select('*').eq('id', user_id).execute()
            if response.data:
                return response.data[0], None
            return None, "Profile not found"
        except Exception as e:
            return None, str(e)
    
    @staticmethod
    def update_hp_balance(user_id, amount, operation='add'):
        """Update user's HP balance"""
        try:
            # Get current balance
            profile = db.client.table('profiles').select('hp_balance').eq('id', user_id).execute()
            if not profile.data:
                return False, "User not found"
            
            current_balance = profile.data[0]['hp_balance']
            
            if operation == 'add':
                new_balance = current_balance + amount
            elif operation == 'subtract':
                if current_balance < amount:
                    return False, "Insufficient HP balance"
                new_balance = current_balance - amount
            else:
                return False, "Invalid operation"
            
            # Update balance
            response = db.client.table('profiles').update({
                "hp_balance": new_balance,
                "updated_at": datetime.now().isoformat(),
                "last_hp_activity_at": datetime.now().isoformat()
            }).eq('id', user_id).execute()
            
            return True, new_balance
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def update_wallet_balance(user_id, amount, operation='add'):
        """Update user's wallet balance"""
        try:
            # Get current balance
            profile = db.client.table('profiles').select('wallet_balance').eq('id', user_id).execute()
            if not profile.data:
                return False, "User not found"
            
            current_balance = float(profile.data[0]['wallet_balance'])
            
            if operation == 'add':
                new_balance = current_balance + amount
            elif operation == 'subtract':
                if current_balance < amount:
                    return False, "Insufficient wallet balance"
                new_balance = current_balance - amount
            else:
                return False, "Invalid operation"
            
            # Update balance
            response = db.client.table('profiles').update({
                "wallet_balance": f"{new_balance:.2f}",
                "updated_at": datetime.now().isoformat()
            }).eq('id', user_id).execute()
            
            return True, new_balance
        except Exception as e:
            return False, str(e)