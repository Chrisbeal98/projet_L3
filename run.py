"""
Système Anti-Vol Intelligent
=============================
Point d'entrée principal de l'application.

Développé dans le cadre du mémoire de Licence 3 Génie Informatique.
Thème : Système d'alerte et de verrouillage à distance des smartphones.
"""

from dotenv import load_dotenv

load_dotenv()

from app import create_app, db

app = create_app()

with app.app_context():
    db.create_all()
    # Migration : ajouter les colonnes manquantes
    from flask import current_app
    with current_app.app_context():
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('appareils')]
        if 'code_verrouillage' not in columns:
            db.session.execute(text('ALTER TABLE appareils ADD COLUMN code_verrouillage VARCHAR(20)'))
            db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_appareils_code_verrouillage ON appareils(code_verrouillage)'))
        if 'code_ussd' not in columns:
            db.session.execute(text('ALTER TABLE appareils ADD COLUMN code_ussd VARCHAR(20)'))
            db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_appareils_code_ussd ON appareils(code_ussd)'))
        db.session.commit()

if __name__ == '__main__':
    import os
    import socket
    port = 8000
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        import socket as _sock
        hostname = _sock.gethostname()
        ip_locale = _sock.gethostbyname(hostname)
        print('[OK] Systeme Anti-Vol Intelligent - Serveur demarre (HTTPS)')
        print(f'[>>] Acces local   : https://localhost:{port}')
        print(f'[>>] Acces reseau  : https://{ip_locale}:{port}')
    app.run(debug=False, host='0.0.0.0', port=port, ssl_context='adhoc')
