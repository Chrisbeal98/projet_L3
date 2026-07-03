"""
Script de peuplement de la base de données avec des données de démonstration.
Crée un admin, des utilisateurs, des appareils, des alertes, etc.
"""

from app import create_app, db, bcrypt
from app.models import (
    User, Appareil, Alerte, Notification,
    Localisation, ZoneRisque, ActiviteUtilisateur
)
from datetime import datetime, timezone, timedelta
import random

app = create_app()

with app.app_context():
    print("Peuplement de la base de donnees...")

    # ═══════════════════════════════════════
    # 1. UTILISATEURS
    # ═══════════════════════════════════════
    print("\nCreation des utilisateurs...")

    admin = User(
        nom='Kouadio',
        prenom='Admin',
        email='admin@nox-antivol.ci',
        telephone='+225 07 00 00 00',
        password_hash=bcrypt.generate_password_hash('admin123'),
        role='admin',
        statut='actif',
        date_creation=datetime.now(timezone.utc) - timedelta(days=90)
    )

    user1 = User(
        nom='Koné',
        prenom='Aminata',
        email='aminata.kone@email.ci',
        telephone='+225 05 12 34 56',
        password_hash=bcrypt.generate_password_hash('motdepasse'),
        role='utilisateur',
        statut='actif',
        date_creation=datetime.now(timezone.utc) - timedelta(days=60)
    )

    user2 = User(
        nom='Touré',
        prenom='Ibrahim',
        email='ibrahim.toure@email.ci',
        telephone='+225 07 98 76 54',
        password_hash=bcrypt.generate_password_hash('motdepasse'),
        role='utilisateur',
        statut='actif',
        date_creation=datetime.now(timezone.utc) - timedelta(days=45)
    )

    user3 = User(
        nom='Diallo',
        prenom='Fatou',
        email='fatou.diallo@email.ci',
        telephone='+225 01 55 66 77',
        password_hash=bcrypt.generate_password_hash('motdepasse'),
        role='utilisateur',
        statut='actif',
        date_creation=datetime.now(timezone.utc) - timedelta(days=30)
    )

    user4 = User(
        nom='Yao',
        prenom='Jean-Marc',
        email='jeanmarc.yao@email.ci',
        telephone='+225 07 11 22 33',
        password_hash=bcrypt.generate_password_hash('motdepasse'),
        role='utilisateur',
        statut='actif',
        date_creation=datetime.now(timezone.utc) - timedelta(days=15)
    )

    user5 = User(
        nom='Bamba',
        prenom='Moussa',
        email='moussa.bamba@email.ci',
        telephone='+225 05 44 55 66',
        password_hash=bcrypt.generate_password_hash('motdepasse'),
        role='utilisateur',
        statut='suspendu',
        date_creation=datetime.now(timezone.utc) - timedelta(days=5)
    )

    try:
        db.session.add_all([admin, user1, user2, user3, user4, user5])
        db.session.commit()
        print("  [OK] 6 utilisateurs crees (1 admin + 5 utilisateurs)")
        print("     Admin : admin@nox-antivol.ci / admin123")
    except Exception:
        db.session.rollback()
        print("  [INFO] Utilisateurs partiellement existants, creation des manquants...")
        # Creer les utilisateurs manquants un par un
        for u in [admin, user1, user2, user3, user4, user5]:
            existing = User.query.filter_by(email=u.email).first()
            if not existing:
                db.session.add(u)
        db.session.commit()
        # Recharger tous
        admin = User.query.filter_by(email='admin@nox-antivol.ci').first()
        user1 = User.query.filter_by(email='aminata.kone@email.ci').first()
        user2 = User.query.filter_by(email='ibrahim.toure@email.ci').first()
        user3 = User.query.filter_by(email='fatou.diallo@email.ci').first()
        user4 = User.query.filter_by(email='jeanmarc.yao@email.ci').first()
        user5 = User.query.filter_by(email='moussa.bamba@email.ci').first()
        print("     Admin : admin@nox-antivol.ci / admin123")

    # ═══════════════════════════════════════
    # 2. APPAREILS
    # ═══════════════════════════════════════
    print("\n[APP] Creation des appareils...")

    appareils_data = [
        # Admin
        (admin.id, '351234567890123', 'Galaxy S24 Ultra', 'Samsung',
         'Android', '14', '+225 07 00 00 01', 'Orange CI', 'actif'),
        # Aminata
        (user1.id, '351234567890456', 'iPhone 15 Pro', 'Apple',
         'iOS', '17.2', '+225 05 12 34 57', 'MTN CI', 'actif'),
        (user1.id, '351234567890789', 'Galaxy A54', 'Samsung',
         'Android', '13', '+225 05 12 34 58', 'Orange CI', 'volé'),
        # Ibrahim
        (user2.id, '351234567891012', 'Redmi Note 13', 'Xiaomi',
         'Android', '14', '+225 07 98 76 55', 'Moov Africa', 'actif'),
        (user2.id, '351234567891345', 'Tecno Spark 20', 'Tecno',
         'Android', '13', '+225 07 98 76 56', 'Orange CI', 'verrouillé'),
        # Fatou
        (user3.id, '351234567891678', 'iPhone 14', 'Apple',
         'iOS', '16.5', '+225 01 55 66 78', 'MTN CI', 'actif'),
        # Jean-Marc
        (user4.id, '351234567891901', 'Galaxy S23', 'Samsung',
         'Android', '14', '+225 07 11 22 34', 'Orange CI', 'actif'),
        (user4.id, '351234567892234', 'Infinix Hot 40', 'Infinix',
         'Android', '13', '+225 07 11 22 35', 'Moov Africa', 'volé'),
        # Moussa
        (user5.id, '351234567892567', 'Oppo Reno 10', 'Oppo', 'Android', '13', '+225 05 44 55 67', 'MTN CI', 'actif'),
    ]

    appareils = []
    for i, (uid, imei, modele, marque, os, ver, tel, op, statut) in enumerate(appareils_data):
        a = Appareil(
            user_id=uid, imei=imei, modele=modele, marque=marque,
            systeme_os=os, version_os=ver, numero_telephone=tel,
            operateur=op, statut=statut,
            date_enregistrement=datetime.now(timezone.utc) - timedelta(days=random.randint(5, 80))
        )
        appareils.append(a)
        db.session.add(a)

    try:
        db.session.commit()
        print(f"  [OK] {len(appareils)} appareils crees")
    except Exception:
        db.session.rollback()
        print("  [INFO] Appareils deja existants, chargement...")
        appareils = Appareil.query.all()

    # Si la liste est vide, charger depuis la base
    if not appareils:
        appareils = Appareil.query.all()

    # ═══════════════════════════════════════
    # 3. ALERTES
    # ═══════════════════════════════════════
    print("\n[ALERT] Creation des alertes...")

    alertes_data = [
        (user1.id, appareils[2].id, 'vol',
         'Téléphone volé au marché de Treichville vers 14h.',
         'en_cours', 'critique', 3),
        (user2.id, appareils[4].id, 'vol',
         'Vol à l\'arraché dans le bus à Adjamé.',
         'en_cours', 'critique', 7),
        (user4.id, appareils[7].id, 'vol',
         'Disparition suspecte au plateau, probablement volé.',
         'en_cours', 'haute', 2),
        (user1.id, appareils[1].id, 'perte',
         'iPhone oublié dans un taxi.', 'traité', 'haute', 20),
        (user3.id, appareils[5].id, 'anomalie',
         'Détection d\'une activité suspecte sur le réseau.',
         'traité', 'moyenne', 15),
        (user2.id, appareils[3].id, 'changement_sim',
         'Carte SIM changée sans autorisation.',
         'en_cours', 'haute', 1),
        (user4.id, appareils[6].id, 'perte',
         'Téléphone perdu lors d\'un déplacement à Bouaké.',
         'traité', 'moyenne', 25),
    ]

    alertes = []
    for uid, aid, type_a, desc, statut, priorite, jours in alertes_data:
        alerte = Alerte(
            user_id=uid, appareil_id=aid, type_alerte=type_a,
            description=desc, statut=statut, priorite=priorite,
            date_creation=datetime.now(timezone.utc) - timedelta(days=jours),
            date_resolution=datetime.now(timezone.utc) - timedelta(days=jours - 2) if statut == 'traité' else None
        )
        alertes.append(alerte)
        db.session.add(alerte)

    try:
        db.session.commit()
        print(f"  [OK] {len(alertes)} alertes creees")
    except Exception:
        db.session.rollback()
        print("  [INFO] Alertes deja existantes, chargement...")
        alertes = Alerte.query.all()

    if not alertes:
        alertes = Alerte.query.all()

    # ═══════════════════════════════════════
    # 4. NOTIFICATIONS
    # ═══════════════════════════════════════
    print("\n[NOTIF] Creation des notifications...")

    notifs_count = 0
    for alerte in alertes:
        user = db.session.get(User, alerte.user_id)
        if not user:
            continue
        for ntype in ['push', 'email', 'sms']:
            notif = Notification(
                alerte_id=alerte.id,
                type_notification=ntype,
                contenu=f'ALERTE {alerte.type_alerte.upper()} — Appareil ID:{alerte.appareil_id}',
                destinataire=user.email if ntype == 'email' else user.telephone,
                statut='envoyé',
                date_envoi=alerte.date_creation
            )
            db.session.add(notif)
            notifs_count += 1

    print(f"  [OK] {notifs_count} notifications creees")

    # ═══════════════════════════════════════
    # 5. LOCALISATIONS GPS
    # ═══════════════════════════════════════
    print("\n[GPS] Creation des localisations GPS...")

    appareils_db = Appareil.query.all() if not appareils else appareils

    # Coordonnées autour d'Abidjan
    locs_data = [
        # Galaxy A54 volé - trajet du voleur
        (appareils_db[2].id, 5.3364, -4.0266, 'Treichville, Abidjan', 15.0, 'gps', 3),
        (appareils_db[2].id, 5.3450, -4.0180, 'Marcory, Abidjan', 25.0, 'réseau', 2.9),
        (appareils_db[2].id, 5.3560, -4.0120, 'Koumassi, Abidjan', 50.0, 'réseau', 2.5),
        (appareils_db[2].id, 5.3100, -4.0150, 'Port-Bouët, Abidjan', 30.0, 'gps', 2),
        # Tecno verrouillé
        (appareils_db[4].id, 5.3600, -3.9900, 'Adjamé, Abidjan', 10.0, 'gps', 7),
        (appareils_db[4].id, 5.3550, -3.9850, 'Attécoubé, Abidjan', 20.0, 'wifi', 6),
        # Infinix volé
        (appareils_db[7].id, 5.3200, -4.0050, 'Le Plateau, Abidjan', 8.0, 'gps', 2),
        (appareils_db[7].id, 5.3400, -3.9700, 'Yopougon, Abidjan', 45.0, 'réseau', 1.5),
        # iPhone normal
        (appareils_db[1].id, 5.3480, -4.0080, 'Cocody, Abidjan', 5.0, 'gps', 0.5),
        # Galaxy S24 admin
        (appareils_db[0].id, 5.3590, -3.9750, 'Riviera, Cocody', 3.0, 'gps', 0.1),
        # Redmi
        (appareils_db[3].id, 5.3100, -4.0300, 'Vridi, Port-Bouët', 12.0, 'gps', 1),
    ]

    locs_count = 0
    for aid, lat, lon, adr, prec, src, jours in locs_data:
        loc = Localisation(
            appareil_id=aid, latitude=lat, longitude=lon,
            adresse=adr, precision_m=prec, source=src,
            date_capture=datetime.now(timezone.utc) - timedelta(days=jours)
        )
        db.session.add(loc)
        locs_count += 1

    print(f"  [OK] {locs_count} localisations GPS creees")

    # ═══════════════════════════════════════
    # 6. ZONES À RISQUE
    # ═══════════════════════════════════════
    print("\n[ZONE] Creation des zones a risque...")

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
        zone = ZoneRisque(
            nom=nom, ville=ville, latitude=lat, longitude=lon,
            rayon_m=rayon, niveau_risque=niveau, nombre_incidents=incidents,
            date_mise_a_jour=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))
        )
        db.session.add(zone)

    print(f"  [OK] {len(zones_data)} zones a risque creees")

    # ═══════════════════════════════════════
    # 7. ACTIVITÉS UTILISATEURS
    # ═══════════════════════════════════════
    print("\n[ACTIVITE] Creation du journal d'activite...")

    activites_data = [
        (admin.id, 'connexion', 'Connexion Admin', 0.1),
        (admin.id, 'connexion', 'Connexion Admin', 1),
        (admin.id, 'connexion', 'Connexion Admin', 2),
        (admin.id, 'connexion', 'Connexion Admin', 3),
        (admin.id, 'connexion', 'Connexion Admin', 5),
        (user1.id, 'inscription', 'Nouveau compte : aminata.kone@email.ci', 60),
        (user1.id, 'connexion', 'Connexion de Aminata Koné', 55),
        (user1.id, 'ajout_appareil', 'Apple iPhone 15 Pro (IMEI: 351234567890456)', 55),
        (user1.id, 'ajout_appareil', 'Samsung Galaxy A54 (IMEI: 351234567890789)', 50),
        (user1.id, 'signalement_alerte', 'Vol — Galaxy A54', 3),
        (user1.id, 'connexion', 'Connexion de Aminata Koné', 2),
        (user1.id, 'connexion', 'Connexion de Aminata Koné', 0.5),
        (user2.id, 'inscription', 'Nouveau compte : ibrahim.toure@email.ci', 45),
        (user2.id, 'connexion', 'Connexion de Ibrahim Touré', 40),
        (user2.id, 'ajout_appareil', 'Xiaomi Redmi Note 13', 40),
        (user2.id, 'ajout_appareil', 'Tecno Spark 20', 35),
        (user2.id, 'signalement_alerte', 'Vol — Tecno Spark 20', 7),
        (user2.id, 'connexion', 'Connexion de Ibrahim Touré', 1),
        (user3.id, 'inscription', 'Nouveau compte : fatou.diallo@email.ci', 30),
        (user3.id, 'connexion', 'Connexion de Fatou Diallo', 25),
        (user3.id, 'ajout_appareil', 'Apple iPhone 14', 25),
        (user3.id, 'connexion', 'Connexion de Fatou Diallo', 3),
        (user4.id, 'inscription', 'Nouveau compte : jeanmarc.yao@email.ci', 15),
        (user4.id, 'connexion', 'Connexion de Jean-Marc Yao', 14),
        (user4.id, 'ajout_appareil', 'Samsung Galaxy S23', 14),
        (user4.id, 'ajout_appareil', 'Infinix Hot 40', 12),
        (user4.id, 'signalement_alerte', 'Vol — Infinix Hot 40', 2),
        (user4.id, 'modification_profil', 'Mise à jour du profil', 10),
        (user4.id, 'connexion', 'Connexion de Jean-Marc Yao', 0.3),
        (user5.id, 'inscription', 'Nouveau compte : moussa.bamba@email.ci', 5),
        (user5.id, 'connexion', 'Connexion de Moussa Bamba', 4),
        (user5.id, 'ajout_appareil', 'Oppo Reno 10', 4),
    ]

    for uid, action, details, jours in activites_data:
        activite = ActiviteUtilisateur(
            user_id=uid, action=action, details=details,
            adresse_ip=f'192.168.1.{random.randint(2, 254)}',
            navigateur='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
            date=datetime.now(timezone.utc) - timedelta(days=jours, hours=random.randint(0, 23))
        )
        db.session.add(activite)

    print(f"  [OK] {len(activites_data)} activites creees")

    # ═══════════════════════════════════════
    # COMMIT FINAL
    # ═══════════════════════════════════════
    db.session.commit()

    print("\n" + "=" * 60)
    print("[OK] BASE DE DONNEES PEUPLEE AVEC SUCCES !")
    print("=" * 60)
    print(f"""
Resume :
   - 6 utilisateurs (1 admin + 5 utilisateurs)
   - 9 appareils (6 actifs, 2 voles, 1 verrouille)
   - 7 alertes (4 en cours, 3 resolues)
   - {notifs_count} notifications
   - {locs_count} localisations GPS
   - {len(zones_data)} zones a risque (Abidjan + Bouake)
   - {len(activites_data)} activites utilisateurs

Comptes de connexion :
   ADMIN : admin@nox-antivol.ci / admin123
   USER  : aminata.kone@email.ci / motdepasse
""")
