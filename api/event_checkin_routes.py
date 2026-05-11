from flask import Blueprint, request, jsonify
from utils.db import db
from datetime import datetime
import uuid
import json

checkin_bp = Blueprint('event_checkins', __name__)

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

def create_hp_transaction(user_id, amount, transaction_type, reference_id, description):
    """Create an HP transaction record"""
    try:
        transaction_data = {
            'user_id': user_id,
            'amount': amount,
            'type': transaction_type,  # 'earn', 'redeem', 'bonus'
            'reference_id': reference_id,
            'description': description,
            'status': 'completed',
            'created_at': datetime.now().isoformat()
        }
        
        response = db.client.table('hp_transactions').insert(transaction_data).execute()
        return response.data[0]['id'] if response.data else None
    except Exception as e:
        print(f"Error creating HP transaction: {e}")
        return None

@checkin_bp.route('/checkin', methods=['POST'])
def checkin_attendee():
    """Check in an attendee using QR code"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        data = request.get_json()
        qr_code = data.get('qr_code')
        
        if not qr_code:
            return jsonify({'success': False, 'message': 'QR code is required'}), 400
        
        # Find ticket by QR code with event details
        ticket_response = db.client.table('event_tickets')\
            .select('*, events(*)')\
            .eq('qr_code', qr_code)\
            .execute()
        
        if not ticket_response.data:
            return jsonify({'success': False, 'message': 'Invalid QR code'}), 404
        
        ticket = ticket_response.data[0]
        event = ticket['events']
        
        # Check authorization (admin or event organizer)
        if not check_admin_or_organizer(user.id, event['id']):
            return jsonify({'success': False, 'message': 'Unauthorized to check in attendees for this event'}), 403
        
        # Check if ticket is already checked in
        existing_checkin = db.client.table('event_checkins')\
            .select('*')\
            .eq('ticket_id', ticket['id'])\
            .execute()
        
        if existing_checkin.data:
            return jsonify({
                'success': False, 
                'message': 'Ticket already checked in',
                'checkin_time': existing_checkin.data[0]['created_at']
            }), 400
        
        # Check ticket status
        if ticket['status'] == 'cancelled':
            return jsonify({'success': False, 'message': 'Ticket has been cancelled'}), 400
        
        if ticket['status'] == 'used':
            return jsonify({'success': False, 'message': 'Ticket has already been used'}), 400
        
        # Check if event is ongoing
        now = datetime.now().isoformat()
        
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
        
        # Create HP transaction if event gives HP reward
        hp_transaction_id = None
        hp_reward = event.get('hp_reward', 0) * ticket['quantity']
        
        if hp_reward > 0:
            hp_transaction_id = create_hp_transaction(
                user_id=ticket['user_id'],
                amount=hp_reward,
                transaction_type='earn',
                reference_id=ticket['id'],
                description=f'HP earned for attending {event["title"]}'
            )
            
            # Update user's HP balance
            if hp_transaction_id:
                profile_response = db.client.table('profiles').select('hp_balance').eq('id', ticket['user_id']).execute()
                if profile_response.data:
                    current_hp = profile_response.data[0]['hp_balance']
                    new_hp = current_hp + hp_reward
                    db.client.table('profiles').update({
                        'hp_balance': new_hp,
                        'updated_at': datetime.now().isoformat(),
                        'last_hp_activity_at': datetime.now().isoformat()
                    }).eq('id', ticket['user_id']).execute()
        
        # Create check-in record
        checkin_data = {
            'ticket_id': ticket['id'],
            'qr_code': qr_code,
            'checked_in_by': user.id,
            'hp_transaction_id': hp_transaction_id,
            'created_at': datetime.now().isoformat()
        }
        
        checkin_response = db.client.table('event_checkins').insert(checkin_data).execute()
        checkin = checkin_response.data[0]
        
        # Update ticket status to used
        db.client.table('event_tickets').update({
            'status': 'used',
            'updated_at': datetime.now().isoformat()
        }).eq('id', ticket['id']).execute()
        
        # Get attendee info
        attendee = db.client.table('profiles')\
            .select('full_name, email, phone')\
            .eq('id', ticket['user_id'])\
            .execute()
        
        # Get checker info
        checker = db.client.table('profiles')\
            .select('full_name')\
            .eq('id', user.id)\
            .execute()
        
        return jsonify({
            'success': True,
            'message': 'Check-in successful',
            'checkin': {
                'id': checkin['id'],
                'ticket_id': ticket['id'],
                'checked_in_at': checkin['created_at'],
                'checked_in_by': checker.data[0]['full_name'] if checker.data else None,
                'hp_reward_earned': hp_reward,
                'hp_transaction_id': hp_transaction_id
            },
            'attendee': attendee.data[0] if attendee.data else None,
            'event': {
                'id': event['id'],
                'title': event['title'],
                'location': event['location']
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@checkin_bp.route('/ticket/<ticket_id>/checkin-status', methods=['GET'])
def get_ticket_checkin_status(ticket_id):
    """Get check-in status for a specific ticket"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get ticket details
        ticket_response = db.client.table('event_tickets')\
            .select('*, events(*)')\
            .eq('id', ticket_id)\
            .execute()
        
        if not ticket_response.data:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        ticket = ticket_response.data[0]
        
        # Check authorization
        profile = db.client.table('profiles').select('role').eq('id', user.id).execute()
        is_admin = profile.data and profile.data[0].get('role') in ['admin', 'super_admin']
        
        if ticket['user_id'] != user.id and not is_admin and not check_admin_or_organizer(user.id, ticket['event_id']):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Get check-in record
        checkin_response = db.client.table('event_checkins')\
            .select('*, checked_in_by_profile:profiles!checked_in_by(full_name)')\
            .eq('ticket_id', ticket_id)\
            .execute()
        
        checkin = checkin_response.data[0] if checkin_response.data else None
        
        return jsonify({
            'success': True,
            'is_checked_in': checkin is not None,
            'checkin_details': checkin,
            'ticket': {
                'id': ticket['id'],
                'status': ticket['status'],
                'quantity': ticket['quantity'],
                'event_title': ticket['events']['title']
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@checkin_bp.route('/event/<event_id>/checkins', methods=['GET'])
def get_event_checkins(event_id):
    """Get all check-ins for an event (admin/organizer only)"""
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
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        # Build query to get check-ins for event tickets
        query = db.client.table('event_checkins')\
            .select('*, ticket:event_tickets!ticket_id(*, profiles(full_name, email, phone)), checked_in_by_profile:profiles!checked_in_by(full_name)')\
            .in_('ticket_id', 
                 db.client.table('event_tickets').select('id').eq('event_id', event_id).execute().data
            )
        
        # Apply date filters
        if date_from:
            query = query.gte('created_at', date_from)
        if date_to:
            query = query.lte('created_at', date_to)
        
        # Order by check-in time
        query = query.order('created_at', desc=True)
        
        # Apply pagination
        query = query.range(offset, offset + limit - 1)
        
        response = query.execute()
        
        # Get total count
        count_response = db.client.table('event_checkins')\
            .select('*', count='exact')\
            .in_('ticket_id', 
                 db.client.table('event_tickets').select('id').eq('event_id', event_id).execute().data
            )\
            .execute()
        
        # Get event details
        event_response = db.client.table('events').select('title, capacity').eq('id', event_id).execute()
        event = event_response.data[0] if event_response.data else None
        
        # Get total tickets sold
        tickets_sold = db.client.table('event_tickets')\
            .select('*', count='exact')\
            .eq('event_id', event_id)\
            .neq('status', 'cancelled')\
            .execute()
        
        return jsonify({
            'success': True,
            'event': event,
            'checkins': response.data,
            'stats': {
                'total_checkins': count_response.count,
                'total_tickets_sold': tickets_sold.count,
                'checkin_rate': round((count_response.count / tickets_sold.count * 100), 2) if tickets_sold.count > 0 else 0
            },
            'pagination': {
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < count_response.count
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@checkin_bp.route('/event/<event_id>/checkins/stats', methods=['GET'])
def get_event_checkin_stats(event_id):
    """Get detailed check-in statistics for an event"""
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
        
        # Get event details
        event_response = db.client.table('events').select('*, organizer:profiles!organizer_id(full_name)').eq('id', event_id).execute()
        if not event_response.data:
            return jsonify({'success': False, 'message': 'Event not found'}), 404
        
        event = event_response.data[0]
        
        # Get all tickets for event
        tickets_response = db.client.table('event_tickets')\
            .select('*, profiles(full_name, email, phone)')\
            .eq('event_id', event_id)\
            .execute()
        
        tickets = tickets_response.data
        
        # Get all check-ins for event
        checkins_response = db.client.table('event_checkins')\
            .select('*, checked_in_by_profile:profiles!checked_in_by(full_name)')\
            .in_('ticket_id', [t['id'] for t in tickets])\
            .execute()
        
        checkins = checkins_response.data
        
        # Calculate statistics
        total_tickets = len(tickets)
        checked_in = len(checkins)
        cancelled_tickets = len([t for t in tickets if t['status'] == 'cancelled'])
        unused_tickets = len([t for t in tickets if t['status'] != 'cancelled' and t['status'] != 'used' and not any(c['ticket_id'] == t['id'] for c in checkins)])
        
        # Check-in timeline (group by hour)
        timeline = {}
        for checkin in checkins:
            hour = checkin['created_at'][:13]  # Group by hour
            if hour not in timeline:
                timeline[hour] = 0
            timeline[hour] += 1
        
        # Check-ins by checker
        by_checker = {}
        for checkin in checkins:
            checker_name = checkin.get('checked_in_by_profile', {}).get('full_name', 'Unknown')
            if checker_name not in by_checker:
                by_checker[checker_name] = 0
            by_checker[checker_name] += 1
        
        # HP stats
        total_hp_awarded = sum([c.get('hp_reward', 0) for c in checkins if c.get('hp_reward')])
        
        return jsonify({
            'success': True,
            'event': {
                'id': event['id'],
                'title': event['title'],
                'starts_at': event['starts_at'],
                'ends_at': event['ends_at'],
                'location': event['location'],
                'capacity': event['capacity'],
                'organizer': event.get('organizer')
            },
            'statistics': {
                'total_tickets_sold': total_tickets,
                'checked_in': checked_in,
                'cancelled': cancelled_tickets,
                'unused': unused_tickets,
                'checkin_rate': round((checked_in / total_tickets * 100), 2) if total_tickets > 0 else 0,
                'total_hp_awarded': total_hp_awarded
            },
            'timeline': timeline,
            'by_checker': by_checker,
            'recent_checkins': checkins[:10]  # Last 10 check-ins
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@checkin_bp.route('/my-checkins', methods=['GET'])
def get_my_checkins():
    """Get user's own check-in history"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Query parameters
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Get user's tickets that have been checked in
        tickets_response = db.client.table('event_tickets')\
            .select('id')\
            .eq('user_id', user.id)\
            .execute()
        
        ticket_ids = [t['id'] for t in tickets_response.data]
        
        if not ticket_ids:
            return jsonify({
                'success': True,
                'checkins': [],
                'pagination': {'total': 0, 'limit': limit, 'offset': offset, 'has_more': False}
            }), 200
        
        # Get check-ins for these tickets
        query = db.client.table('event_checkins')\
            .select('*, ticket:event_tickets!ticket_id(*, events(*))')\
            .in_('ticket_id', ticket_ids)\
            .order('created_at', desc=True)\
            .range(offset, offset + limit - 1)
        
        response = query.execute()
        
        # Get total count
        count_response = db.client.table('event_checkins')\
            .select('*', count='exact')\
            .in_('ticket_id', ticket_ids)\
            .execute()
        
        return jsonify({
            'success': True,
            'checkins': response.data,
            'pagination': {
                'total': count_response.count,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < count_response.count
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@checkin_bp.route('/recent', methods=['GET'])
def get_recent_checkins():
    """Get recent check-ins across all events (admin only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Check if admin
        profile = db.client.table('profiles').select('role').eq('id', user.id).execute()
        if not profile.data or profile.data[0].get('role') not in ['admin', 'super_admin']:
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        limit = request.args.get('limit', 20, type=int)
        
        response = db.client.table('event_checkins')\
            .select('*, ticket:event_tickets!ticket_id(*, events(*), profiles(full_name, email)), checked_in_by_profile:profiles!checked_in_by(full_name)')\
            .order('created_at', desc=True)\
            .limit(limit)\
            .execute()
        
        return jsonify({
            'success': True,
            'recent_checkins': response.data
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@checkin_bp.route('/verify-qr', methods=['POST'])
def verify_qr_code():
    """Verify QR code without checking in (for validation)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        data = request.get_json()
        qr_code = data.get('qr_code')
        
        if not qr_code:
            return jsonify({'success': False, 'message': 'QR code is required'}), 400
        
        # Find ticket by QR code
        ticket_response = db.client.table('event_tickets')\
            .select('*, events(*), profiles(full_name, email, phone)')\
            .eq('qr_code', qr_code)\
            .execute()
        
        if not ticket_response.data:
            return jsonify({'success': False, 'message': 'Invalid QR code'}), 404
        
        ticket = ticket_response.data[0]
        event = ticket['events']
        
        # Check if already checked in
        is_checked_in = False
        checkin_time = None
        
        checkin_response = db.client.table('event_checkins')\
            .select('*')\
            .eq('ticket_id', ticket['id'])\
            .execute()
        
        if checkin_response.data:
            is_checked_in = True
            checkin_time = checkin_response.data[0]['created_at']
        
        # Check ticket validity
        now = datetime.now().isoformat()
        is_valid = True
        validation_issues = []
        
        if ticket['status'] == 'cancelled':
            is_valid = False
            validation_issues.append('Ticket has been cancelled')
        
        if ticket['status'] == 'used':
            is_valid = False
            validation_issues.append('Ticket has already been used')
        
        if is_checked_in:
            is_valid = False
            validation_issues.append('Ticket has already been checked in')
        
        if now < event['starts_at']:
            is_valid = False
            validation_issues.append(f'Event has not started yet. Starts at: {event["starts_at"]}')
        
        if now > event['ends_at']:
            is_valid = False
            validation_issues.append(f'Event has already ended. Ended at: {event["ends_at"]}')
        
        if ticket.get('qr_expires_at') and ticket['qr_expires_at'] < now:
            is_valid = False
            validation_issues.append('QR code has expired')
        
        return jsonify({
            'success': True,
            'is_valid': is_valid,
            'validation_issues': validation_issues,
            'ticket': {
                'id': ticket['id'],
                'quantity': ticket['quantity'],
                'status': ticket['status'],
                'is_checked_in': is_checked_in,
                'checked_in_at': checkin_time
            },
            'event': {
                'id': event['id'],
                'title': event['title'],
                'starts_at': event['starts_at'],
                'ends_at': event['ends_at'],
                'location': event['location']
            },
            'attendee': {
                'full_name': ticket['profiles']['full_name'],
                'email': ticket['profiles']['email'],
                'phone': ticket['profiles']['phone']
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@checkin_bp.route('/bulk-checkin', methods=['POST'])
def bulk_checkin():
    """Bulk check-in multiple attendees (admin/organizer only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        data = request.get_json()
        event_id = data.get('event_id')
        qr_codes = data.get('qr_codes', [])
        
        if not event_id:
            return jsonify({'success': False, 'message': 'Event ID is required'}), 400
        
        if not qr_codes:
            return jsonify({'success': False, 'message': 'At least one QR code is required'}), 400
        
        # Check authorization
        if not check_admin_or_organizer(user.id, event_id):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        results = []
        successful = 0
        failed = 0
        
        for qr_code in qr_codes:
            try:
                # Find ticket by QR code
                ticket_response = db.client.table('event_tickets')\
                    .select('*, events(*)')\
                    .eq('qr_code', qr_code)\
                    .eq('event_id', event_id)\
                    .execute()
                
                if not ticket_response.data:
                    results.append({'qr_code': qr_code, 'success': False, 'message': 'Invalid QR code'})
                    failed += 1
                    continue
                
                ticket = ticket_response.data[0]
                event = ticket['events']
                
                # Check if already checked in
                existing_checkin = db.client.table('event_checkins')\
                    .select('*')\
                    .eq('ticket_id', ticket['id'])\
                    .execute()
                
                if existing_checkin.data:
                    results.append({'qr_code': qr_code, 'success': False, 'message': 'Already checked in'})
                    failed += 1
                    continue
                
                # Check ticket status
                if ticket['status'] == 'cancelled':
                    results.append({'qr_code': qr_code, 'success': False, 'message': 'Ticket cancelled'})
                    failed += 1
                    continue
                
                # Create check-in
                checkin_data = {
                    'ticket_id': ticket['id'],
                    'qr_code': qr_code,
                    'checked_in_by': user.id,
                    'created_at': datetime.now().isoformat()
                }
                
                db.client.table('event_checkins').insert(checkin_data).execute()
                
                # Update ticket status
                db.client.table('event_tickets').update({
                    'status': 'used',
                    'updated_at': datetime.now().isoformat()
                }).eq('id', ticket['id']).execute()
                
                results.append({'qr_code': qr_code, 'success': True, 'message': 'Checked in successfully'})
                successful += 1
                
            except Exception as e:
                results.append({'qr_code': qr_code, 'success': False, 'message': str(e)})
                failed += 1
        
        return jsonify({
            'success': True,
            'summary': {
                'total': len(qr_codes),
                'successful': successful,
                'failed': failed
            },
            'results': results
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500