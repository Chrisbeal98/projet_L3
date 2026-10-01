"""
Amorçage de la base de données au démarrage du serveur.

Ce module_exists pour une raison précise : depuis l'arrivée d'Alembic, AUCUN
`CREATE TABLE` ni `ALTER TABLE` ne doit être exécuté au démarrage. Le schéma
est décrit par les révisions de `migrations/versions/`, et c'est le seul endroit
qui a le droit de le modifier.

`run.py` (développement) et `wsgi.py` (gunicorn / Render) appellent donc
`preparer_base()` au lieu de `db.create_all()`. En production, Render applique
en plus les migrations avant le déploiement (`preDeployCommand` dans
`render.yaml`) : `preparer_base()` est alors un no-op, car la base est déjà à
la révision `head`.

Ce module n'est PAS importé par `app/__init__.py` : une commande
`flask db ...` doit pouvoir s'exécuter sans déclencher la création du compte
administrateur ni du jeu de démonstration.
"""

import os
import random
import secrets
import string
from datetime import datetime, timedelta, timezone

from app import bcrypt, db
from app.models import Alerte, Appareil, User, ZoneRisque


# ─────────────────────────────────────────────
# MIGRATIONS
# ─────────────────────────────────────────────
def appliquer_migrations():
    """Aligne la base sur la dernière révision (`head`).

    Idempotent : Alembic ne rejoue que les révisions manquantes. Si le
    répertoire `migrations/` est absent (paquet déployé sans les sources de
    migration), on le dit clairement plutôt que d'échouer en silence ou de
    recréer les tables à l'aveugle.
    """
    from flask import current_app
    from flask_migrate import upgrade

    dossier = current_app.extensions['migrate'].directory
    if not os.path.isdir(dossier):
        current_app.logger.warning(
            'Répertoire de migrations introuvable (%s) : schéma laissé en l\'état. '
            'La base doit déjà être à jour.', dossier,
        )
        return

    upgrade(directory=dossier)


# ─────────────────────────────────────────────
# COMPTE ADMINISTRATEUR
# ─────────────────────────────────────────────
def _creer_ou_reparer_admin():
    """Crée le compte administrateur à partir des variables d'environnement.

    Aucun compte n'est codé en dur, et le mot de passe n'est JAMAIS réécrit au
    démarrage : l'ancien code le réinitialisait à chaque boot, ce qui rendait
    toute rotation de secret inopérante. Le mot de passe n'est réécrit que si
    une rotation explicite est demandée, ou si le compte n'a jamais eu de
    secret.

    Variables reconnues :
        ADMIN_EMAIL, ADMIN_PASSWORD          (création initiale)
        ADMIN_PASSWORD_MIGRATION             (rotation explicite, une fois)
        ADMIN_NOM, ADMIN_PRENOM, ADMIN_TELEPHONE
    """
    env = os.environ

    admin_email = (env.get('ADMIN_EMAIL') or '').strip().lower()
    admin_password = env.get('ADMIN_PASSWORD') or ''
    admin_rotation = env.get('ADMIN_PASSWORD_MIGRATION') or ''

    if not admin_email or not (admin_password or admin_rotation):
        print('[SECURITY] ADMIN_EMAIL / ADMIN_PASSWORD absents : '
              "aucun compte administrateur n'est créé. "
              "C'est le comportement attendu en production si l'admin existe déjà.")
        return

    if '@' not in admin_email or len(admin_rotation or admin_password) < 8:
        raise RuntimeError(
            'ADMIN_EMAIL invalide ou mot de passe administrateur trop court '
            '(8 caractères minimum). Refus de démarrer.'
        )

    admin = User.query.filter_by(email=admin_email).first()
    nouveau_mdp = admin_rotation or admin_password

    if not admin:
        admin = User(
            nom=(env.get('ADMIN_NOM') or 'Administrateur').strip(),
            prenom=(env.get('ADMIN_PRENOM') or 'Antivol').strip(),
            email=admin_email,
            password_hash=bcrypt.generate_password_hash(nouveau_mdp),
            role='admin',
            statut='actif',
            telephone=env.get('ADMIN_TELEPHONE') or None,
            date_creation=datetime.now(timezone.utc),
        )
        db.session.add(admin)
        print(f'[SECURITY] Compte administrateur créé : {admin_email}')
    else:
        if admin_rotation or not admin.password_hash:
            admin.password_hash = bcrypt.generate_password_hash(nouveau_mdp)
            print(f'[SECURITY] Mot de passe administrateur réinitialisé : {admin_email}')
        if admin.role != 'admin':
            admin.role = 'admin'

    db.session.commit()


# ─────────────────────────────────────────────
# SEED DE DÉMONSTRATION
# ─────────────────────────────────────────────
def _seed_demo_autorise():
    return os.environ.get('SEED_DEMO_DATA', '').strip().lower() in (
        '1', 'true', 'yes', 'on',
    )


