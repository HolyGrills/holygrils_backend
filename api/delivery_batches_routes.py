from flask import Blueprint, request, jsonify
from utils.db import db
from datetime import datetime

delivery_batches_bp = Blueprint('delivery_batches', __name__)


def verify_token(token):
    try:
        user = db.client.auth.get_user(token)
        return user
    except:
        return None


def check_admin_or_rider_manager(user_id):
    try:
        profile = db.client.table('profiles').select('role').eq('id', user_id).execute()
        if profile.data and profile.data[0].get('role') in ['admin', 'super_admin', 'rider_manager']:
            return True
        return False
    except:
        return False


def check_rider_access(user_id, rider_id):
    try:
        if user_id == rider_id:
            return True
        profile = db.client.table('profiles').select('role').eq('id', user_id).execute()
        if profile.data and profile.data[0].get('role') in ['admin', 'super_admin', 'rider_manager']:
            return True
        return False
    except:
        return False


@delivery_batches_bp.route('/batches', methods=['POST'])
def create_delivery_batch():
    """
    Create a new delivery batch
    ---
    tags:
      - Delivery Batches
    security:
      - BearerAuth: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [zone]
          properties:
            zone:
              type: string
              example: Zone A
            notes:
              type: string
            delivery_window_id:
              type: string
            window_id:
              type: string
    responses:
      201:
        description: Batch created successfully
        schema:
          properties:
            success: {type: boolean}
            message: {type: string}
            delivery_batch: {type: object}
      400:
        description: Zone is required
      401:
        description: Unauthorized
      403:
        description: Admin or rider manager access required
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        if not check_admin_or_rider_manager(user.id):
            return jsonify({'success': False, 'message': 'Admin or rider manager access required'}), 403

        data = request.get_json()
        if not data.get('zone'):
            return jsonify({'success': False, 'message': 'Zone is required'}), 400

        batch_data = {k: v for k, v in {
            'status': 'open',
            'notes': data.get('notes'),
            'zone': data['zone'],
            'delivery_window_id': data.get('delivery_window_id'),
            'window_id': data.get('window_id'),
            'created_at': datetime.now().isoformat()
        }.items() if v is not None}

        response = db.client.table('delivery_batches').insert(batch_data).execute()
        return jsonify({'success': True, 'message': 'Delivery batch created successfully',
                        'delivery_batch': response.data[0]}), 201
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/batches', methods=['GET'])
def get_delivery_batches():
    """
    Get all delivery batches with optional filtering
    ---
    tags:
      - Delivery Batches
    security:
      - BearerAuth: []
    parameters:
      - in: query
        name: status
        type: string
        enum: [open, assigned, in_progress, completed, cancelled]
      - in: query
        name: rider_id
        type: string
      - in: query
        name: zone
        type: string
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: List of delivery batches
        schema:
          properties:
            success: {type: boolean}
            delivery_batches: {type: array, items: {type: object}}
            pagination:
              type: object
              properties:
                total: {type: integer}
                limit: {type: integer}
                offset: {type: integer}
                has_more: {type: boolean}
      401:
        description: Unauthorized
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401

        status = request.args.get('status')
        rider_id = request.args.get('rider_id')
        zone = request.args.get('zone')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        query = db.client.table('delivery_batches').select('*, rider:profiles!rider_id(full_name, email, phone)')
        if status: query = query.eq('status', status)
        if rider_id: query = query.eq('rider_id', rider_id)
        if zone: query = query.eq('zone', zone)
        query = query.order('created_at', desc=True).range(offset, offset + limit - 1)
        response = query.execute()

        count_query = db.client.table('delivery_batches').select('*', count='exact')
        if status: count_query = count_query.eq('status', status)
        if rider_id: count_query = count_query.eq('rider_id', rider_id)
        if zone: count_query = count_query.eq('zone', zone)
        count_response = count_query.execute()

        return jsonify({
            'success': True,
            'delivery_batches': response.data,
            'pagination': {
                'total': count_response.count,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < count_response.count
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/batches/<batch_id>', methods=['GET'])
def get_delivery_batch(batch_id):
    """
    Get a single delivery batch by ID
    ---
    tags:
      - Delivery Batches
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
    responses:
      200:
        description: Batch details with rider and orders
        schema:
          properties:
            success: {type: boolean}
            delivery_batch: {type: object}
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Batch not found
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401

        response = db.client.table('delivery_batches')\
            .select('*, rider:profiles!rider_id(full_name, email, phone), orders:orders(*)')\
            .eq('id', batch_id).execute()

        if not response.data:
            return jsonify({'success': False, 'message': 'Delivery batch not found'}), 404

        batch = response.data[0]
        if batch.get('rider_id') and not check_rider_access(user.id, batch['rider_id']):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

        return jsonify({'success': True, 'delivery_batch': batch}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/batches/<batch_id>', methods=['PUT'])
def update_delivery_batch(batch_id):
    """
    Update a delivery batch
    ---
    tags:
      - Delivery Batches
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            status:
              type: string
              enum: [open, assigned, in_progress, completed, cancelled]
            notes: {type: string}
            zone: {type: string}
            delivery_window_id: {type: string}
            window_id: {type: string}
    responses:
      200:
        description: Batch updated successfully
        schema:
          properties:
            success: {type: boolean}
            message: {type: string}
            delivery_batch: {type: object}
      400:
        description: Invalid status transition or no fields to update
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Batch not found
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401

        existing = db.client.table('delivery_batches').select('*').eq('id', batch_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'Delivery batch not found'}), 404

        batch = existing.data[0]
        if batch.get('rider_id'):
            if not check_rider_access(user.id, batch['rider_id']):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        elif not check_admin_or_rider_manager(user.id):
            return jsonify({'success': False, 'message': 'Admin or rider manager access required'}), 403

        data = request.get_json()
        update_data = {f: data[f] for f in ['status', 'notes', 'zone', 'delivery_window_id', 'window_id'] if f in data}

        if 'status' in update_data:
            valid_transitions = {
                'open': ['assigned', 'cancelled'],
                'assigned': ['in_progress', 'cancelled'],
                'in_progress': ['completed', 'cancelled'],
                'completed': [], 'cancelled': []
            }
            current_status = batch['status']
            new_status = update_data['status']
            if new_status not in valid_transitions.get(current_status, []):
                return jsonify({'success': False,
                                'message': f'Invalid status transition from {current_status} to {new_status}'}), 400
            if new_status == 'completed' and not batch.get('completed_at'):
                update_data['completed_at'] = datetime.now().isoformat()

        if not update_data:
            return jsonify({'success': False, 'message': 'No fields to update'}), 400

        response = db.client.table('delivery_batches').update(update_data).eq('id', batch_id).execute()
        return jsonify({'success': True, 'message': 'Delivery batch updated successfully',
                        'delivery_batch': response.data[0]}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/batches/<batch_id>/assign-rider', methods=['POST'])
def assign_rider_to_batch(batch_id):
    """
    Assign a rider to a delivery batch
    ---
    tags:
      - Delivery Batches
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [rider_id]
          properties:
            rider_id: {type: string}
    responses:
      200:
        description: Rider assigned successfully
        schema:
          properties:
            success: {type: boolean}
            message: {type: string}
            delivery_batch: {type: object}
      400:
        description: Rider ID missing, batch not open, or user is not a rider
      401:
        description: Unauthorized
      403:
        description: Admin or rider manager access required
      404:
        description: Batch or rider not found
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        if not check_admin_or_rider_manager(user.id):
            return jsonify({'success': False, 'message': 'Admin or rider manager access required'}), 403

        existing = db.client.table('delivery_batches').select('*').eq('id', batch_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'Delivery batch not found'}), 404

        batch = existing.data[0]
        if batch['status'] != 'open':
            return jsonify({'success': False,
                            'message': f'Cannot assign rider to batch with status {batch["status"]}'}), 400

        data = request.get_json()
        rider_id = data.get('rider_id')
        if not rider_id:
            return jsonify({'success': False, 'message': 'Rider ID is required'}), 400

        rider_response = db.client.table('profiles').select('role, full_name').eq('id', rider_id).execute()
        if not rider_response.data:
            return jsonify({'success': False, 'message': 'Rider not found'}), 404

        rider = rider_response.data[0]
        if rider['role'] not in ['delivery_rider', 'admin', 'super_admin']:
            return jsonify({'success': False, 'message': 'User is not a delivery rider'}), 400

        response = db.client.table('delivery_batches').update({
            'rider_id': rider_id, 'status': 'assigned',
            'updated_at': datetime.now().isoformat()
        }).eq('id', batch_id).execute()

        return jsonify({'success': True,
                        'message': f'Rider {rider["full_name"]} assigned to batch successfully',
                        'delivery_batch': response.data[0]}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/batches/<batch_id>/add-orders', methods=['POST'])
def add_orders_to_batch(batch_id):
    """
    Add orders to a delivery batch
    ---
    tags:
      - Delivery Batches
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [order_ids]
          properties:
            order_ids:
              type: array
              items: {type: string}
              example: ["order-uuid-1", "order-uuid-2"]
    responses:
      200:
        description: Orders processed (check errors array for partial failures)
        schema:
          properties:
            success: {type: boolean}
            message: {type: string}
            updated_orders: {type: array, items: {type: object}}
            errors:
              type: array
              items:
                type: object
                properties:
                  order_id: {type: string}
                  error: {type: string}
      400:
        description: Order IDs missing or batch is completed/cancelled
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Batch not found
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401

        existing = db.client.table('delivery_batches').select('*').eq('id', batch_id).execute()
        if not existing.data:
            return jsonify({'success': False, 'message': 'Delivery batch not found'}), 404

        batch = existing.data[0]
        if batch.get('rider_id'):
            if not check_rider_access(user.id, batch['rider_id']):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        elif not check_admin_or_rider_manager(user.id):
            return jsonify({'success': False, 'message': 'Admin or rider manager access required'}), 403

        if batch['status'] in ['completed', 'cancelled']:
            return jsonify({'success': False,
                            'message': f'Cannot add orders to {batch["status"]} batch'}), 400

        data = request.get_json()
        order_ids = data.get('order_ids', [])
        if not order_ids:
            return jsonify({'success': False, 'message': 'Order IDs are required'}), 400

        updated_orders, errors = [], []
        for order_id in order_ids:
            try:
                order_response = db.client.table('orders').select('status, delivery_batch_id').eq('id', order_id).execute()
                if not order_response.data:
                    errors.append({'order_id': order_id, 'error': 'Order not found'}); continue
                order = order_response.data[0]
                if order.get('delivery_batch_id'):
                    errors.append({'order_id': order_id, 'error': 'Order already assigned to a batch'}); continue
                if order['status'] not in ['ready', 'assigned']:
                    errors.append({'order_id': order_id, 'error': f'Order status {order["status"]} not ready for delivery'}); continue
                update_response = db.client.table('orders').update({
                    'delivery_batch_id': batch_id, 'status': 'assigned',
                    'updated_at': datetime.now().isoformat()
                }).eq('id', order_id).execute()
                updated_orders.append(update_response.data[0])
            except Exception as e:
                errors.append({'order_id': order_id, 'error': str(e)})

        return jsonify({'success': True,
                        'message': f'Added {len(updated_orders)} orders to batch, {len(errors)} errors',
                        'updated_orders': updated_orders, 'errors': errors}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/batches/<batch_id>/orders', methods=['GET'])
def get_batch_orders(batch_id):
    """
    Get all orders in a delivery batch
    ---
    tags:
      - Delivery Batches
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
    responses:
      200:
        description: Orders in the batch with user and item details
        schema:
          properties:
            success: {type: boolean}
            batch: {type: object}
            orders: {type: array, items: {type: object}}
            total_orders: {type: integer}
      401:
        description: Unauthorized
      403:
        description: Forbidden
      404:
        description: Batch not found
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401

        batch_response = db.client.table('delivery_batches').select('*').eq('id', batch_id).execute()
        if not batch_response.data:
            return jsonify({'success': False, 'message': 'Delivery batch not found'}), 404

        batch = batch_response.data[0]
        if batch.get('rider_id') and not check_rider_access(user.id, batch['rider_id']):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403

        orders_response = db.client.table('orders')\
            .select('*, user:profiles!user_id(full_name, email, phone), order_items(*, menu_items(*))')\
            .eq('delivery_batch_id', batch_id).execute()

        return jsonify({'success': True, 'batch': batch,
                        'orders': orders_response.data,
                        'total_orders': len(orders_response.data)}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/batches/<batch_id>/start-delivery', methods=['POST'])
def start_delivery(batch_id):
    """
    Start delivery for a batch (assigned rider or admin only)
    ---
    tags:
      - Delivery Batches
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
    responses:
      200:
        description: Delivery started, all orders set to out_for_delivery
        schema:
          properties:
            success: {type: boolean}
            message: {type: string}
            delivery_batch: {type: object}
      400:
        description: Batch is not in assigned status
      401:
        description: Unauthorized
      403:
        description: Only assigned rider can start delivery
      404:
        description: Batch not found
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401

        batch_response = db.client.table('delivery_batches').select('*').eq('id', batch_id).execute()
        if not batch_response.data:
            return jsonify({'success': False, 'message': 'Delivery batch not found'}), 404

        batch = batch_response.data[0]
        if batch.get('rider_id') != user.id:
            profile = db.client.table('profiles').select('role').eq('id', user.id).execute()
            if not profile.data or profile.data[0].get('role') not in ['admin', 'super_admin']:
                return jsonify({'success': False, 'message': 'Only assigned rider can start delivery'}), 403

        if batch['status'] != 'assigned':
            return jsonify({'success': False,
                            'message': f'Cannot start delivery for batch with status {batch["status"]}'}), 400

        now = datetime.now().isoformat()
        response = db.client.table('delivery_batches').update(
            {'status': 'in_progress', 'updated_at': now}).eq('id', batch_id).execute()
        db.client.table('orders').update(
            {'status': 'out_for_delivery', 'out_for_delivery_at': now, 'updated_at': now}
        ).eq('delivery_batch_id', batch_id).execute()

        return jsonify({'success': True, 'message': 'Delivery started successfully',
                        'delivery_batch': response.data[0]}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/batches/<batch_id>/complete-delivery', methods=['POST'])
def complete_delivery(batch_id):
    """
    Complete delivery for a batch (assigned rider or admin only)
    ---
    tags:
      - Delivery Batches
    security:
      - BearerAuth: []
    parameters:
      - in: path
        name: batch_id
        type: string
        required: true
    responses:
      200:
        description: Delivery completed, all orders set to delivered
        schema:
          properties:
            success: {type: boolean}
            message: {type: string}
            delivery_batch: {type: object}
      400:
        description: Batch is not in in_progress status
      401:
        description: Unauthorized
      403:
        description: Only assigned rider can complete delivery
      404:
        description: Batch not found
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401

        batch_response = db.client.table('delivery_batches').select('*').eq('id', batch_id).execute()
        if not batch_response.data:
            return jsonify({'success': False, 'message': 'Delivery batch not found'}), 404

        batch = batch_response.data[0]
        if batch.get('rider_id') != user.id:
            profile = db.client.table('profiles').select('role').eq('id', user.id).execute()
            if not profile.data or profile.data[0].get('role') not in ['admin', 'super_admin']:
                return jsonify({'success': False, 'message': 'Only assigned rider can complete delivery'}), 403

        if batch['status'] != 'in_progress':
            return jsonify({'success': False,
                            'message': f'Cannot complete delivery for batch with status {batch["status"]}'}), 400

        now = datetime.now().isoformat()
        response = db.client.table('delivery_batches').update(
            {'status': 'completed', 'completed_at': now, 'updated_at': now}).eq('id', batch_id).execute()
        db.client.table('orders').update(
            {'status': 'delivered', 'delivered_at': now, 'updated_at': now}
        ).eq('delivery_batch_id', batch_id).execute()

        return jsonify({'success': True, 'message': 'Delivery completed successfully',
                        'delivery_batch': response.data[0]}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/rider/my-batches', methods=['GET'])
def get_rider_batches():
    """
    Get batches assigned to the currently authenticated rider
    ---
    tags:
      - Rider
    security:
      - BearerAuth: []
    parameters:
      - in: query
        name: status
        type: string
        enum: [open, assigned, in_progress, completed, cancelled]
      - in: query
        name: limit
        type: integer
        default: 20
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: Rider's batches with pagination
        schema:
          properties:
            success: {type: boolean}
            batches: {type: array, items: {type: object}}
            pagination:
              type: object
              properties:
                total: {type: integer}
                limit: {type: integer}
                offset: {type: integer}
                has_more: {type: boolean}
      401:
        description: Unauthorized
      403:
        description: Only delivery riders can access this endpoint
      404:
        description: User not found
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401

        profile = db.client.table('profiles').select('role').eq('id', user.id).execute()
        if not profile.data:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        if profile.data[0].get('role') not in ['delivery_rider', 'admin', 'super_admin']:
            return jsonify({'success': False, 'message': 'Access denied. Only delivery riders can access this endpoint.'}), 403

        status = request.args.get('status')
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)

        query = db.client.table('delivery_batches').select('*, orders:orders(count)').eq('rider_id', user.id)
        if status: query = query.eq('status', status)
        query = query.order('created_at', desc=True).range(offset, offset + limit - 1)
        response = query.execute()

        count_query = db.client.table('delivery_batches').select('*', count='exact').eq('rider_id', user.id)
        if status: count_query = count_query.eq('status', status)
        count_response = count_query.execute()

        return jsonify({
            'success': True,
            'batches': response.data,
            'pagination': {
                'total': count_response.count,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < count_response.count
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/stats', methods=['GET'])
def get_batch_statistics():
    """
    Get delivery batch statistics (admin/rider manager only)
    ---
    tags:
      - Admin
    security:
      - BearerAuth: []
    responses:
      200:
        description: Aggregated batch statistics and per-rider performance
        schema:
          properties:
            success: {type: boolean}
            statistics:
              type: object
              properties:
                total_batches: {type: integer}
                open_batches: {type: integer}
                assigned_batches: {type: integer}
                in_progress_batches: {type: integer}
                completed_batches: {type: integer}
                cancelled_batches: {type: integer}
                average_completion_time_minutes: {type: number}
                completion_rate: {type: number}
            rider_performance:
              type: array
              items:
                type: object
                properties:
                  rider_name: {type: string}
                  total_batches: {type: integer}
                  completed_batches: {type: integer}
                  cancelled_batches: {type: integer}
      401:
        description: Unauthorized
      403:
        description: Admin or rider manager access required
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        if not check_admin_or_rider_manager(user.id):
            return jsonify({'success': False, 'message': 'Admin or rider manager access required'}), 403

        batches = db.client.table('delivery_batches').select('status, created_at, completed_at').execute().data
        total = len(batches)

        completion_times = []
        for b in batches:
            if b['status'] == 'completed' and b.get('created_at') and b.get('completed_at'):
                created = datetime.fromisoformat(b['created_at'].replace('Z', '+00:00'))
                completed = datetime.fromisoformat(b['completed_at'].replace('Z', '+00:00'))
                completion_times.append((completed - created).total_seconds() / 60)

        completed_count = len([b for b in batches if b['status'] == 'completed'])

        rider_stats = db.client.table('delivery_batches')\
            .select('rider_id, status, rider:profiles!rider_id(full_name)').execute().data

        rider_performance = {}
        for b in rider_stats:
            if b.get('rider_id'):
                rid = b['rider_id']
                if rid not in rider_performance:
                    rider_performance[rid] = {
                        'rider_name': b.get('rider', {}).get('full_name', 'Unknown'),
                        'total_batches': 0, 'completed_batches': 0, 'cancelled_batches': 0
                    }
                rider_performance[rid]['total_batches'] += 1
                if b['status'] == 'completed': rider_performance[rid]['completed_batches'] += 1
                elif b['status'] == 'cancelled': rider_performance[rid]['cancelled_batches'] += 1

        return jsonify({
            'success': True,
            'statistics': {
                'total_batches': total,
                'open_batches': len([b for b in batches if b['status'] == 'open']),
                'assigned_batches': len([b for b in batches if b['status'] == 'assigned']),
                'in_progress_batches': len([b for b in batches if b['status'] == 'in_progress']),
                'completed_batches': completed_count,
                'cancelled_batches': len([b for b in batches if b['status'] == 'cancelled']),
                'average_completion_time_minutes': round(sum(completion_times) / len(completion_times), 2) if completion_times else 0,
                'completion_rate': round((completed_count / total * 100), 2) if total > 0 else 0
            },
            'rider_performance': list(rider_performance.values())
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@delivery_batches_bp.route('/available-riders', methods=['GET'])
def get_available_riders():
    """
    Get available and busy riders for batch assignment (admin/rider manager only)
    ---
    tags:
      - Admin
    security:
      - BearerAuth: []
    responses:
      200:
        description: Riders split into available and busy lists
        schema:
          properties:
            success: {type: boolean}
            available_riders:
              type: array
              items:
                type: object
                properties:
                  id: {type: string}
                  full_name: {type: string}
                  email: {type: string}
                  phone: {type: string}
                  is_available: {type: boolean}
                  current_load: {type: integer}
            busy_riders:
              type: array
              items: {type: object}
            total_riders: {type: integer}
      401:
        description: Unauthorized
      403:
        description: Admin or rider manager access required
      500:
        description: Server error
    """
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        if not check_admin_or_rider_manager(user.id):
            return jsonify({'success': False, 'message': 'Admin or rider manager access required'}), 403

        riders_response = db.client.table('profiles')\
            .select('id, full_name, email, phone')\
            .in_('role', ['delivery_rider', 'admin', 'super_admin'])\
            .eq('is_active', True).execute()

        active_batches = db.client.table('delivery_batches')\
            .select('rider_id').in_('status', ['assigned', 'in_progress']).execute()
        active_riders = {b['rider_id'] for b in active_batches.data if b.get('rider_id')}

        riders = [{**r, 'is_available': r['id'] not in active_riders,
                   'current_load': 1 if r['id'] in active_riders else 0}
                  for r in riders_response.data]

        return jsonify({
            'success': True,
            'available_riders': [r for r in riders if r['is_available']],
            'busy_riders': [r for r in riders if not r['is_available']],
            'total_riders': len(riders)
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500