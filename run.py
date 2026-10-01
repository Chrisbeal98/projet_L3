"""
Système Anti-Vol Intelligent
=============================
Point d'entrée principal de l'application (développement).

Développé dans le cadre du mémoire de Licence 3 Génie Informatique.
Thème : Système d'alerte et de verrouillage à distance des smartphones.

    python run.py    ->  http://localhost:8000

La base est amenée à la dernière révision par les migrations Alembic
(`app/bootstrap.py`), et plus par des `ALTER TABLE` écrits ici.
"""

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.bootstrap import preparer_base

app = create_app()

with app.app_context():
    preparer_base()

if __name__ == '__main__':
    import os
    port = 8000
    if not os.environ.get('WERKZEUG_RUN_MAIN'):
        import socket as _sock
        hostname = _sock.gethostname()
        ip_locale = _sock.gethostbyname(hostname)
        print('[OK] Systeme Anti-Vol Intelligent - Serveur demarre (HTTP)')
        print(f'[>>] Acces local   : http://localhost:{port}')
        print(f'[>>] Acces reseau  : http://{ip_locale}:{port}')
    app.run(debug=False, host='0.0.0.0', port=port)
