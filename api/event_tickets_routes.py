from flask import Blueprint, request, jsonify, send_file
from utils.db import db
from utils.auth import AuthService
from datetime import datetime, timedelta
import uuid
import json
import qrcode
from io import BytesIO
import base64

ticket_bp = Blueprint('event_tickets', __name__)

def verify_token(token):
    """Verify JWT token and get user"""
    try:
        from utils.db import db
        user = db.client.auth.get_user(token)
        return user
    except:
        return None

def check_admin_or_organizer(user_id, event_id=None):
    """Check if user is admin or event organizer"""
    try:
        # Get user role
        profile = db.client.table('profiles').select('role').eq('id', user_id).execute()
        if profile.data and profile.data[0].get('role') in ['admin', 'super_admin']:
            return True
        
        # If event_id provided, check if user is the organizer
        if event_id:
            event = db.client.table('events').select('organizer_id').eq('id', event_id).execute()
            if event.data and event.data[0].get('organizer_id') == user_id:
                return True
        
        return False
    except:
        return False

def generate_qr_code(ticket_id, qr_code_data):
    """Generate QR code image and return as base64"""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_code_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return img_str
    except Exception as e:
        print(f"QR generation error: {e}")
        return None

@ticket_bp.route('/purchase', methods=['POST'])
def purchase_ticket():
    """Purchase tickets for an event"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        data = request.get_json()
        
        # Validate required fields
        if not data.get('event_id'):
            return jsonify({'success': False, 'message': 'Event ID is required'}), 400
        
        quantity = int(data.get('quantity', 1))
        if quantity < 1:
            return jsonify({'success': False, 'message': 'Quantity must be at least 1'}), 400
        
        # Get event details
        event_response = db.client.table('events').select('*').eq('id', data['event_id']).execute()
        if not event_response.data:
            return jsonify({'success': False, 'message': 'Event not found'}), 404
        
        event = event_response.data[0]
        
        # Check if event is published
        if not event.get('is_published'):
            return jsonify({'success': False, 'message': 'Event is not available for booking'}), 400
        
        # Check if event has passed
        now = datetime.now().isoformat()
        if event['ends_at'] < now:
            return jsonify({'success': False, 'message': 'Event has already ended'}), 400
        
        # Check capacity
        if event.get('capacity'):
            # Get current ticket count for this event
            ticket_count = db.client.table('event_tickets')\
                .select('*', count='exact')\
                .eq('event_id', data['event_id'])\
                .neq('status', 'cancelled')\
                .execute()
            
            available_capacity = event['capacity'] - ticket_count.count
            if quantity > available_capacity:
                return jsonify({
                    'success': False, 
                    'message': f'Only {available_capacity} tickets available'
                }), 400
        
        # Check if user already has active tickets for this event
        existing_tickets = db.client.table('event_tickets')\
            .select('*', count='exact')\
            .eq('event_id', data['event_id'])\
            .eq('user_id', user.id)\
            .neq('status', 'cancelled')\
            .execute()
        
        # Create ticket
        qr_code_data = f"{user.id}:{data['event_id']}:{uuid.uuid4().hex}"
        qr_expires_at = datetime.now() + timedelta(days=30)  # QR valid for 30 days
        
        ticket_data = {
            'event_id': data['event_id'],
            'user_id': user.id,
            'quantity': quantity,
            'status': 'confirmed',
            'qr_code': qr_code_data,
            'qr_expires_at': qr_expires_at.isoformat(),
            'created_at': datetime.now().isoformat()
        }
        
        # Calculate total cost
        ticket_price = float(event.get('ticket_price', 0))
        total_cost = ticket_price * quantity
        hp_reward = event.get('hp_reward', 0) * quantity
        
        response = db.client.table('event_tickets').insert(ticket_data).execute()
        ticket = response.data[0]
        
        # Deduct from user's wallet balance if payment is required
        if total_cost > 0:
            profile_response = db.client.table('profiles').select('wallet_balance').eq('id', user.id).execute()
            if profile_response.data:
                current_balance = float(profile_response.data[0]['wallet_balance'])
                if current_balance >= total_cost:
                    new_balance = current_balance - total_cost
                    db.client.table('profiles').update({
                        'wallet_balance': str(new_balance),
                        'updated_at': datetime.now().isoformat()
                    }).eq('id', user.id).execute()
                else:
                    # Cancel ticket if insufficient funds
                    db.client.table('event_tickets').update({
                        'status': 'cancelled',
                        'updated_at': datetime.now().isoformat()
                    }).eq('id', ticket['id']).execute()
                    return jsonify({
                        'success': False,
                        'message': 'Insufficient wallet balance'
                    }), 400
        
        # Add HP reward to user
        if hp_reward > 0:
            profile_response = db.client.table('profiles').select('hp_balance').eq('id', user.id).execute()
            if profile_response.data:
                current_hp = profile_response.data[0]['hp_balance']
                new_hp = current_hp + hp_reward
                db.client.table('profiles').update({
                    'hp_balance': new_hp,
                    'updated_at': datetime.now().isoformat()
                }).eq('id', user.id).execute()
        
        # Generate QR code image
        qr_image = generate_qr_code(ticket['id'], qr_code_data)
        
        return jsonify({
            'success': True,
            'message': 'Ticket purchased successfully',
            'ticket': {
                'id': ticket['id'],
                'event_id': ticket['event_id'],
                'event_title': event['title'],
                'quantity': quantity,
                'total_cost': total_cost,
                'hp_reward': hp_reward,
                'qr_code': qr_code_data,
                'qr_code_image': qr_image,
                'qr_expires_at': ticket['qr_expires_at'],
                'status': ticket['status'],
                'created_at': ticket['created_at']
            }
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@ticket_bp.route('/my-tickets', methods=['GET'])
def get_my_tickets():
    """Get current user's tickets"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Query parameters
        status = request.args.get('status')
        upcoming = request.args.get('upcoming', 'false').lower() == 'true'
        past = request.args.get('past', 'false').lower() == 'true'
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Build query
        query = db.client.table('event_tickets')\
            .select('*, events(*)')
        
        if status:
            query = query.eq('status', status)
        else:
            query = query.neq('status', 'cancelled')
        
        query = query.eq('user_id', user.id)
        
        # Date filtering
        now = datetime.now().isoformat()
        if upcoming:
            # Join with events to check start date
            tickets = query.execute()
            filtered_tickets = [t for t in tickets.data if t['events']['starts_at'] > now]
            tickets.data = filtered_tickets
        elif past:
            tickets = query.execute()
            filtered_tickets = [t for t in tickets.data if t['events']['ends_at'] < now]
            tickets.data = filtered_tickets
        else:
            tickets = query.execute()
        
        # Apply pagination
        total = len(tickets.data)
        paginated_tickets = tickets.data[offset:offset + limit]
        
        return jsonify({
            'success': True,
            'tickets': paginated_tickets,
            'pagination': {
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < total
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@ticket_bp.route('/<ticket_id>', methods=['GET'])
def get_ticket(ticket_id):
    """Get a single ticket by ID"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get ticket
        response = db.client.table('event_tickets')\
            .select('*, events(*)')\
            .eq('id', ticket_id)\
            .execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        ticket = response.data[0]
        
        # Check authorization (ticket owner or admin/organizer)
        profile = db.client.table('profiles').select('role').eq('id', user.id).execute()
        is_admin = profile.data and profile.data[0].get('role') in ['admin', 'super_admin']
        
        if ticket['user_id'] != user.id and not is_admin:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Generate fresh QR code image if needed
        qr_image = None
        if ticket.get('qr_code') and ticket['status'] != 'cancelled':
            qr_image = generate_qr_code(ticket['id'], ticket['qr_code'])
        
        return jsonify({
            'success': True,
            'ticket': {
                **ticket,
                'qr_code_image': qr_image
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@ticket_bp.route('/<ticket_id>/validate', methods=['POST'])
def validate_ticket(ticket_id):
    """Validate a ticket (for event organizers/admin)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get ticket with event details
        response = db.client.table('event_tickets')\
            .select('*, events(*)')\
            .eq('id', ticket_id)\
            .execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        ticket = response.data[0]
        
        # Check if user is authorized to validate (admin or event organizer)
        if not check_admin_or_organizer(user.id, ticket['event_id']):
            return jsonify({'success': False, 'message': 'Unauthorized to validate tickets for this event'}), 403
        
        # Check ticket status
        if ticket['status'] == 'cancelled':
            return jsonify({'success': False, 'message': 'Ticket has been cancelled'}), 400
        
        if ticket['status'] == 'used':
            return jsonify({'success': False, 'message': 'Ticket has already been used'}), 400
        
        # Check if event is ongoing
        now = datetime.now().isoformat()
        event = ticket['events']
        
        if now < event['starts_at']:
            return jsonify({
                'success': False,
                'message': 'Event has not started yet',
                'event_starts_at': event['starts_at']
            }), 400
        
        if now > event['ends_at']:
            return jsonify({
                'success': False,
                'message': 'Event has already ended',
                'event_ends_at': event['ends_at']
            }), 400
        
        # Check QR code expiry
        if ticket.get('qr_expires_at') and ticket['qr_expires_at'] < now:
            return jsonify({'success': False, 'message': 'QR code has expired'}), 400
        
        # Validate ticket
        data = request.get_json()
        update_data = {
            'status': 'used',
            'updated_at': datetime.now().isoformat()
        }
        
        if data and data.get('notes'):
            update_data['validation_notes'] = data['notes']
        
        db.client.table('event_tickets').update(update_data).eq('id', ticket_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Ticket validated successfully',
            'ticket': {
                'id': ticket['id'],
                'event_title': event['title'],
                'user_id': ticket['user_id'],
                'quantity': ticket['quantity'],
                'validated_at': datetime.now().isoformat()
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@ticket_bp.route('/<ticket_id>/cancel', methods=['POST'])
def cancel_ticket(ticket_id):
    """Cancel a ticket (user or admin)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get ticket
        response = db.client.table('event_tickets')\
            .select('*, events(*)')\
            .eq('id', ticket_id)\
            .execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        ticket = response.data[0]
        
        # Check authorization
        profile = db.client.table('profiles').select('role').eq('id', user.id).execute()
        is_admin = profile.data and profile.data[0].get('role') in ['admin', 'super_admin']
        
        if ticket['user_id'] != user.id and not is_admin:
            return jsonify({'success': False, 'message': 'Unauthorized to cancel this ticket'}), 403
        
        # Check if event has already passed
        now = datetime.now().isoformat()
        if ticket['events']['starts_at'] < now:
            return jsonify({'success': False, 'message': 'Cannot cancel ticket for past event'}), 400
        
        # Check if ticket is already used
        if ticket['status'] == 'used':
            return jsonify({'success': False, 'message': 'Cannot cancel a used ticket'}), 400
        
        if ticket['status'] == 'cancelled':
            return jsonify({'success': False, 'message': 'Ticket already cancelled'}), 400
        
        # Cancel ticket
        update_data = {
            'status': 'cancelled',
            'updated_at': datetime.now().isoformat()
        }
        
        data = request.get_json()
        if data and data.get('reason'):
            update_data['cancellation_reason'] = data['reason']
        
        db.client.table('event_tickets').update(update_data).eq('id', ticket_id).execute()
        
        # Refund wallet if applicable (optional - implement based on your policy)
        # This would depend on your refund policy
        
        return jsonify({
            'success': True,
            'message': 'Ticket cancelled successfully'
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@ticket_bp.route('/event/<event_id>/tickets', methods=['GET'])
def get_event_tickets(event_id):
    """Get all tickets for an event (admin/organizer only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Check authorization
        if not check_admin_or_organizer(user.id, event_id):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Query parameters
        status = request.args.get('status')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Build query
        query = db.client.table('event_tickets')\
            .select('*, profiles(full_name, email, phone)')\
            .eq('event_id', event_id)
        
        if status:
            query = query.eq('status', status)
        
        # Apply pagination
        query = query.range(offset, offset + limit - 1)
        
        response = query.execute()
        
        # Get total count
        count_query = db.client.table('event_tickets').select('*', count='exact').eq('event_id', event_id)
        if status:
            count_query = count_query.eq('status', status)
        count_response = count_query.execute()
        
        # Calculate stats
        stats_query = db.client.table('event_tickets')\
            .select('status', count='exact')\
            .eq('event_id', event_id)\
            .execute()
        
        status_counts = {}
        for ticket in stats_query.data:
            status_counts[ticket['status']] = status_counts.get(ticket['status'], 0) + 1
        
        return jsonify({
            'success': True,
            'tickets': response.data,
            'stats': {
                'total': count_response.count,
                'by_status': status_counts
            },
            'pagination': {
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < count_response.count
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@ticket_bp.route('/event/<event_id>/checkin', methods=['POST'])
def checkin_attendee(event_id):
    """Check in an attendee using QR code (admin/organizer only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Check authorization
        if not check_admin_or_organizer(user.id, event_id):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        data = request.get_json()
        qr_code = data.get('qr_code')
        
        if not qr_code:
            return jsonify({'success': False, 'message': 'QR code is required'}), 400
        
        # Find ticket by QR code
        ticket_response = db.client.table('event_tickets')\
            .select('*, events(*)')\
            .eq('qr_code', qr_code)\
            .eq('event_id', event_id)\
            .execute()
        
        if not ticket_response.data:
            return jsonify({'success': False, 'message': 'Invalid QR code'}), 404
        
        ticket = ticket_response.data[0]
        
        # Check ticket status
        if ticket['status'] == 'cancelled':
            return jsonify({'success': False, 'message': 'Ticket has been cancelled'}), 400
        
        if ticket['status'] == 'used':
            return jsonify({'success': False, 'message': 'Ticket has already been used'}), 400
        
        # Check if event is ongoing
        now = datetime.now().isoformat()
        event = ticket['events']
        
        if now < event['starts_at']:
            return jsonify({
                'success': False,
                'message': 'Event has not started yet',
                'event_starts_at': event['starts_at']
            }), 400
        
        if now > event['ends_at']:
            return jsonify({
                'success': False,
                'message': 'Event has already ended',
                'event_ends_at': event['ends_at']
            }), 400
        
        # Mark ticket as used
        db.client.table('event_tickets').update({
            'status': 'used',
            'updated_at': datetime.now().isoformat()
        }).eq('id', ticket['id']).execute()
        
        # Get attendee info
        attendee = db.client.table('profiles')\
            .select('full_name, email, phone')\
            .eq('id', ticket['user_id'])\
            .execute()
        
        return jsonify({
            'success': True,
            'message': 'Check-in successful',
            'attendee': attendee.data[0] if attendee.data else None,
            'ticket': {
                'id': ticket['id'],
                'quantity': ticket['quantity'],
                'checked_in_at': datetime.now().isoformat()
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@ticket_bp.route('/stats', methods=['GET'])
def get_ticket_stats():
    """Get ticket statistics for user"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        now = datetime.now().isoformat()
        
        # Get all user tickets
        tickets_response = db.client.table('event_tickets')\
            .select('*, events(starts_at, ends_at, title)')\
            .eq('user_id', user.id)\
            .execute()
        
        tickets = tickets_response.data
        
        stats = {
            'total_tickets': len(tickets),
            'active_tickets': len([t for t in tickets if t['status'] not in ['cancelled', 'used'] and t['events']['ends_at'] > now]),
            'used_tickets': len([t for t in tickets if t['status'] == 'used']),
            'cancelled_tickets': len([t for t in tickets if t['status'] == 'cancelled']),
            'upcoming_events': len([t for t in tickets if t['events']['starts_at'] > now and t['status'] not in ['cancelled', 'used']]),
            'past_events': len([t for t in tickets if t['events']['ends_at'] < now])
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@ticket_bp.route('/<ticket_id>/regenerate-qr', methods=['POST'])
def regenerate_qr_code(ticket_id):
    """Regenerate QR code for a ticket"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get ticket
        response = db.client.table('event_tickets').select('*').eq('id', ticket_id).execute()
        if not response.data:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        ticket = response.data[0]
        
        # Check authorization
        if ticket['user_id'] != user.id:
            profile = db.client.table('profiles').select('role').eq('id', user.id).execute()
            is_admin = profile.data and profile.data[0].get('role') in ['admin', 'super_admin']
            if not is_admin:
                return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Check if ticket is still valid
        if ticket['status'] == 'cancelled':
            return jsonify({'success': False, 'message': 'Cannot regenerate QR for cancelled ticket'}), 400
        
        if ticket['status'] == 'used':
            return jsonify({'success': False, 'message': 'Cannot regenerate QR for used ticket'}), 400
        
        # Generate new QR code
        new_qr_code = f"{ticket['user_id']}:{ticket['event_id']}:{uuid.uuid4().hex}"
        new_expiry = datetime.now() + timedelta(days=30)
        
        db.client.table('event_tickets').update({
            'qr_code': new_qr_code,
            'qr_expires_at': new_expiry.isoformat(),
            'updated_at': datetime.now().isoformat()
        }).eq('id', ticket_id).execute()
        
        # Generate new QR image
        qr_image = generate_qr_code(ticket_id, new_qr_code)
        
        return jsonify({
            'success': True,
            'message': 'QR code regenerated successfully',
            'qr_code': new_qr_code,
            'qr_code_image': qr_image,
            'qr_expires_at': new_expiry.isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500