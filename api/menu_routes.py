from flask import Blueprint, request, jsonify
from utils.db import db

menu_bp = Blueprint('menu', __name__)

@menu_bp.route('/categories', methods=['GET'])
def get_categories():
    """Get all active menu categories"""
    try:
        response = db.client.table('menu_category')\
            .select('*')\
            .eq('is_active', True)\
            .order('sort_order')\
            .execute()
        
        return jsonify({
            'success': True,
            'categories': response.data
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/categories/<category_id>', methods=['GET'])
def get_category_by_id(category_id):
    """Get a specific category by ID"""
    try:
        response = db.client.table('menu_category')\
            .select('*')\
            .eq('id', category_id)\
            .eq('is_active', True)\
            .execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'category': response.data[0]
            }), 200
        else:
            return jsonify({'success': False, 'message': 'Category not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/categories/slug/<slug>', methods=['GET'])
def get_category_by_slug(slug):
    """Get a specific category by slug"""
    try:
        response = db.client.table('menu_category')\
            .select('*')\
            .eq('slug', slug)\
            .eq('is_active', True)\
            .execute()
        
        if response.data:
            return jsonify({
                'success': True,
                'category': response.data[0]
            }), 200
        else:
            return jsonify({'success': False, 'message': 'Category not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/items', methods=['GET'])
def get_food_items():
    """Get all available food items with optional filtering"""
    try:
        category_id = request.args.get('category_id')
        is_featured = request.args.get('is_featured')
        search = request.args.get('search')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Start query
        query = db.client.table('menu_items').select('*').eq('is_available', True)
        
        # Apply filters
        if category_id:
            query = query.eq('category_id', category_id)
        
        if is_featured and is_featured.lower() == 'true':
            query = query.eq('is_featured', True)
        
        if search:
            query = query.ilike('name', f'%{search}%')
        
        # Apply pagination
        query = query.range(offset, offset + limit - 1)
        
        response = query.execute()
        
        # Get total count for pagination
        count_query = db.client.table('menu_items').select('*', count='exact').eq('is_available', True)
        if category_id:
            count_query = count_query.eq('category_id', category_id)
        count_response = count_query.execute()
        total_count = count_response.count
        
        return jsonify({
            'success': True,
            'food_items': response.data,
            'pagination': {
                'total': total_count,
                'limit': limit,
                'offset': offset,
                'has_more': offset + limit < total_count
            }
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/items/<item_id>', methods=['GET'])
def get_food_item(item_id):
    """Get single food item details with its category"""
    try:
        # Get the menu item
        item_response = db.client.table('menu_items')\
            .select('*')\
            .eq('id', item_id)\
            .execute()
        
        if not item_response.data:
            return jsonify({'success': False, 'message': 'Food item not found'}), 404
        
        food_item = item_response.data[0]
        
        # Get the category information
        category_response = db.client.table('menu_category')\
            .select('id, name, slug, description')\
            .eq('id', food_item['category_id'])\
            .execute()
        
        if category_response.data:
            food_item['category'] = category_response.data[0]
        
        return jsonify({
            'success': True,
            'food_item': food_item
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/items/slug/<slug>', methods=['GET'])
def get_food_item_by_slug(slug):
    """Get single food item by slug with its category"""
    try:
        # Get the menu item by slug
        item_response = db.client.table('menu_items')\
            .select('*')\
            .eq('slug', slug)\
            .eq('is_available', True)\
            .execute()
        
        if not item_response.data:
            return jsonify({'success': False, 'message': 'Food item not found'}), 404
        
        food_item = item_response.data[0]
        
        # Get the category information
        category_response = db.client.table('menu_category')\
            .select('id, name, slug, description')\
            .eq('id', food_item['category_id'])\
            .execute()
        
        if category_response.data:
            food_item['category'] = category_response.data[0]
        
        return jsonify({
            'success': True,
            'food_item': food_item
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/category-items/<category_id>', methods=['GET'])
def get_items_by_category(category_id):
    """Get all items in a specific category"""
    try:
        # First verify category exists
        category_response = db.client.table('menu_category')\
            .select('id, name, slug, description')\
            .eq('id', category_id)\
            .eq('is_active', True)\
            .execute()
        
        if not category_response.data:
            return jsonify({'success': False, 'message': 'Category not found'}), 404
        
        # Get items in this category
        items_response = db.client.table('menu_items')\
            .select('*')\
            .eq('category_id', category_id)\
            .eq('is_available', True)\
            .order('name')\
            .execute()
        
        return jsonify({
            'success': True,
            'category': category_response.data[0],
            'items': items_response.data,
            'count': len(items_response.data)
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/featured', methods=['GET'])
def get_featured_items():
    """Get all featured food items"""
    try:
        response = db.client.table('menu_items')\
            .select('*')\
            .eq('is_available', True)\
            .eq('is_featured', True)\
            .execute()
        
        # Enrich with category information
        items_with_categories = []
        for item in response.data:
            category_response = db.client.table('menu_category')\
                .select('id, name')\
                .eq('id', item['category_id'])\
                .execute()
            
            if category_response.data:
                item['category_name'] = category_response.data[0]['name']
            items_with_categories.append(item)
        
        return jsonify({
            'success': True,
            'featured_items': items_with_categories
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/search', methods=['GET'])
def search_menu_items():
    """Search menu items by name, description, or tags"""
    try:
        query = request.args.get('q', '')
        if not query:
            return jsonify({'success': False, 'message': 'Search query required'}), 400
        
        # Search in name, description, and tags
        response = db.client.table('menu_items')\
            .select('*')\
            .eq('is_available', True)\
            .ilike('name', f'%{query}%')\
            .execute()
        
        # Also search in tags (PostgreSQL JSONB search)
        # Note: This might need adjustment based on your Supabase version
        tag_response = db.client.table('menu_items')\
            .select('*')\
            .eq('is_available', True)\
            .contains('tags', [query])\
            .execute()
        
        # Combine and deduplicate results
        all_items = response.data + tag_response.data
        unique_items = {item['id']: item for item in all_items}.values()
        
        return jsonify({
            'success': True,
            'query': query,
            'results': list(unique_items),
            'count': len(unique_items)
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/items/<item_id>/options', methods=['GET'])
def get_item_options(item_id):
    """Get customization options for a menu item"""
    try:
        response = db.client.table('menu_items')\
            .select('options, name')\
            .eq('id', item_id)\
            .execute()
        
        if not response.data:
            return jsonify({'success': False, 'message': 'Item not found'}), 404
        
        import json
        options = response.data[0].get('options', '{}')
        
        # Parse options if it's a string
        if isinstance(options, str):
            options = json.loads(options)
        
        return jsonify({
            'success': True,
            'item_name': response.data[0]['name'],
            'options': options
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/popular', methods=['GET'])
def get_popular_items():
    """Get popular items based on tags or order frequency"""
    try:
        # Get items with 'popular' tag
        response = db.client.table('menu_items')\
            .select('*')\
            .eq('is_available', True)\
            .contains('tags', ['popular'])\
            .limit(10)\
            .execute()
        
        return jsonify({
            'success': True,
            'popular_items': response.data
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@menu_bp.route('/categories-with-items', methods=['GET'])
def get_categories_with_items():
    """Get all categories with their items (for menu display)"""
    try:
        # Get all active categories
        categories_response = db.client.table('menu_category')\
            .select('*')\
            .eq('is_active', True)\
            .order('sort_order')\
            .execute()
        
        result = []
        for category in categories_response.data:
            # Get items for this category
            items_response = db.client.table('menu_items')\
                .select('*')\
                .eq('category_id', category['id'])\
                .eq('is_available', True)\
                .order('name')\
                .execute()
            
            result.append({
                'category': category,
                'items': items_response.data,
                'item_count': len(items_response.data)
            })
        
        return jsonify({
            'success': True,
            'menu': result
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500