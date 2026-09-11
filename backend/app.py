from flask import Flask
from flask_cors import CORS
from config import SECRET_KEY
from database import init_db

# Importar blueprints
from routes.public import public_bp
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.panel_cliente import panel_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY
CORS(app, supports_credentials=True)

# Inicializar BD al arrancar
init_db()

# Registrar blueprints
app.register_blueprint(public_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(panel_bp)

if __name__ == '__main__':
    app.run(debug=True, port=5000)