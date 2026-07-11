import os

from app import create_app, db, bcrypt
from app.models import User, Appareil, Alerte, Notification, Localisation, ZoneRisque, ActiviteUtilisateur
from datetime import datetime, timezone, timedelta
import random

app = create_app()

with app.app_context():
    db.create_all()

    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)

    # Migration robuste : vérifier TOUTES les colonnes du modèle Appareil
    try:
        columns = [c['name'] for c in inspector.get_columns('appareils')]
        all_migrations = {
            'device_uuid': 'ALTER TABLE appareils ADD COLUMN device_uuid VARCHAR(64)',
            'contacts_urgents': 'ALTER TABLE appareils ADD COLUMN contacts_urgents TEXT',
            'code_verrouillage': 'ALTER TABLE appareils ADD COLUMN code_verrouillage VARCHAR(20)',
            'code_ussd': 'ALTER TABLE appareils ADD COLUMN code_ussd VARCHAR(20)',
        }
        for col, sql in all_migrations.items():
            if col not in columns:
                db.session.execute(text(sql))
        if 'device_uuid' not in columns:
            db.session.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS ix_appareils_device_uuid ON appareils(device_uuid)'))
        db.session.commit()
    except Exception as e:
        print(f'[WARN] Migration appareils: {e}')
        db.session.rollback()

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

    # ─── Seed démo : utilisateurs + appareils + alertes (si vide) ───
    if not Appareil.query.first():
        print('[SEED] Aucun appareil trouvé — seed des données de démonstration...')

        demo_users = [
            User(nom='Koné', prenom='Aminata', email='aminata.kone@email.ci',
                 telephone='+225 05 12 34 56', password_hash=bcrypt.generate_password_hash('motdepasse'),
                 role='utilisateur', statut='actif', date_creation=datetime.now(timezone.utc) - timedelta(days=60)),
            User(nom='Touré', prenom='Ibrahim', email='ibrahim.toure@email.ci',
                 telephone='+225 07 98 76 54', password_hash=bcrypt.generate_password_hash('motdepasse'),
                 role='utilisateur', statut='actif', date_creation=datetime.now(timezone.utc) - timedelta(days=45)),
            User(nom='Diallo', prenom='Fatou', email='fatou.diallo@email.ci',
                 telephone='+225 01 55 66 77', password_hash=bcrypt.generate_password_hash('motdepasse'),
                 role='utilisateur', statut='actif', date_creation=datetime.now(timezone.utc) - timedelta(days=30)),
            User(nom='Yao', prenom='Jean-Marc', email='jeanmarc.yao@email.ci',
                 telephone='+225 07 11 22 33', password_hash=bcrypt.generate_password_hash('motdepasse'),
                 role='utilisateur', statut='actif', date_creation=datetime.now(timezone.utc) - timedelta(days=15)),
            User(nom='Bamba', prenom='Moussa', email='moussa.bamba@email.ci',
                 telephone='+225 05 44 55 66', password_hash=bcrypt.generate_password_hash('motdepasse'),
                 role='utilisateur', statut='suspendu', date_creation=datetime.now(timezone.utc) - timedelta(days=5)),
        ]
        for u in demo_users:
            existing = User.query.filter_by(email=u.email).first()
            if not existing:
                db.session.add(u)
        db.session.commit()

        # Recharger les users
        u_admin = User.query.filter_by(email='kouadiochrisherve@gmail.com').first()
        u1 = User.query.filter_by(email='aminata.kone@email.ci').first()
        u2 = User.query.filter_by(email='ibrahim.toure@email.ci').first()
        u3 = User.query.filter_by(email='fatou.diallo@email.ci').first()
        u4 = User.query.filter_by(email='jeanmarc.yao@email.ci').first()
        u5 = User.query.filter_by(email='moussa.bamba@email.ci').first()

        devices_data = [
            (u_admin.id, '351234567890123', 'Galaxy S24 Ultra', 'Samsung', 'Android', '14', '+225 07 00 00 01', 'Orange CI', 'actif'),
            (u1.id, '351234567890456', 'iPhone 15 Pro', 'Apple', 'iOS', '17.2', '+225 05 12 34 57', 'MTN CI', 'actif'),
            (u1.id, '351234567890789', 'Galaxy A54', 'Samsung', 'Android', '13', '+225 05 12 34 58', 'Orange CI', 'volé'),
            (u2.id, '351234567891012', 'Redmi Note 13', 'Xiaomi', 'Android', '14', '+225 07 98 76 55', 'Moov Africa', 'actif'),
            (u2.id, '351234567891345', 'Tecno Spark 20', 'Tecno', 'Android', '13', '+225 07 98 76 56', 'Orange CI', 'verrouillé'),
            (u3.id, '351234567891678', 'iPhone 14', 'Apple', 'iOS', '16.5', '+225 01 55 66 78', 'MTN CI', 'actif'),
            (u4.id, '351234567891901', 'Galaxy S23', 'Samsung', 'Android', '14', '+225 07 11 22 34', 'Orange CI', 'actif'),
            (u4.id, '351234567892234', 'Infinix Hot 40', 'Infinix', 'Android', '13', '+225 07 11 22 35', 'Moov Africa', 'volé'),
            (u5.id, '351234567892567', 'Oppo Reno 10', 'Oppo', 'Android', '13', '+225 05 44 55 67', 'MTN CI', 'actif'),
        ]

        appareils = []
        for uid, imei, modele, marque, os, ver, tel, op, statut in devices_data:
            a = Appareil(
                user_id=uid, imei=imei, modele=modele, marque=marque,
                systeme_os=os, version_os=ver, numero_telephone=tel,
                operateur=op, statut=statut,
                date_enregistrement=datetime.now(timezone.utc) - timedelta(days=random.randint(5, 80))
            )
            db.session.add(a)
            appareils.append(a)
        db.session.commit()

        # Recharger pour avoir les IDs
        appareils = Appareil.query.all()

        # Alertes
        if len(appareils) >= 8:
            alertes_data = [
                (u1.id, appareils[2].id, 'vol', 'Téléphone volé au marché de Treichville.', 'en_cours', 'critique'),
                (u2.id, appareils[4].id, 'vol', "Vol à l'arraché dans le bus à Adjamé.", 'en_cours', 'critique'),
                (u4.id, appareils[7].id, 'vol', 'Disparition suspecte au Plateau.', 'en_cours', 'haute'),
                (u1.id, appareils[1].id, 'perte', 'iPhone oublié dans un taxi.', 'traité', 'haute'),
                (u3.id, appareils[5].id, 'anomalie', "Activité suspecte sur le réseau.", 'traité', 'moyenne'),
            ]
            for uid, aid, type_a, desc, statut, priorite in alertes_data:
                db.session.add(Alerte(
                    user_id=uid, appareil_id=aid, type_alerte=type_a,
                    description=desc, statut=statut, priorite=priorite,
                    date_creation=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 15))
                ))
            db.session.commit()

        print(f'[SEED] {len(devices_data)} appareils, {len(alertes_data)} alertes créés')

    # ─── Zones à risque (seed automatique) ───
    if not ZoneRisque.query.first():
        zones_data = [
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
        ]
        db.session.add_all(zones_data)
        db.session.commit()

    print('[OK] Démarrage terminé.')
