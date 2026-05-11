from flask import Blueprint, request, jsonify
from utils.db import db
from datetime import datetime
import json
import uuid

delivery_zones_bp = Blueprint('delivery_zones', __name__)

def verify_token(token):
    """Verify JWT token and get user"""
    try:
        from utils.db import db
        user = db.client.auth.get_user(token)
        return user
    except:
        return None

def check_admin_access(user_id):
    """Check if user has admin access"""
    try:
        profile = db.client.table('profiles').select('role').eq('id', user_id).execute()
        if profile.data and profile.data[0].get('role') in ['admin', 'super_admin']:
            return True
        return False
    except:
        return False

def point_in_polygon(lat, lng, polygon_coords):
    """Check if a point is inside a polygon (Ray casting algorithm)"""
    try:
        x = float(lng)
        y = float(lat)
        inside = False
        n = len(polygon_coords)
        
        for i in range(n):
            x1, y1 = float(polygon_coords[i]['lng']), float(polygon_coords[i]['lat'])
            x2, y2 = float(polygon_coords[(i + 1) % n]['lng']), float(polygon_coords[(i + 1) % n]['lat'])
            
            # Check if point is on the boundary
            if (y1 == y2 and y == y1 and min(x1, x2) <= x <= max(x1, x2)):
                return True
            
            # Check if ray intersects with edge
            if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
                inside = not inside
        
        return inside
    except Exception as e:
        print(f"Error in point_in_polygon: {e}")
        return False

