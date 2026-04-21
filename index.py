# Modules
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os


# Blueprints
from api.auth_routes import auth_bp
from api.menu_routes import menu_bp
from api.order_routes import order_bp
from api.user_routes import user_bp


load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

CORS(app)

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(menu_bp, url_prefix='/api/menu')
app.register_blueprint(order_bp, url_prefix='/api/orders')
app.register_blueprint(user_bp, url_prefix='/api/user')

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'HolyGrills API is running'}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)