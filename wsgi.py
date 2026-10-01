"""
Point d'entrée WSGI — utilisé par gunicorn sur Render.

    gunicorn wsgi:app

Ce fichier ne fait QUE créer l'application et amorcer la base. Le schéma est
appliqué par les migrations Alembic (`app/bootstrap.py` →
`flask_migrate.upgrade()`), plus les éventuelles révisions déjà appliquées par
`preDeployCommand` de `render.yaml`. Il n'y a plus aucun `CREATE TABLE` ni
`ALTER TABLE` dans le code de démarrage.
"""

from app import create_app
from app.bootstrap import preparer_base

app = create_app()

with app.app_context():
    preparer_base()
