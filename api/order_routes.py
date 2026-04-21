from flask import Blueprint, request, jsonify
from utils.db import db
from datetime import datetime
import uuid
import json

order_bp = Blueprint('orders', __name__)

def verify_token(token):
    """Verify JWT token and get user"""
    try:
        from utils.db import db
        user = db.client.auth.get_user(token)
        return user
    except:
        return None

def generate_order_number():
    """Generate a unique order number"""
    return f"HG-{uuid.uuid4().hex[:10].upper()}"

@order_bp.route('/create', methods=['POST'])
def create_order():
    """Create a new order"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        data = request.get_json()
        
        # Get user profile for email and phone
        profile_response = db.client.table('profiles').select('email, phone, full_name').eq('id', user.id).execute()
        user_email = profile_response.data[0]['email'] if profile_response.data else None
        user_phone = profile_response.data[0]['phone'] if profile_response.data else None
        user_name = profile_response.data[0]['full_name'] if profile_response.data else None
        
        # Calculate totals and prepare order items
        subtotal = 0
        total_hp_earned = 0
        order_items_data = []
        
        for item in data.get('items', []):
            # Get menu item details
            menu_response = db.client.table('menu_items').select('*').eq('id', item['menu_item_id']).execute()
            if not menu_response.data:
                return jsonify({'success': False, 'message': f'Menu item {item["menu_item_id"]} not found'}), 400
            
            menu_item = menu_response.data[0]
            price = float(menu_item['price'])
            quantity = item['quantity']
            line_total = price * quantity
            
            subtotal += line_total
            total_hp_earned += (menu_item.get('hp_earn', 0) * quantity)
            
            # Prepare order item snapshot
            order_items_data.append({
                'menu_item_id': item['menu_item_id'],
                'name_snapshot': menu_item['name'],
                'price_snapshot': str(price),
                'hp_earn_snapshot': menu_item.get('hp_earn', 0),
                'quantity': quantity,
                'options_snapshot': json.dumps(item.get('options', {})),
                'line_total': str(line_total)
            })
        
        # Calculate final totals
        delivery_fee = float(data.get('delivery_fee', 0))
        discount_amount = float(data.get('discount_amount', 0))
        hp_redeemed = int(data.get('hp_redeemed', 0))
        wallet_amount_used = float(data.get('wallet_amount_used', 0))
        card_amount_used = float(data.get('card_amount_used', subtotal + delivery_fee - discount_amount - wallet_amount_used))
        
        total_amount = subtotal + delivery_fee - discount_amount - wallet_amount_used - card_amount_used
        
        # Create order
        order_number = generate_order_number()
        now = datetime.now().isoformat()
        
        # Handle delivery address snapshot
        delivery_address_snapshot = data.get('delivery_address')
        if isinstance(delivery_address_snapshot, dict):
            delivery_address_snapshot = json.dumps(delivery_address_snapshot)
        
        order_data = {
            'order_number': order_number,
            'user_id': user.id,
            'guest_email': user_email if not data.get('guest_email') else data.get('guest_email'),
            'guest_phone': user_phone if not data.get('guest_phone') else data.get('guest_phone'),
            'status': 'pending',
            'payment_status': data.get('payment_status', 'pending'),
            'subtotal': str(subtotal),
            'delivery_fee': str(delivery_fee),
            'discount_amount': str(discount_amount),
            'total_amount': str(total_amount),
            'hp_earned': total_hp_earned,
            'hp_redeemed': hp_redeemed,
            'wallet_amount_used': str(wallet_amount_used),
            'card_amount_used': str(card_amount_used),
            'delivery_address_snapshot': delivery_address_snapshot,
            'notes': data.get('notes'),
            'scheduled_for': data.get('scheduled_for'),
            'created_at': now,
            'updated_at': now
        }
        
        # Remove None values
        order_data = {k: v for k, v in order_data.items() if v is not None}
        
        order_response = db.client.table('orders').insert(order_data).execute()
        order_id = order_response.data[0]['id']
        
        # Create order items
        for item_data in order_items_data:
            item_data['order_id'] = order_id
            item_data['created_at'] = now
            db.client.table('order_items').insert(item_data).execute()
        
        # Create status log
        status_log_data = {
            'order_id': order_id,
            'status': 'pending',
            'changed_by': user.id,
            'note': 'Order created',
            'metadata': json.dumps({'source': 'api_create'}),
            'created_at': now
        }
        db.client.table('order_status_logs').insert(status_log_data).execute()
        
        return jsonify({
            'success': True,
            'message': 'Order created successfully',
            'order_id': order_id,
            'order_number': order_number,
            'total_amount': total_amount,
            'hp_earned': total_hp_earned
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@order_bp.route('/my-orders', methods=['GET'])
def get_user_orders():
    """Get current user's orders with items"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get pagination parameters
        limit = request.args.get('limit', 20, type=int)
        offset = request.args.get('offset', 0, type=int)
        status = request.args.get('status')
        
        # Build query
        query = db.client.table('orders')\
            .select('*')\
            .eq('user_id', user.id)\
            .order('created_at', desc=True)\
            .range(offset, offset + limit - 1)
        
        if status:
            query = query.eq('status', status)
        
        response = query.execute()
        
        # Get order items for each order
        orders_with_items = []
        for order in response.data:
            items_response = db.client.table('order_items')\
                .select('*')\
                .eq('order_id', order['id'])\
                .execute()
            
            # Get status logs
            logs_response = db.client.table('order_status_logs')\
                .select('*')\
                .eq('order_id', order['id'])\
                .order('created_at', desc=True)\
                .execute()
            
            # Get review if exists
            review_response = db.client.table('order_reviews')\
                .select('*')\
                .eq('order_id', order['id'])\
                .execute()
            
            order['items'] = items_response.data
            order['status_logs'] = logs_response.data
            order['review'] = review_response.data[0] if review_response.data else None
            
            orders_with_items.append(order)
        
        # Get total count
        count_query = db.client.table('orders').select('*', count='exact').eq('user_id', user.id)
        if status:
            count_query = count_query.eq('status', status)
        count_response = count_query.execute()
        
        return jsonify({
            'success': True,
            'orders': orders_with_items,
            'pagination': {
                'total': count_response.count,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < count_response.count
            }
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@order_bp.route('/<order_id>', methods=['GET'])
def get_order_details(order_id):
    """Get detailed order information"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get order details
        order_response = db.client.table('orders').select('*').eq('id', order_id).execute()
        
        if not order_response.data:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order = order_response.data[0]
        
        # Check if user owns the order
        if order['user_id'] != user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Get order items
        items_response = db.client.table('order_items')\
            .select('*')\
            .eq('order_id', order_id)\
            .execute()
        
        # Get status logs
        logs_response = db.client.table('order_status_logs')\
            .select('*')\
            .eq('order_id', order_id)\
            .order('created_at', desc=True)\
            .execute()
        
        # Get review if exists
        review_response = db.client.table('order_reviews')\
            .select('*')\
            .eq('order_id', order_id)\
            .execute()
        
        order['items'] = items_response.data
        order['status_logs'] = logs_response.data
        order['review'] = review_response.data[0] if review_response.data else None
        
        return jsonify({
            'success': True,
            'order': order
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@order_bp.route('/<order_id>/status', methods=['GET'])
def get_order_status(order_id):
    """Get order status and timeline"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get order details
        order_response = db.client.table('orders')\
            .select('id, order_number, status, payment_status, total_amount, created_at, updated_at')\
            .eq('id', order_id)\
            .execute()
        
        if not order_response.data:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order = order_response.data[0]
        
        # Check if user owns the order
        order_detail = db.client.table('orders').select('user_id').eq('id', order_id).execute()
        if order_detail.data and order_detail.data[0]['user_id'] != user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Get status logs
        logs_response = db.client.table('order_status_logs')\
            .select('*')\
            .eq('order_id', order_id)\
            .order('created_at', asc=True)\
            .execute()
        
        # Build status timeline
        timeline = []
        for log in logs_response.data:
            timeline.append({
                'status': log['status'],
                'timestamp': log['created_at'],
                'note': log.get('note'),
                'changed_by': log.get('changed_by')
            })
        
        return jsonify({
            'success': True,
            'order_number': order['order_number'],
            'current_status': order['status'],
            'payment_status': order['payment_status'],
            'total_amount': order['total_amount'],
            'created_at': order['created_at'],
            'updated_at': order['updated_at'],
            'timeline': timeline
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@order_bp.route('/<order_id>/update-status', methods=['PUT'])
def update_order_status(order_id):
    """Update order status (Admin/Delivery person only)"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        data = request.get_json()
        new_status = data.get('status')
        note = data.get('note', '')
        
        if not new_status:
            return jsonify({'success': False, 'message': 'Status is required'}), 400
        
        # Valid status transitions
        valid_statuses = ['pending', 'confirmed', 'preparing', 'ready', 'assigned', 'out_for_delivery', 'delivered', 'cancelled', 'refunded']
        
        if new_status not in valid_statuses:
            return jsonify({'success': False, 'message': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}), 400
        
        # Get current order
        order_response = db.client.table('orders').select('status').eq('id', order_id).execute()
        if not order_response.data:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        current_status = order_response.data[0]['status']
        
        # Update order status
        now = datetime.now().isoformat()
        update_data = {
            'status': new_status,
            'updated_at': now
        }
        
        # Set specific timestamps based on status
        if new_status == 'confirmed':
            update_data['payment_confirmed_at'] = now
        elif new_status == 'preparing':
            update_data['received_at'] = now
        elif new_status == 'ready':
            update_data['ready_at'] = now
        elif new_status == 'assigned':
            update_data['assigned_at'] = now
        elif new_status == 'out_for_delivery':
            update_data['out_for_delivery_at'] = now
        elif new_status == 'delivered':
            update_data['delivered_at'] = now
        elif new_status == 'cancelled':
            update_data['cancelled_at'] = now
        elif new_status == 'refunded':
            update_data['refunded_at'] = now
        
        # Update order
        db.client.table('orders').update(update_data).eq('id', order_id).execute()
        
        # Create status log
        status_log_data = {
            'order_id': order_id,
            'status': new_status,
            'changed_by': user.id,
            'note': note,
            'metadata': json.dumps({'previous_status': current_status, 'source': 'api_update'}),
            'created_at': now
        }
        db.client.table('order_status_logs').insert(status_log_data).execute()
        
        return jsonify({
            'success': True,
            'message': f'Order status updated from {current_status} to {new_status}',
            'order_id': order_id,
            'status': new_status
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@order_bp.route('/<order_id>/review', methods=['POST'])
def add_order_review(order_id):
    """Add a review for an order"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        data = request.get_json()
        rating = data.get('rating')
        comment = data.get('comment', '')
        
        if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
            return jsonify({'success': False, 'message': 'Rating must be between 1 and 5'}), 400
        
        # Check if order exists and belongs to user
        order_response = db.client.table('orders').select('status, user_id').eq('id', order_id).execute()
        if not order_response.data:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order = order_response.data[0]
        if order['user_id'] != user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Check if order is delivered
        if order['status'] != 'delivered':
            return jsonify({'success': False, 'message': 'Can only review delivered orders'}), 400
        
        # Check if review already exists
        existing_review = db.client.table('order_reviews').select('id').eq('order_id', order_id).execute()
        if existing_review.data:
            return jsonify({'success': False, 'message': 'Review already exists for this order'}), 400
        
        # Create review
        now = datetime.now().isoformat()
        review_data = {
            'order_id': order_id,
            'user_id': user.id,
            'rating': rating,
            'comment': comment,
            'hp_rewarded': rating * 10,  # Example: 10 HP per rating point
            'is_flagged': False,
            'created_at': now,
            'updated_at': now
        }
        
        review_response = db.client.table('order_reviews').insert(review_data).execute()
        
        # Add HP to user's balance
        hp_rewarded = rating * 10
        profile_response = db.client.table('profiles').select('hp_balance').eq('id', user.id).execute()
        if profile_response.data:
            current_hp = profile_response.data[0]['hp_balance']
            new_hp = current_hp + hp_rewarded
            db.client.table('profiles').update({
                'hp_balance': new_hp,
                'updated_at': now
            }).eq('id', user.id).execute()
        
        return jsonify({
            'success': True,
            'message': 'Review added successfully',
            'review_id': review_response.data[0]['id'],
            'hp_rewarded': hp_rewarded
        }), 201
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@order_bp.route('/<order_id>/review', methods=['GET'])
def get_order_review(order_id):
    """Get review for an order"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        review_response = db.client.table('order_reviews')\
            .select('*')\
            .eq('order_id', order_id)\
            .execute()
        
        if not review_response.data:
            return jsonify({'success': False, 'message': 'No review found for this order'}), 404
        
        return jsonify({
            'success': True,
            'review': review_response.data[0]
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@order_bp.route('/stats', methods=['GET'])
def get_order_stats():
    """Get order statistics for the user"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Get all orders
        orders_response = db.client.table('orders')\
            .select('status, total_amount, hp_earned')\
            .eq('user_id', user.id)\
            .execute()
        
        orders = orders_response.data
        
        stats = {
            'total_orders': len(orders),
            'total_spent': sum(float(order.get('total_amount', 0)) for order in orders),
            'total_hp_earned': sum(order.get('hp_earned', 0) for order in orders),
            'completed_orders': len([o for o in orders if o['status'] == 'delivered']),
            'pending_orders': len([o for o in orders if o['status'] in ['pending', 'confirmed', 'preparing', 'ready', 'assigned', 'out_for_delivery']]),
            'cancelled_orders': len([o for o in orders if o['status'] == 'cancelled'])
        }
        
        return jsonify({
            'success': True,
            'stats': stats
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@order_bp.route('/cancel/<order_id>', methods=['POST'])
def cancel_order(order_id):
    """Cancel an order if it's not yet prepared"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return jsonify({'success': False, 'message': 'No authorization token'}), 401
        
        token = auth_header.split(' ')[1]
        user = verify_token(token)
        
        if not user:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        
        # Check order status
        order_response = db.client.table('orders')\
            .select('status, user_id')\
            .eq('id', order_id)\
            .execute()
        
        if not order_response.data:
            return jsonify({'success': False, 'message': 'Order not found'}), 404
        
        order = order_response.data[0]
        
        if order['user_id'] != user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Check if order can be cancelled
        cancellable_statuses = ['pending', 'confirmed']
        if order['status'] not in cancellable_statuses:
            return jsonify({'success': False, 'message': f'Order cannot be cancelled in {order["status"]} status'}), 400
        
        # Cancel order
        now = datetime.now().isoformat()
        db.client.table('orders').update({
            'status': 'cancelled',
            'cancelled_at': now,
            'updated_at': now
        }).eq('id', order_id).execute()
        
        # Create status log
        status_log_data = {
            'order_id': order_id,
            'status': 'cancelled',
            'changed_by': user.id,
            'note': 'Order cancelled by user',
            'metadata': json.dumps({'source': 'api_cancel'}),
            'created_at': now
        }
        db.client.table('order_status_logs').insert(status_log_data).execute()
        
        return jsonify({
            'success': True,
            'message': 'Order cancelled successfully',
            'order_id': order_id
        }), 200
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500