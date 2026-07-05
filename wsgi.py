from app import create_app, db
from app.models import User

app = create_app()

@app.route('/dev/make-admin/<email>')
def make_admin(email):
    user = User.query.filter_by(email=email).first()
    if user:
        user.role = 'admin'
        db.session.commit()
        return f"OK - {email} est maintenant admin"
    return "Utilisateur pas trouvé"
