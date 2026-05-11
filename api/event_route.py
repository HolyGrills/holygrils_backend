from flask import Blueprint, request, jsonify
from utils.db import db
from datetime import datetime
import uuid
import json

event_bp = Blueprint('events', __name__)

def verify_token(token):
    """Verify JWT token and get user"""
    try:
        from utils.db import db
        user = db.client.auth.get_user(token)
        return user
    except:
        return None

def check_admin_or_organizer(user_id, organizer_id=None):
    """Check if user is admin or the event organizer"""
    try:
        # Get user role
        profile = db.client.table('profiles').select('role').eq('id', user_id).execute()
        if profile.data and profile.data[0].get('role') in ['admin', 'super_admin']:
            return True
        
        # Check if user is the organizer
        if organizer_id and user_id == organizer_id:
            return True
        
        return False
    except:
        return False

def generate_event_slug(title):
    """Generate a unique slug from event title"""
    slug = title.lower().strip()
    # Replace spaces and special characters
    slug = ''.join(c if c.isalnum() else '-' for c in slug)
    # Remove multiple dashes
    slug = '-'.join(filter(None, slug.split('-')))
    # Add random suffix to ensure uniqueness
    return f"{slug}-{uuid.uuid4().hex[:6]}"

@event_bp.route('/', methods=['POST'])
def create_event():
    """Create a new event"""
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
        required_fields = ['title', 'starts_at', 'ends_at', 'location']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
        
        # Validate dates
        starts_at = datetime.fromisoformat(data['starts_at'].replace('Z', '+00:00'))
        ends_at = datetime.fromisoformat(data['ends_at'].replace('Z', '+00:00'))
        
        if ends_at <= starts_at:
            return jsonify({'success': False, 'message': 'End time must be after start time'}), 400
        
        # Generate unique slug
        slug = data.get('slug') or generate_event_slug(data['title'])
        
        # Check if slug already exists
        existing = db.client.table('events').select('id').eq('slug', slug).execute()
        if existing.data:
            # Add random suffix to make it unique
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"
        
        # Prepare event data
        event_data = {
            'title': data['title'],
            'slug': slug,
            'description': data.get('description'),
            'starts_at': data['starts_at'],
            'ends_at': data['ends_at'],
            'location': data['location'],
            'image_url': data.get('image_url'),
            'ticket_price': float(data.get('ticket_price', 0)),
            'hp_reward': int(data.get('hp_reward', 0)),
            'capacity': data.get('capacity'),
            'is_published': data.get('is_published', False),
            'metadata': json.dumps(data.get('metadata', {})),
            'hp_promo_enabled': data.get('hp_promo_enabled', False),
            'is_featured': data.get('is_featured', False),
            'organizer_id': data.get('organizer_id', user.id),
            'created_at': datetime.now().isoformat()
        }
        
        # Remove None values
        event_data = {k: v for k, v in event_data.items() if v is not None}
        
        response = db.client.table('events').insert(event_data).execute()
        
        return jsonify({
            'success': True,
            'message': 'Event created successfully',
            'event': response.data[0]
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/', methods=['GET'])
def get_events():
    """Get all events with filtering and pagination"""
    try:
        # Query parameters
        is_published = request.args.get('is_published')
        is_featured = request.args.get('is_featured')
        upcoming = request.args.get('upcoming', 'false').lower() == 'true'
        past = request.args.get('past', 'false').lower() == 'true'
        organizer_id = request.args.get('organizer_id')
        search = request.args.get('search')
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Start query
        query = db.client.table('events').select('*')
        
        # Apply filters
        if is_published is not None:
            query = query.eq('is_published', is_published.lower() == 'true')
        
        if is_featured is not None:
            query = query.eq('is_featured', is_featured.lower() == 'true')
        
        if organizer_id:
            query = query.eq('organizer_id', organizer_id)
        
        if search:
            query = query.or_(f"title.ilike.%{search}%,description.ilike.%{search}%")
        
        # Date filtering
        now = datetime.now().isoformat()
        if upcoming:
            query = query.gt('starts_at', now)
        elif past:
            query = query.lt('ends_at', now)
        
        # Order by start date
        query = query.order('starts_at', desc=False)
        
        # Apply pagination
        query = query.range(offset, offset + limit - 1)
        
        response = query.execute()
        
        # Get total count
        count_query = db.client.table('events').select('*', count='exact')
        if is_published is not None:
            count_query = count_query.eq('is_published', is_published.lower() == 'true')
        if organizer_id:
            count_query = count_query.eq('organizer_id', organizer_id)
        if upcoming:
            count_query = count_query.gt('starts_at', now)
        elif past:
            count_query = count_query.lt('ends_at', now)
        
        count_response = count_query.execute()
        
        return jsonify({
            'success': True,
            'events': response.data,
            'pagination': {
                'total': count_response.count,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < count_response.count
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/<event_id>', methods=['GET'])
def get_event(event_id):
    """Get a single event by ID"""
    try:
        response = db.client.table('events').select('*').eq('id', event_id).execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Event not found'}), 404
        
        event = response.data[0]
        
        # Get organizer details if exists
        if event.get('organizer_id'):
            organizer = db.client.table('profiles').select('full_name, email, phone').eq('id', event['organizer_id']).execute()
            if organizer.data:
                event['organizer'] = organizer.data[0]
        
        return jsonify({
            'success': True,
            'event': event
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/slug/<slug>', methods=['GET'])
def get_event_by_slug(slug):
    """Get a single event by slug"""
    try:
        response = db.client.table('events').select('*').eq('slug', slug).execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Event not found'}), 404
        
        event = response.data[0]
        
        # Get organizer details if exists
        if event.get('organizer_id'):
            organizer = db.client.table('profiles').select('full_name, email, phone').eq('id', event['organizer_id']).execute()
            if organizer.data:
                event['organizer'] = organizer.data[0]
        
        return jsonify({
            'success': True,
            'event': event
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/<event_id>', methods=['PUT'])
def update_event(event_id):
    """Update an event"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get existing event
        existing = db.client.table('events').select('*').eq('id', event_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'Event not found'}), 404
        
        event = existing.data[0]
        
        # Check authorization
        if not check_admin_or_organizer(user.id, event.get('organizer_id')):
            return jsonify({'success': False, 'message': 'Unauthorized to update this event'}), 403
        
        data = request.get_json()
        
        # Prepare update data
        update_data = {
            'updated_at': datetime.now().isoformat()
        }
        
        # Allowed fields for update
        allowed_fields = [
            'title', 'description', 'starts_at', 'ends_at', 'location',
            'image_url', 'ticket_price', 'hp_reward', 'capacity',
            'is_published', 'metadata', 'hp_promo_enabled', 'is_featured',
            'organizer_id'
        ]
        
        for field in allowed_fields:
            if field in data:
                # Handle special fields
                if field in ['ticket_price']:
                    update_data[field] = float(data[field])
                elif field in ['hp_reward', 'capacity']:
                    update_data[field] = int(data[field]) if data[field] else None
                elif field == 'metadata' and isinstance(data[field], dict):
                    update_data[field] = json.dumps(data[field])
                else:
                    update_data[field] = data[field]
        
        # If title is updated, update slug
        if 'title' in data and data['title'] != event['title']:
            new_slug = generate_event_slug(data['title'])
            # Check if new slug exists
            slug_exists = db.client.table('events').select('id').eq('slug', new_slug).neq('id', event_id).execute()
            if slug_exists.data:
                new_slug = f"{new_slug}-{uuid.uuid4().hex[:4]}"
            update_data['slug'] = new_slug
        
        # Validate dates if both are provided
        if 'starts_at' in update_data and 'ends_at' in update_data:
            starts_at = datetime.fromisoformat(update_data['starts_at'].replace('Z', '+00:00'))
            ends_at = datetime.fromisoformat(update_data['ends_at'].replace('Z', '+00:00'))
            if ends_at <= starts_at:
                return jsonify({'success': False, 'message': 'End time must be after start time'}), 400
        elif 'starts_at' in update_data:
            starts_at = datetime.fromisoformat(update_data['starts_at'].replace('Z', '+00:00'))
            ends_at = datetime.fromisoformat(event['ends_at'].replace('Z', '+00:00'))
            if ends_at <= starts_at:
                return jsonify({'success': False, 'message': 'End time must be after start time'}), 400
        elif 'ends_at' in update_data:
            ends_at = datetime.fromisoformat(update_data['ends_at'].replace('Z', '+00:00'))
            starts_at = datetime.fromisoformat(event['starts_at'].replace('Z', '+00:00'))
            if ends_at <= starts_at:
                return jsonify({'success': False, 'message': 'End time must be after start time'}), 400
        
        response = db.client.table('events').update(update_data).eq('id', event_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Event updated successfully',
            'event': response.data[0]
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    """Delete an event"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get existing event
        existing = db.client.table('events').select('*').eq('id', event_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'Event not found'}), 404
        
        event = existing.data[0]
        
        # Check authorization
        if not check_admin_or_organizer(user.id, event.get('organizer_id')):
            return jsonify({'success': False, 'message': 'Unauthorized to delete this event'}), 403
        
        # Delete event
        db.client.table('events').delete().eq('id', event_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Event deleted successfully'
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/<event_id>/publish', methods=['POST'])
def publish_event(event_id):
    """Publish or unpublish an event"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        data = request.get_json()
        is_published = data.get('is_published', True)
        
        # Get existing event
        existing = db.client.table('events').select('*').eq('id', event_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'Event not found'}), 404
        
        event = existing.data[0]
        
        # Check authorization
        if not check_admin_or_organizer(user.id, event.get('organizer_id')):
            return jsonify({'success': False, 'message': 'Unauthorized to modify this event'}), 403
        
        # Update publish status
        response = db.client.table('events').update({
            'is_published': is_published,
            'updated_at': datetime.now().isoformat()
        }).eq('id', event_id).execute()
        
        return jsonify({
            'success': True,
            'message': f'Event {"published" if is_published else "unpublished"} successfully',
            'is_published': is_published
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/featured', methods=['GET'])
def get_featured_events():
    """Get all featured events"""
    try:
        now = datetime.now().isoformat()
        
        response = db.client.table('events')\
            .select('*')\
            .eq('is_featured', True)\
            .eq('is_published', True)\
            .gt('ends_at', now)\
            .order('starts_at', desc=False)\
            .limit(10)\
            .execute()
        
        return jsonify({
            'success': True,
            'featured_events': response.data
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/upcoming', methods=['GET'])
def get_upcoming_events():
    """Get upcoming events"""
    try:
        now = datetime.now().isoformat()
        limit = request.args.get('limit', 10, type=int)
        
        response = db.client.table('events')\
            .select('*')\
            .eq('is_published', True)\
            .gt('starts_at', now)\
            .order('starts_at', desc=False)\
            .limit(limit)\
            .execute()
        
        return jsonify({
            'success': True,
            'upcoming_events': response.data,
            'count': len(response.data)
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/past', methods=['GET'])
def get_past_events():
    """Get past events"""
    try:
        now = datetime.now().isoformat()
        limit = request.args.get('limit', 10, type=int)
        
        response = db.client.table('events')\
            .select('*')\
            .eq('is_published', True)\
            .lt('ends_at', now)\
            .order('starts_at', desc=True)\
            .limit(limit)\
            .execute()
        
        return jsonify({
            'success': True,
            'past_events': response.data,
            'count': len(response.data)
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@event_bp.route('/stats', methods=['GET'])
def get_event_stats():
    """Get event statistics (admin only)"""
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
        
        now = datetime.now().isoformat()
        
        # Get various stats
        total_events = db.client.table('events').select('*', count='exact').execute()
        published_events = db.client.table('events').select('*', count='exact').eq('is_published', True).execute()
        featured_events = db.client.table('events').select('*', count='exact').eq('is_featured', True).execute()
        upcoming_events = db.client.table('events').select('*', count='exact').gt('starts_at', now).execute()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_events': total_events.count,
                'published_events': published_events.count,
                'featured_events': featured_events.count,
                'upcoming_events': upcoming_events.count,
                'draft_events': total_events.count - published_events.count
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500