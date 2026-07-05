from app import create_app, db
from app.models import User

app = create_app()

with app.app_context():
    db.create_all()

@app.route('/dev/make-admin/<email>')
def make_admin(email):
    user = User.query.filter_by(email=email).first()
    if user:
        user.role = 'admin'
        db.session.commit()
        return f"OK - {email} est maintenant admin"
    return "Utilisateur pas trouvé"

@app.route('/dev/promote-me')
def promote_me():
    from flask_login import current_user
    if current_user.is_authenticated:
        user = db.session.get(User, int(current_user.id))
        if user:
            user.role = 'admin'
            db.session.commit()
            return f"OK - {user.email} est maintenant admin"
        return "Utilisateur pas trouvé"
    return "Non connecté"
