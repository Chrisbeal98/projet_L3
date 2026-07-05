from app import create_app, db, bcrypt
from app.models import User, Appareil, Alerte, Notification, Localisation, ZoneRisque, ActiviteUtilisateur
from datetime import datetime, timezone, timedelta
import random

app = create_app()

with app.app_context():
    db.create_all()

    # ─── Admin ───
    admin = User.query.filter_by(email='kouadiochrisherve@gmail.com').first()
    if not admin:
        admin = User(
            nom='Kouadio', prenom='Chris',
            email='kouadiochrisherve@gmail.com',
            password_hash=bcrypt.generate_password_hash('kouadio98'),
            role='admin', statut='actif',
            date_creation=datetime.now(timezone.utc)
        )
        db.session.add(admin)
    else:
        admin.password_hash = bcrypt.generate_password_hash('kouadio98')
        admin.role = 'admin'
    db.session.commit()

    # ─── Données de démonstration ───
    if User.query.count() <= 1:
        users_data = [
            ('Touré', 'Ibrahim', 'ibrahim.toure@email.ci', '+225 07 98 76 54', 'utilisateur', 45),
            ('Diallo', 'Fatou', 'fatou.diallo@email.ci', '+225 01 55 66 77', 'utilisateur', 30),
            ('Yao', 'Jean-Marc', 'jeanmarc.yao@email.ci', '+225 07 11 22 33', 'utilisateur', 15),
            ('Bamba', 'Moussa', 'moussa.bamba@email.ci', '+225 05 44 55 66', 'suspendu', 5),
        ]
        for nom, prenom, email, tel, role, jours in users_data:
            u = User(nom=nom, prenom=prenom, email=email, telephone=tel,
                     password_hash=bcrypt.generate_password_hash('motdepasse'),
                     role=role, statut='actif' if role != 'suspendu' else 'suspendu',
                     date_creation=datetime.now(timezone.utc) - timedelta(days=jours))
            db.session.add(u)
        db.session.commit()

        appareils_data = [
            (admin.id, '351234567890123', 'Galaxy S24 Ultra', 'Samsung', 'Android', '14', '+225 07 00 00 01', 'Orange CI', 'actif'),
            (2, '351234567891012', 'Redmi Note 13', 'Xiaomi', 'Android', '14', '+225 07 98 76 55', 'Moov Africa', 'actif'),
            (2, '351234567891345', 'Tecno Spark 20', 'Tecno', 'Android', '13', '+225 07 98 76 56', 'Orange CI', 'verrouillé'),
            (3, '351234567891678', 'iPhone 14', 'Apple', 'iOS', '16.5', '+225 01 55 66 78', 'MTN CI', 'actif'),
            (4, '351234567891901', 'Galaxy S23', 'Samsung', 'Android', '14', '+225 07 11 22 34', 'Orange CI', 'actif'),
            (4, '351234567892234', 'Infinix Hot 40', 'Infinix', 'Android', '13', '+225 07 11 22 35', 'Moov Africa', 'volé'),
            (5, '351234567892567', 'Oppo Reno 10', 'Oppo', 'Android', '13', '+225 05 44 55 67', 'MTN CI', 'actif'),
        ]
        for uid, imei, modele, marque, os, ver, tel, op, statut in appareils_data:
            db.session.add(Appareil(user_id=uid, imei=imei, modele=modele, marque=marque,
                           systeme_os=os, version_os=ver, numero_telephone=tel,
                           operateur=op, statut=statut,
                           date_enregistrement=datetime.now(timezone.utc) - timedelta(days=random.randint(5, 80))))
        db.session.commit()

        appareils = Appareil.query.all()
        alertes_data = [
            (2, appareils[2].id, 'vol', 'Vol à l\'arraché dans le bus à Adjamé.', 'en_cours', 'critique', 7),
            (4, appareils[5].id, 'vol', 'Disparition suspecte au plateau.', 'en_cours', 'haute', 2),
            (2, appareils[1].id, 'changement_sim', 'Carte SIM changée sans autorisation.', 'en_cours', 'haute', 1),
            (3, appareils[3].id, 'anomalie', 'Activité suspecte sur le réseau.', 'traité', 'moyenne', 15),
            (4, appareils[4].id, 'perte', 'Téléphone perdu à Bouaké.', 'traité', 'moyenne', 25),
        ]
        for uid, aid, typ, desc, statut, priorite, jours in alertes_data:
            db.session.add(Alerte(user_id=uid, appareil_id=aid, type_alerte=typ, description=desc,
                         statut=statut, priorite=priorite,
                         date_creation=datetime.now(timezone.utc) - timedelta(days=jours),
                         date_resolution=datetime.now(timezone.utc) - timedelta(days=jours - 2) if statut == 'traité' else None))
        db.session.commit()

        alertes = Alerte.query.all()
        for alerte in alertes:
            for ntype in ['push', 'email', 'sms']:
                u = db.session.get(User, alerte.user_id)
                db.session.add(Notification(alerte_id=alerte.id, type_notification=ntype,
                    contenu=f'ALERTE {alerte.type_alerte.upper()} — Appareil ID:{alerte.appareil_id}',
                    destinataire=u.email if ntype == 'email' else u.telephone, statut='envoyé',
                    date_envoi=alerte.date_creation))

        locs_data = [
            (appareils[2].id, 5.3600, -3.9900, 'Adjamé, Abidjan', 10.0, 'gps', 7),
            (appareils[2].id, 5.3550, -3.9850, 'Attécoubé, Abidjan', 20.0, 'wifi', 6),
            (appareils[5].id, 5.3200, -4.0050, 'Le Plateau, Abidjan', 8.0, 'gps', 2),
            (appareils[5].id, 5.3400, -3.9700, 'Yopougon, Abidjan', 45.0, 'réseau', 1.5),
            (appareils[0].id, 5.3590, -3.9750, 'Riviera, Cocody', 3.0, 'gps', 0.1),
            (appareils[1].id, 5.3100, -4.0300, 'Vridi, Port-Bouët', 12.0, 'gps', 1),
        ]
        for aid, lat, lon, adr, prec, src, jours in locs_data:
            db.session.add(Localisation(appareil_id=aid, latitude=lat, longitude=lon,
                               adresse=adr, precision_m=prec, source=src,
                               date_capture=datetime.now(timezone.utc) - timedelta(days=jours)))
        db.session.commit()

        zones_data = [
            ('Marché de Treichville', 'Abidjan', 5.3364, -4.0266, 300, 'critique', 45),
            ('Gare routière Adjamé', 'Abidjan', 5.3600, -3.9900, 400, 'élevé', 32),
            ('Plateau - Centre-ville', 'Abidjan', 5.3200, -4.0050, 250, 'élevé', 28),
            ('Marché de Yopougon', 'Abidjan', 5.3400, -3.9700, 350, 'moyen', 18),
            ('Commune de Abobo', 'Abidjan', 5.4200, -4.0200, 500, 'élevé', 37),
            ('Port-Bouët plage', 'Abidjan', 5.2570, -3.9260, 200, 'moyen', 12),
            ('Gare de Bouaké', 'Bouaké', 7.6900, -5.0300, 300, 'moyen', 15),
        ]
        for nom, ville, lat, lon, rayon, niveau, incidents in zones_data:
            db.session.add(ZoneRisque(nom=nom, ville=ville, latitude=lat, longitude=lon,
                             rayon_m=rayon, niveau_risque=niveau, nombre_incidents=incidents,
                             date_mise_a_jour=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))))
        db.session.commit()

        activites_data = [
            (admin.id, 'connexion', 'Connexion Admin', 0.1),
            (2, 'inscription', 'Inscription Ibrahim Touré', 45),
            (2, 'signalement_alerte', 'Vol — Tecno Spark 20', 7),
            (3, 'inscription', 'Inscription Fatou Diallo', 30),
            (4, 'inscription', 'Inscription Jean-Marc Yao', 15),
            (4, 'signalement_alerte', 'Vol — Infinix Hot 40', 2),
        ]
        for uid, action, details, jours in activites_data:
            db.session.add(ActiviteUtilisateur(user_id=uid, action=action, details=details,
                       adresse_ip=f'192.168.1.{random.randint(2, 254)}',
                       navigateur='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
                       date=datetime.now(timezone.utc) - timedelta(days=jours, hours=random.randint(0, 23))))
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
