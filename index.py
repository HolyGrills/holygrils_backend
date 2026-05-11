# Modules
from flasgger import Swagger
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os


# Blueprints
from api.auth_routes import auth_bp
from api.menu_routes import menu_bp
from api.order_routes import order_bp
from api.user_routes import user_bp
from api.event_routes import event_bp
from routes.event_tickets_routes import ticket_bp
from routes.event_checkin_routes import checkin_bp
from routes.delivery_zones_routes import delivery_zones_bp
from routes.delivery_batches_routes import delivery_batches_bp


load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

CORS(app)
swagger = Swagger(app, template={
    "info": {
        "title": "Your App API",
        "description": "API documentation",
        "version": "1.0.0"
    },
    "securityDefinitions": {
        "BearerAuth": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Enter: Bearer <token>"
        }
    }
})

# Register Blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(menu_bp, url_prefix='/api/menu')
app.register_blueprint(order_bp, url_prefix='/api/orders')
app.register_blueprint(user_bp, url_prefix='/api/user')
app.register_blueprint(event_bp,url_prefix='/api/events')
app.register_blueprint(ticket_bp, url_prefix='/api/tickets')
app.register_blueprint(checkin_bp, url_prefix='/api/checkins')
app.register_blueprint(delivery_zones_bp, url_prefix='/api/delivery')
app.register_blueprint(delivery_batches_bp, url_prefix='/api/delivery/batches')

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy', 'message': 'HolyGrills API is running'}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)