def _seed_demo():
    """Jeu de données de démonstration, sur demande explicite.

    Il contient des comptes et des mots de passe connus : il ne doit JAMAIS
    être injecté en production. Le mot de passe est tiré au hasard à chaque
    exécution et affiché UNE FOIS dans les journaux de déploiement ; aucun mot
    de passe n'est écrit dans le dépôt.
    """
    if not _seed_demo_autorise() or Appareil.query.first():
        return

    print('[SEED] Aucun appareil trouvé — seed des données de démonstration...')

    mdp_demo = secrets.token_urlsafe(12)
    print(f'[SEED] Mot de passe des comptes de démonstration : {mdp_demo}')
    print('[SEED] CHANGEZ-LE immédiatement après connexion (page Profil).')

    demo_users = [
        User(nom='Koné', prenom='Aminata', email='aminata.kone@email.ci',
             telephone='+225 05 12 34 56', password_hash=bcrypt.generate_password_hash(mdp_demo),
             role='utilisateur', statut='actif',
             date_creation=datetime.now(timezone.utc) - timedelta(days=60)),
        User(nom='Touré', prenom='Ibrahim', email='ibrahim.toure@email.ci',
             telephone='+225 07 98 76 54', password_hash=bcrypt.generate_password_hash(mdp_demo),
             role='utilisateur', statut='actif',
             date_creation=datetime.now(timezone.utc) - timedelta(days=45)),
        User(nom='Diallo', prenom='Fatou', email='fatou.diallo@email.ci',
             telephone='+225 01 55 66 77', password_hash=bcrypt.generate_password_hash(mdp_demo),
             role='utilisateur', statut='actif',
             date_creation=datetime.now(timezone.utc) - timedelta(days=30)),
        User(nom='Yao', prenom='Jean-Marc', email='jeanmarc.yao@email.ci',
             telephone='+225 07 11 22 33', password_hash=bcrypt.generate_password_hash(mdp_demo),
             role='utilisateur', statut='actif',
             date_creation=datetime.now(timezone.utc) - timedelta(days=15)),
        User(nom='Bamba', prenom='Moussa', email='moussa.bamba@email.ci',
             telephone='+225 05 44 55 66', password_hash=bcrypt.generate_password_hash(mdp_demo),
             role='utilisateur', statut='suspendu',
             date_creation=datetime.now(timezone.utc) - timedelta(days=5)),
    ]
    for u in demo_users:
        if not User.query.filter_by(email=u.email).first():
            db.session.add(u)
    db.session.commit()

    # Recharger : le compte admin de référence est celui défini par ADMIN_EMAIL ;
    # à défaut, le premier appareil est rattaché à u1.
    u_admin = User.query.filter_by(role='admin').first()
    u1 = User.query.filter_by(email='aminata.kone@email.ci').first()
    u2 = User.query.filter_by(email='ibrahim.toure@email.ci').first()
    u3 = User.query.filter_by(email='fatou.diallo@email.ci').first()
    u4 = User.query.filter_by(email='jeanmarc.yao@email.ci').first()
    u5 = User.query.filter_by(email='moussa.bamba@email.ci').first()

    proprio_admin = u_admin.id if u_admin else u1.id

    devices_data = [
        (proprio_admin, '351234567890123', 'Galaxy S24 Ultra', 'Samsung', 'Android', '14', '+225 07 00 00 01', 'Orange CI', 'actif'),
        (u1.id, '351234567890456', 'iPhone 15 Pro', 'Apple', 'iOS', '17.2', '+225 05 12 34 57', 'MTN CI', 'actif'),
        (u1.id, '351234567890789', 'Galaxy A54', 'Samsung', 'Android', '13', '+225 05 12 34 58', 'Orange CI', 'volé'),
        (u2.id, '351234567891012', 'Redmi Note 13', 'Xiaomi', 'Android', '14', '+225 07 98 76 55', 'Moov Africa', 'actif'),
        (u2.id, '351234567891345', 'Tecno Spark 20', 'Tecno', 'Android', '13', '+225 07 98 76 56', 'Orange CI', 'verrouillé'),
        (u3.id, '351234567891678', 'iPhone 14', 'Apple', 'iOS', '16.5', '+225 01 55 66 78', 'MTN CI', 'actif'),
        (u4.id, '351234567891901', 'Galaxy S23', 'Samsung', 'Android', '14', '+225 07 11 22 34', 'Orange CI', 'actif'),
        (u4.id, '351234567892234', 'Infinix Hot 40', 'Infinix', 'Android', '13', '+225 07 11 22 35', 'Moov Africa', 'volé'),
        (u5.id, '351234567892567', 'Oppo Reno 10', 'Oppo', 'Android', '13', '+225 05 44 55 67', 'MTN CI', 'actif'),
    ]

    from app.routes.api import generer_code_pin, generer_code_verrouillage

    codes_vk = set()
    codes_pk = set()
    for uid, imei, modele, marque, os, ver, tel, op, statut in devices_data:
        while True:
            cv = ''.join(random.choices(string.digits, k=4))
            if cv not in codes_vk:
                codes_vk.add(cv)
                break
        while True:
            cp = ''.join(random.choices(string.digits, k=4))
            if cp not in codes_pk:
                codes_pk.add(cp)
                break
        db.session.add(Appareil(
            user_id=uid, imei=imei, modele=modele, marque=marque,
            systeme_os=os, version_os=ver, numero_telephone=tel,
            operateur=op, statut=statut,
            code_verrouillage=cv, code_ussd=cp,
            date_enregistrement=datetime.now(timezone.utc) - timedelta(days=random.randint(5, 80))
        ))
    db.session.commit()

    appareils = Appareil.query.order_by(Appareil.id).all()

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


# ─────────────────────────────────────────────
# ZONES À RISQUE
# ─────────────────────────────────────────────
def _seed_zones():
    """Les zones à risque sont des données de référence, pas de la démonstration.

    Elles décrivent des quartiers réels d'Abidjan : sans elles, la carte est
    vide et la démonstration de la fonctionnalité est impossible. Elles ne
    contiennent aucune donnée personnelle.
    """
    if ZoneRisque.query.first():
        return

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


# ─────────────────────────────────────────────
# POINT D'ENTRÉE
# ─────────────────────────────────────────────
def preparer_base():
    """Migrations + compte administrateur + données de référence.

    À appeler dans un contexte d'application, une fois, au démarrage.
    """
    appliquer_migrations()
    _creer_ou_reparer_admin()
    _seed_demo()
    _seed_zones()
    print('[OK] Démarrage terminé.')
