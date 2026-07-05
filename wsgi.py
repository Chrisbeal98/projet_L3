from app import create_app, db, bcrypt
from app.models import User, ZoneRisque
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    db.create_all()

    admin = User.query.filter_by(email='kouadiochrisherve@gmail.com').first()
    if not admin:
        admin = User(
            nom='Kouadio',
            prenom='Chris',
            email='kouadiochrisherve@gmail.com',
            password_hash=bcrypt.generate_password_hash('kouadio98'),
            role='admin',
            statut='actif',
            date_creation=datetime.now(timezone.utc)
        )
        db.session.add(admin)
    else:
        admin.password_hash = bcrypt.generate_password_hash('kouadio98')
        admin.role = 'admin'
    db.session.commit()

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

@app.route('/dev/init-zones')
def init_zones():
    if ZoneRisque.query.first():
        return "Zones déjà existantes"
    zones = [
        ZoneRisque(nom='Yopougon', ville='Abidjan', latitude=5.3325, longitude=-4.0730, rayon_m=800, niveau_risque='critique', nombre_incidents=42),
        ZoneRisque(nom='Abobo', ville='Abidjan', latitude=5.4230, longitude=-4.0300, rayon_m=700, niveau_risque='critique', nombre_incidents=38),
        ZoneRisque(nom='Koumassi', ville='Abidjan', latitude=5.2900, longitude=-3.9600, rayon_m=600, niveau_risque='élevé', nombre_incidents=25),
        ZoneRisque(nom='Marcory', ville='Abidjan', latitude=5.3100, longitude=-3.9900, rayon_m=500, niveau_risque='élevé', nombre_incidents=20),
        ZoneRisque(nom='Treichville', ville='Abidjan', latitude=5.3000, longitude=-3.9700, rayon_m=500, niveau_risque='élevé', nombre_incidents=18),
        ZoneRisque(nom='Adjamé', ville='Abidjan', latitude=5.3500, longitude=-3.9900, rayon_m=400, niveau_risque='moyen', nombre_incidents=15),
        ZoneRisque(nom='Cocody', ville='Abidjan', latitude=5.3600, longitude=-3.9800, rayon_m=600, niveau_risque='moyen', nombre_incidents=12),
        ZoneRisque(nom='Plateau', ville='Abidjan', latitude=5.3200, longitude=-4.0200, rayon_m=400, niveau_risque='moyen', nombre_incidents=10),
        ZoneRisque(nom='Port-Bouët', ville='Abidjan', latitude=5.2500, longitude=-3.9000, rayon_m=600, niveau_risque='élevé', nombre_incidents=22),
        ZoneRisque(nom='Bingerville', ville='Abidjan', latitude=5.3500, longitude=-3.8800, rayon_m=500, niveau_risque='faible', nombre_incidents=5),
        ZoneRisque(nom='Anyama', ville='Abidjan', latitude=5.4800, longitude=-4.0500, rayon_m=600, niveau_risque='moyen', nombre_incidents=8),
        ZoneRisque(nom='Attécoubé', ville='Abidjan', latitude=5.3300, longitude=-4.0400, rayon_m=400, niveau_risque='moyen', nombre_incidents=11),
        ZoneRisque(nom='Bouaké Centre', ville='Bouaké', latitude=7.6900, longitude=-5.0300, rayon_m=600, niveau_risque='élevé', nombre_incidents=16),
        ZoneRisque(nom='Bouaké Nord', ville='Bouaké', latitude=7.7300, longitude=-5.0300, rayon_m=500, niveau_risque='moyen', nombre_incidents=9),
        ZoneRisque(nom='San-Pédro', ville='San-Pédro', latitude=4.7500, longitude=-6.6400, rayon_m=500, niveau_risque='moyen', nombre_incidents=7),
        ZoneRisque(nom='Gagnoa', ville='Gagnoa', latitude=6.1300, longitude=-5.9500, rayon_m=400, niveau_risque='faible', nombre_incidents=4),
        ZoneRisque(nom='Daloa', ville='Daloa', latitude=6.8800, longitude=-6.4500, rayon_m=400, niveau_risque='faible', nombre_incidents=3),
        ZoneRisque(nom='Man', ville='Man', latitude=7.4100, longitude=-7.5500, rayon_m=400, niveau_risque='faible', nombre_incidents=2),
        ZoneRisque(nom='Korhogo', ville='Korhogo', latitude=9.4600, longitude=-5.6300, rayon_m=400, niveau_risque='faible', nombre_incidents=3),
    ]
    for z in zones:
        db.session.add(z)
    db.session.commit()
    return f"OK - {len(zones)} zones ajoutées"
