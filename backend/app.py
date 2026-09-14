from flask import Flask, jsonify
from flask_cors import CORS
from config import SECRET_KEY
from database import init_db
from extensions import limiter

# Importar blueprints
from routes.public import public_bp
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.panel_cliente import panel_bp

app = Flask(__name__)
app.secret_key = SECRET_KEY
CORS(app, supports_credentials=True)

# Configurar rate limiting
limiter.init_app(app)

# Inicializar BD al arrancar
init_db()

# Registrar blueprints
app.register_blueprint(public_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(panel_bp)

# Manejador de error para cuando se pasa el límite de peticiones
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'Demasiadas peticiones. Espera un momento e intenta de nuevo.'}), 429

# Manejador GLOBAL de errores no capturados
@app.errorhandler(Exception)
def handle_exception(e):
    from werkzeug.exceptions import HTTPException
    # Si es un error HTTP normal (404, 405, etc.), dejar que Flask lo maneje
    if isinstance(e, HTTPException):
        return e
    # Error inesperado: loggear y devolver JSON genérico
    import traceback
    print(f"[ERROR GLOBAL] {type(e).__name__}: {e}")
    traceback.print_exc()
    return jsonify({'error': 'Error interno del servidor'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)