def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points using Haversine formula"""
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # Earth's radius in kilometers
    
    lat1, lng1, lat2, lng2 = map(radians, [float(lat1), float(lng1), float(lat2), float(lng2)])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    distance = R * c
    
    return distance

@delivery_zones_bp.route('/zones', methods=['POST'])
def create_delivery_zone():
    """Create a new delivery zone (admin only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Check admin access
        if not check_admin_access(user.id):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'delivery_fee']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'message': f'Missing required field: {field}'}), 400
        
        # Validate delivery fee
        if float(data['delivery_fee']) < 0:
            return jsonify({'success': False, 'message': 'Delivery fee cannot be negative'}), 400
        
        # Prepare zone data
        zone_data = {
            'name': data['name'],
            'description': data.get('description'),
            'delivery_fee': float(data['delivery_fee']),
            'min_order': float(data.get('min_order', 0)),
            'is_active': data.get('is_active', True),
            'polygon': json.dumps(data.get('polygon', [])),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        response = db.client.table('delivery_zones').insert(zone_data).execute()
        
        return jsonify({
            'success': True,
            'message': 'Delivery zone created successfully',
            'delivery_zone': response.data[0]
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@delivery_zones_bp.route('/zones', methods=['GET'])
def get_delivery_zones():
    """Get all delivery zones"""
    try:
        # Query parameters
        is_active = request.args.get('is_active')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Build query
        query = db.client.table('delivery_zones').select('*')
        
        if is_active is not None:
            query = query.eq('is_active', is_active.lower() == 'true')
        
        # Order by name
        query = query.order('name')
        
        # Apply pagination
        query = query.range(offset, offset + limit - 1)
        
        response = query.execute()
        
        # Get total count
        count_query = db.client.table('delivery_zones').select('*', count='exact')
        if is_active is not None:
            count_query = count_query.eq('is_active', is_active.lower() == 'true')
        count_response = count_query.execute()
        
        # Parse polygon JSON for each zone
        zones = []
        for zone in response.data:
            if zone.get('polygon'):
                try:
                    zone['polygon'] = json.loads(zone['polygon']) if isinstance(zone['polygon'], str) else zone['polygon']
                except:
                    zone['polygon'] = []
            zones.append(zone)
        
        return jsonify({
            'success': True,
            'delivery_zones': zones,
            'pagination': {
                'total': count_response.count,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < count_response.count
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@delivery_zones_bp.route('/zones/<zone_id>', methods=['GET'])
def get_delivery_zone(zone_id):
    """Get a single delivery zone by ID"""
    try:
        response = db.client.table('delivery_zones').select('*').eq('id', zone_id).execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Delivery zone not found'}), 404
        
        zone = response.data[0]
        
        # Parse polygon JSON
        if zone.get('polygon'):
            try:
                zone['polygon'] = json.loads(zone['polygon']) if isinstance(zone['polygon'], str) else zone['polygon']
            except:
                zone['polygon'] = []
        
        return jsonify({
            'success': True,
            'delivery_zone': zone
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@delivery_zones_bp.route('/zones/<zone_id>', methods=['PUT'])
def update_delivery_zone(zone_id):
    """Update a delivery zone (admin only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Check admin access
        if not check_admin_access(user.id):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        # Check if zone exists
        existing = db.client.table('delivery_zones').select('id').eq('id', zone_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'Delivery zone not found'}), 404
        
        data = request.get_json()
        
        # Prepare update data
        update_data = {
            'updated_at': datetime.now().isoformat()
        }
        
        # Allowed fields for update
        allowed_fields = ['name', 'description', 'delivery_fee', 'min_order', 'is_active', 'polygon']
        
        for field in allowed_fields:
            if field in data:
                if field == 'delivery_fee':
                    if float(data[field]) < 0:
                        return jsonify({'success': False, 'message': 'Delivery fee cannot be negative'}), 400
                    update_data[field] = float(data[field])
                elif field == 'min_order':
                    if float(data[field]) < 0:
                        return jsonify({'success': False, 'message': 'Minimum order cannot be negative'}), 400
                    update_data[field] = float(data[field])
                elif field == 'polygon':
                    update_data[field] = json.dumps(data[field])
                else:
                    update_data[field] = data[field]
        
        response = db.client.table('delivery_zones').update(update_data).eq('id', zone_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Delivery zone updated successfully',
            'delivery_zone': response.data[0]
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@delivery_zones_bp.route('/zones/<zone_id>', methods=['DELETE'])
def delete_delivery_zone(zone_id):
    """Delete a delivery zone (admin only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Check admin access
        if not check_admin_access(user.id):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        # Check if zone exists
        existing = db.client.table('delivery_zones').select('id').eq('id', zone_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'Delivery zone not found'}), 404
        
        # Delete zone
        db.client.table('delivery_zones').delete().eq('id', zone_id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Delivery zone deleted successfully'
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@delivery_zones_bp.route('/check-availability', methods=['POST'])
def check_delivery_availability():
    """Check if a location is within any delivery zone"""
    try:
        data = request.get_json()
        
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if not latitude or not longitude:
            return jsonify({'success': False, 'message': 'Latitude and longitude are required'}), 400
        
        # Get all active delivery zones
        zones_response = db.client.table('delivery_zones')\
            .select('*')\
            .eq('is_active', True)\
            .execute()
        
        available_zones = []
        
        for zone in zones_response.data:
            # Parse polygon
            polygon = zone.get('polygon')
            if polygon:
                try:
                    if isinstance(polygon, str):
                        polygon = json.loads(polygon)
                    
                    # Check if point is inside polygon
                    if point_in_polygon(latitude, longitude, polygon):
                        available_zones.append({
                            'id': zone['id'],
                            'name': zone['name'],
                            'delivery_fee': float(zone['delivery_fee']),
                            'min_order': float(zone['min_order']),
                            'description': zone.get('description')
                        })
                except Exception as e:
                    print(f"Error processing zone {zone['id']}: {e}")
                    continue
        
        is_available = len(available_zones) > 0
        
        return jsonify({
            'success': True,
            'is_available': is_available,
            'available_zones': available_zones,
            'message': 'Delivery available' if is_available else 'No delivery available to this location'
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@delivery_zones_bp.route('/calculate-fee', methods=['POST'])
def calculate_delivery_fee():
    """Calculate delivery fee based on location and order amount"""
    try:
        data = request.get_json()
        
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        order_amount = float(data.get('order_amount', 0))
        
        if not latitude or not longitude:
            return jsonify({'success': False, 'message': 'Latitude and longitude are required'}), 400
        
        # Get all active delivery zones
        zones_response = db.client.table('delivery_zones')\
            .select('*')\
            .eq('is_active', True)\
            .execute()
        
        applicable_zones = []
        
        for zone in zones_response.data:
            # Parse polygon
            polygon = zone.get('polygon')
            if polygon:
                try:
                    if isinstance(polygon, str):
                        polygon = json.loads(polygon)
                    
                    # Check if point is inside polygon
                    if point_in_polygon(latitude, longitude, polygon):
                        min_order = float(zone.get('min_order', 0))
                        delivery_fee = float(zone['delivery_fee'])
                        
                        # Check if order meets minimum requirement
                        if order_amount >= min_order:
                            applicable_zones.append({
                                'zone_id': zone['id'],
                                'zone_name': zone['name'],
                                'delivery_fee': delivery_fee,
                                'min_order': min_order,
                                'waived': False
                            })
                        else:
                            # Still return but indicate fee is not waived
                            applicable_zones.append({
                                'zone_id': zone['id'],
                                'zone_name': zone['name'],
                                'delivery_fee': delivery_fee,
                                'min_order': min_order,
                                'waived': False,
                                'message': f'Minimum order of {min_order} required for delivery'
                            })
                except Exception as e:
                    print(f"Error processing zone {zone['id']}: {e}")
                    continue
        
        if not applicable_zones:
            return jsonify({
                'success': True,
                'is_deliverable': False,
                'message': 'No delivery available to this location'
            }), 200
        
        # Select the zone with lowest delivery fee
        best_zone = min(applicable_zones, key=lambda x: x['delivery_fee'])
        
        return jsonify({
            'success': True,
            'is_deliverable': True,
            'delivery_fee': best_zone['delivery_fee'],
            'zone': {
                'id': best_zone['zone_id'],
                'name': best_zone['zone_name'],
                'min_order': best_zone['min_order']
            },
            'meets_min_order': order_amount >= best_zone['min_order'],
            'message': f'Delivery fee: {best_zone["delivery_fee"]}' if order_amount >= best_zone['min_order'] else f'Add {best_zone["min_order"] - order_amount} more for delivery'
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@delivery_zones_bp.route('/validate-address', methods=['POST'])
def validate_delivery_address():
    """Validate a delivery address against delivery zones"""
    try:
        data = request.get_json()
        
        address_line1 = data.get('address_line1')
        city = data.get('city')
        state = data.get('state')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if not latitude or not longitude:
            return jsonify({'success': False, 'message': 'Latitude and longitude are required'}), 400
        
        # Get all active delivery zones
        zones_response = db.client.table('delivery_zones')\
            .select('*')\
            .eq('is_active', True)\
            .execute()
        
        matching_zone = None
        
        for zone in zones_response.data:
            polygon = zone.get('polygon')
            if polygon:
                try:
                    if isinstance(polygon, str):
                        polygon = json.loads(polygon)
                    
                    if point_in_polygon(latitude, longitude, polygon):
                        matching_zone = {
                            'id': zone['id'],
                            'name': zone['name'],
                            'delivery_fee': float(zone['delivery_fee']),
                            'min_order': float(zone['min_order']),
                            'description': zone.get('description')
                        }
                        break
                except Exception as e:
                    print(f"Error processing zone {zone['id']}: {e}")
                    continue
        
        is_valid = matching_zone is not None
        
        return jsonify({
            'success': True,
            'is_valid': is_valid,
            'delivery_zone': matching_zone,
            'address': {
                'line1': address_line1,
                'city': city,
                'state': state,
                'latitude': latitude,
                'longitude': longitude
            },
            'message': 'Address is within delivery zone' if is_valid else 'Address is not within any delivery zone'
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@delivery_zones_bp.route('/zones/<zone_id>/stats', methods=['GET'])
def get_zone_statistics(zone_id):
    """Get statistics for a delivery zone (admin only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Check admin access
        if not check_admin_access(user.id):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        # Get zone details
        zone_response = db.client.table('delivery_zones').select('*').eq('id', zone_id).execute()
        if not zone_response.data:
            return jsonify({'success': False, 'message': 'Delivery zone not found'}), 404
        
        zone = zone_response.data[0]
        
        # Get orders that used this zone (assuming orders table has delivery_zone_id)
        # Note: You may need to add delivery_zone_id to orders table
        try:
            orders_response = db.client.table('orders')\
                .select('*', count='exact')\
                .eq('delivery_zone_id', zone_id)\
                .execute()
            total_orders = orders_response.count
        except:
            total_orders = 0
        
        return jsonify({
            'success': True,
            'zone': {
                'id': zone['id'],
                'name': zone['name'],
                'delivery_fee': float(zone['delivery_fee']),
                'min_order': float(zone['min_order']),
                'is_active': zone['is_active'],
                'created_at': zone['created_at'],
                'updated_at': zone['updated_at']
            },
            'statistics': {
                'total_orders': total_orders,
                'estimated_revenue': total_orders * float(zone['delivery_fee'])
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@delivery_zones_bp.route('/batch-update', methods=['POST'])
def batch_update_zones():
    """Batch update multiple delivery zones (admin only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Check admin access
        if not check_admin_access(user.id):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        data = request.get_json()
        zones = data.get('zones', [])
        
        if not zones:
            return jsonify({'success': False, 'message': 'No zones provided for batch update'}), 400
        
        updated_zones = []
        errors = []
        
        for zone_data in zones:
            try:
                zone_id = zone_data.get('id')
                if not zone_id:
                    errors.append({'zone': zone_data, 'error': 'Zone ID required'})
                    continue
                
                # Prepare update data
                update_data = {'updated_at': datetime.now().isoformat()}
                
                allowed_fields = ['name', 'description', 'delivery_fee', 'min_order', 'is_active', 'polygon']
                for field in allowed_fields:
                    if field in zone_data:
                        if field in ['delivery_fee', 'min_order']:
                            update_data[field] = float(zone_data[field])
                        elif field == 'polygon':
                            update_data[field] = json.dumps(zone_data[field])
                        else:
                            update_data[field] = zone_data[field]
                
                response = db.client.table('delivery_zones').update(update_data).eq('id', zone_id).execute()
                updated_zones.append(response.data[0])
                
            except Exception as e:
                errors.append({'zone': zone_data, 'error': str(e)})
        
        return jsonify({
            'success': True,
            'message': f'Updated {len(updated_zones)} zones, {len(errors)} errors',
            'updated_zones': updated_zones,
            'errors': errors
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500