"""
Routes API REST — Antivol Intelligent.
Architecture 3-tiers — Couche Logique Métier (API).
"""

import secrets
import random
import string

from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user, login_user
from app import db, bcrypt
from app.models import User, Appareil, Alerte, Localisation, FcmToken, TelephoneCollecte
from datetime import datetime, timezone
from flask import current_app

api_bp = Blueprint('api', __name__)


def generer_code_verrouillage():
    """Génère un code de verrouillage unique à 4 chiffres."""
    while True:
        code = ''.join(random.choices(string.digits, k=4))
        if not Appareil.query.filter_by(code_verrouillage=code).first():
            return code


def generer_code_pin():
    """Génère un code PIN unique à 4 chiffres."""
    while True:
        code = ''.join(random.choices(string.digits, k=4))
        if not Appareil.query.filter_by(code_ussd=code).first():
            return code


def get_request_user():
    """Retourne l'utilisateur depuis la session (Flask-Login) ou depuis le body JSON (mobile)."""
    if current_user.is_authenticated:
        return current_user
    data = request.get_json(silent=True)
    if data and 'user_id' in data:
        uid = data.get('user_id')
        if uid is not None:
            return db.session.get(User, int(uid))
    return None


# ─── Anti-bot : limiteur de taux API ───
from datetime import datetime, timedelta
_tentatives_api_login = {}
_tentatives_api_register = {}

def _api_rate_limit(ip, stockage, limite=10, fenetre=300):
    maintenant = datetime.now()
    if ip in stockage:
        stockage[ip] = [t for t in stockage[ip] if maintenant - t < timedelta(seconds=fenetre)]
        if len(stockage[ip]) >= limite:
            return False
        stockage[ip].append(maintenant)
    else:
        stockage[ip] = [maintenant]
    return True


# ─────────────────────────────────────────────
# AUTH API (CORRIGÉ POUR LE TEST L3)
# ─────────────────────────────────────────────
@api_bp.route('/auth/register', methods=['POST'])
def api_register():
    """Inscription via API pour l'application mobile."""
    ip = request.remote_addr or 'unknown'
    if not _api_rate_limit(ip, _tentatives_api_register, limite=5, fenetre=600):
        return jsonify({'error': 'Trop de tentatives. Réessayez plus tard.'}), 429

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Données JSON manquantes'}), 400

    nom = data.get('nom')
    prenom = data.get('prenom')
    email = data.get('email')
    telephone = data.get('telephone')
    password = data.get('password')

    if not all([nom, prenom, email, password]):
        return jsonify({'error': 'Tous les champs obligatoires sont requis'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Cet email est déjà utilisé'}), 409

    new_user = User(
        nom=nom,
        prenom=prenom,
        email=email,
        telephone=telephone,
        password_hash=bcrypt.generate_password_hash(password).decode('utf-8')
    )

    db.session.add(new_user)
    db.session.commit()

    login_user(new_user)

    return jsonify({
        'message': 'Compte créé avec succès',
        'user': {'id': new_user.id, 'nom': new_user.nom, 'email': new_user.email}
    }), 201


@api_bp.route('/auth/login', methods=['POST'])
def api_login():
    ip = request.remote_addr or 'unknown'
    if not _api_rate_limit(ip, _tentatives_api_login, limite=10, fenetre=300):
        return jsonify({'error': 'Trop de tentatives. Réessayez plus tard.'}), 429

    data = request.get_json()

    if not data:
        return jsonify({'error': 'Données JSON manquantes'}), 400

    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()

    if user and bcrypt.check_password_hash(user.password_hash, password):
        login_user(user)
        return jsonify({
            'message': 'Connexion réussie',
            'user': {'id': user.id, 'nom': user.nom, 'email': user.email}
        }), 200

    print(f"--- ÉCHEC CONNEXION API : {email} ---")
    return jsonify({'error': 'Email ou mot de passe incorrect'}), 401


# ─────────────────────────────────────────────
# APPAREILS API
# ─────────────────────────────────────────────
@api_bp.route('/appareils', methods=['GET'])
@login_required
def get_appareils():
    """Récupérer les appareils de l'utilisateur connecté."""
    appareils = Appareil.query.filter_by(user_id=current_user.id).all()

    return jsonify([{
        'id': a.id, 'imei': a.imei, 'modele': a.modele,
        'marque': a.marque, 'statut': a.statut,
        'date_enregistrement': a.date_enregistrement.isoformat()
    } for a in appareils]), 200

@api_bp.route('/appareils/register', methods=['POST'])
def api_register_device():
    """Enregistrer un nouvel appareil (mobile)."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Données manquantes'}), 400

    imei = data.get('imei')
    modele = data.get('modele', 'Inconnu')
    marque = data.get('marque', 'Inconnu')

    if not imei:
        return jsonify({'error': 'IMEI requis'}), 400

    existing = Appareil.query.filter_by(imei=imei).first()
    if existing:
        if existing.user_id == user.id:
            return jsonify({
                'message': 'Appareil déjà enregistré',
                'id': existing.id,
                'imei': existing.imei
            }), 200
        return jsonify({'error': 'Cet IMEI est déjà enregistré par un autre utilisateur'}), 403

    if len(imei) > 20:
        imei = imei[:20]

    nouvel_appareil = Appareil(
        user_id=user.id,
        imei=imei,
        modele=modele,
        marque=marque,
        systeme_os='Android',
        version_os='Inconnue',
        code_verrouillage=generer_code_verrouillage(),
        code_ussd=generer_code_pin()
    )

    db.session.add(nouvel_appareil)
    db.session.commit()

    return jsonify({
        'message': 'Appareil enregistré',
        'id': nouvel_appareil.id,
        'imei': nouvel_appareil.imei,
        'code_verrouillage': nouvel_appareil.code_verrouillage,
        'code_pin': nouvel_appareil.code_ussd
    }), 201


@api_bp.route('/appareils/<int:id>/deverrouiller', methods=['POST'])
def api_deverrouiller(id):
    """Déverrouiller un appareil (propriétaire uniquement)."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    appareil = db.get_or_404(Appareil, id)

    if appareil.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    appareil.statut = 'actif'
    db.session.commit()

    print(f"--- ACTION REUSSIE : {appareil.modele} déverrouillé ---")
    return jsonify({'message': 'Appareil déverrouillé', 'statut': 'actif'}), 200


# ─────────────────────────────────────────────
# VÉRIFICATION DE VERROUILLAGE EN TEMPS RÉEL
# ─────────────────────────────────────────────
@api_bp.route('/appareils/<int:id>/statut', methods=['GET'])
def check_statut(id):
    """Le mobile interroge cet endpoint pour savoir s'il doit se verrouiller."""
    appareil = db.session.get(Appareil, id)
    if not appareil:
        return jsonify({"error": "Appareil introuvable"}), 404

    verrouille = appareil.statut in ('volé', 'verrouillé')

    return jsonify({
        "appareil_id": appareil.id,
        "imei": appareil.imei,
        "statut": appareil.statut,
        "verrouille": verrouille,
        "code_verrouillage": appareil.code_verrouillage,
        "code_pin": appareil.code_ussd,
        "message": (
            "VERROUILLAGE ACTIF — Cet appareil a été signalé comme volé ou perdu"
            if verrouille else "Appareil normal"
        )
    }), 200


# ─────────────────────────────────────────────
# VERROUILLAGE À DISTANCE
# ─────────────────────────────────────────────
@api_bp.route('/appareils/<int:id>/verrouiller', methods=['POST'])
def api_verrouiller(id):
    """Verrouiller un appareil à distance (authentifié)."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    appareil = db.get_or_404(Appareil, id)

    if appareil.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    appareil.statut = 'verrouillé'
    db.session.commit()

    print(f"--- ACTION REUSSIE : {appareil.modele} verrouillé ---")
    return jsonify({'message': 'Appareil verrouillé', 'statut': 'verrouillé'}), 200


@api_bp.route('/appareils/verrouiller-par-code', methods=['POST'])
def api_verrouiller_par_code():
    """Verrouiller un appareil en utilisant son code de verrouillage (sans authentification).

    Permet à un utilisateur de verrouiller son téléphone depuis n'importe quel appareil
    (autre téléphone, navigateur) en connaissant uniquement le code.
    """
    data = request.get_json()
    if not data or 'code' not in data:
        return jsonify({'error': 'Code de verrouillage requis'}), 400

    code = data.get('code', '').strip()

    appareil = Appareil.query.filter_by(code_verrouillage=code).first()
    if not appareil:
        return jsonify({'error': 'Code invalide. Aucun appareil trouvé avec ce code.'}), 404

    if appareil.statut in ('volé', 'verrouillé'):
        return jsonify({'error': 'Cet appareil est déjà verrouillé', 'statut': appareil.statut}), 409

    appareil.statut = 'verrouillé'
    db.session.commit()

    # Créer une alerte automatique
    alerte = Alerte(
        user_id=appareil.user_id,
        appareil_id=appareil.id,
        type_alerte='perte',
        description='Verrouillé à distance via code de verrouillage',
        priorite='haute',
        statut='en_cours'
    )
    db.session.add(alerte)
    db.session.commit()

    return jsonify({
        'message': 'Appareil verrouillé avec succès',
        'statut': 'verrouillé',
        'appareil': f"{appareil.marque} {appareil.modele}"
    }), 200


@api_bp.route('/appareils/<int:id>/verrouiller-pin', methods=['POST'])
def api_verrouiller_pin(id):
    """Verrouiller via code PIN (authentifié)."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    appareil = db.get_or_404(Appareil, id)
    if appareil.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    if not appareil.code_ussd:
        return jsonify({'error': 'Aucun code PIN généré pour cet appareil'}), 404

    appareil.statut = 'verrouillé'
    db.session.commit()

    return jsonify({
        'message': 'Appareil verrouillé via PIN',
        'code_pin': appareil.code_ussd,
        'statut': 'verrouillé'
    }), 200


@api_bp.route('/appareils/<int:id>/codes', methods=['GET'])
def api_get_codes(id):
    """Récupérer les codes de verrouillage d'un appareil (authentifié)."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    appareil = db.get_or_404(Appareil, id)
    if appareil.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    return jsonify({
        'appareil_id': appareil.id,
        'code_verrouillage': appareil.code_verrouillage,
        'code_pin': appareil.code_ussd
    }), 200


# ─────────────────────────────────────────────
# GÉOLOCALISATION EN TEMPS RÉEL (NOUVEAU)
# ─────────────────────────────────────────────
@api_bp.route('/localisation/update', methods=['POST'])
def update_localisation():
    """Réception des coordonnées GPS réelles du mobile."""
    data = request.get_json()
    appareil_id = data.get('appareil_id')
    lat = data.get('latitude')
    lng = data.get('longitude')

    if not lat or not lng:
        return jsonify({"error": "Données GPS incomplètes"}), 400

    if appareil_id:
        appareil = db.session.get(Appareil, appareil_id)
        if not appareil:
            return jsonify({"error": "Appareil introuvable"}), 404

        nouvelle_loc = Localisation(
            appareil_id=appareil_id,
            latitude=lat,
            longitude=lng,
            precision_m=data.get('precision_m'),
            source=data.get('source', 'gps'),
            date_capture=datetime.now(timezone.utc)
        )
        db.session.add(nouvelle_loc)
        db.session.commit()
        print(f"--- GPS REÇU : Appareil {appareil_id} à ({lat}, {lng}) ---")

    return jsonify({"status": "success", "message": "Position mise à jour"}), 200


@api_bp.route('/localisations/latest', methods=['GET'])
@login_required
def get_latest_localisations():
    """Renvoie la dernière position + les 30 dernières positions de chaque appareil."""
    if current_user.role == 'admin':
        q = Appareil.query
    else:
        q = Appareil.query.filter_by(user_id=current_user.id)

    appareils = q.all()
    if not appareils:
        return jsonify([]), 200

    LIMIT = 30
    result = []

    for app in appareils:
        positions = Localisation.query \
            .filter_by(appareil_id=app.id) \
            .order_by(Localisation.date_capture.desc()) \
            .limit(LIMIT) \
            .all()

        if not positions:
            continue

        trail = [{
            'latitude': p.latitude,
            'longitude': p.longitude,
            'date_capture': p.date_capture.isoformat() if hasattr(p.date_capture, 'isoformat') else str(p.date_capture),
            'precision_m': p.precision_m,
            'source': p.source,
            'adresse': p.adresse,
        } for p in reversed(positions)]

        d = positions[0]
        result.append({
            'appareil_id': app.id,
            'marque': app.marque,
            'modele': app.modele,
            'imei': app.imei,
            'statut': app.statut,
            'latitude': d.latitude,
            'longitude': d.longitude,
            'precision_m': d.precision_m,
            'source': d.source,
            'adresse': d.adresse,
            'date_capture': d.date_capture.isoformat() if hasattr(d.date_capture, 'isoformat') else str(d.date_capture),
            'trail': trail,
        })

    return jsonify(result), 200


@api_bp.route('/localisations/historique/<int:appareil_id>', methods=['GET'])
@login_required
def get_historique_localisations(appareil_id):
    """Renvoie l'historique complet des positions d'un appareil."""
    appareil = db.session.get(Appareil, appareil_id)
    if not appareil:
        return jsonify({'error': 'Appareil introuvable'}), 404
    if appareil.user_id != current_user.id and current_user.role != 'admin':
        return jsonify({'error': 'Accès refusé'}), 403

    positions = Localisation.query \
        .filter_by(appareil_id=appareil_id) \
        .order_by(Localisation.date_capture.asc()) \
        .all()

    return jsonify([{
        'latitude': p.latitude,
        'longitude': p.longitude,
        'precision_m': p.precision_m,
        'source': p.source,
        'adresse': p.adresse,
        'date_capture': p.date_capture.isoformat()
    } for p in positions]), 200


# ─────────────────────────────────────────────
# VÉRIFICATION CODE DÉVERROUILLAGE (MOBILE)
# ─────────────────────────────────────────────
@api_bp.route('/appareils/<int:id>/verifier-code', methods=['POST'])
def api_verifier_code(id):
    """Vérifier le code de déverrouillage saisi sur le mobile.
    Utilise les 4 derniers chiffres du mot de passe de l'utilisateur."""
    data = request.get_json()
    if not data or 'code' not in data:
        return jsonify({'error': 'Code manquant'}), 400

    appareil = db.session.get(Appareil, id)
    if not appareil:
        return jsonify({'error': 'Appareil introuvable'}), 404

    proprietaire = db.session.get(User, appareil.user_id)
    if not proprietaire:
        return jsonify({'error': 'Propriétaire introuvable'}), 404

    code_saisi = data.get('code', '').strip()

    pwd_hash = proprietaire.password_hash
    if isinstance(pwd_hash, bytes):
        pwd_hash = pwd_hash.decode('utf-8')
    hash_clean = pwd_hash.replace('$2b$', '').replace('$2a$', '')
    chiffres = ''.join([c for c in hash_clean if c.isdigit()])
    if len(chiffres) >= 4:
        code_attendu = chiffres[-4:]
    else:
        code_attendu = chiffres.zfill(4)[:4]

    if code_saisi == code_attendu:
        appareil.statut = 'actif'
        db.session.commit()
        print(f"--- CODE CORRECT : Appareil {appareil.id} déverrouillé ---")
        return jsonify({'message': 'Code correct', 'statut': 'actif'}), 200

    print(f"--- CODE INCORRECT : saisi={code_saisi}, attendu={code_attendu} ---")
    return jsonify({'error': 'Code incorrect'}), 401


# ─────────────────────────────────────────────
# DASHBOARD / STATISTIQUES
# ─────────────────────────────────────────────
@api_bp.route('/dashboard/stats', methods=['GET', 'POST'])
def api_dashboard_stats():
    """Statistiques pour le tableau de bord mobile."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    appareils = Appareil.query.filter_by(user_id=user.id).all()
    total_appareils = len(appareils)
    total_voles = sum(1 for a in appareils if a.statut == 'volé')
    total_verrouilles = sum(1 for a in appareils if a.statut == 'verrouillé')
    total_alertes = Alerte.query.filter_by(user_id=user.id, statut='en_cours').count()

    return jsonify({
        'total_appareils': total_appareils,
        'total_alertes': total_alertes,
        'total_voles': total_voles,
        'total_verrouilles': total_verrouilles,
    }), 200


# ─────────────────────────────────────────────
# PROFIL UTILISATEUR
# ─────────────────────────────────────────────
@api_bp.route('/auth/me', methods=['GET', 'POST'])
def api_me():
    """Profil de l'utilisateur connecté."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    return jsonify({
        'user': {
            'id': user.id,
            'nom': user.nom,
            'prenom': user.prenom,
            'email': user.email,
            'telephone': user.telephone or '',
            'role': user.role,
            'date_creation': user.date_creation.isoformat() if user.date_creation else None
        }
    }), 200


# ─────────────────────────────────────────────
# ALERTES API
# ─────────────────────────────────────────────
@api_bp.route('/alertes', methods=['GET', 'POST'])
def get_alertes():
    """Liste des alertes de l'utilisateur connecté."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    alertes = Alerte.query.filter_by(user_id=user.id).order_by(Alerte.date_creation.desc()).all()
    return jsonify([{
        'id': a.id,
        'type': a.type_alerte,
        'description': a.description or '',
        'statut': a.statut,
        'priorite': a.priorite,
        'appareil_id': a.appareil_id,
        'date_creation': a.date_creation.isoformat() if a.date_creation else None
    } for a in alertes]), 200


@api_bp.route('/alertes/signaler', methods=['POST'])
def api_signaler_alerte():
    """Signaler un vol ou une perte."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Données manquantes'}), 400

    appareil_id = data.get('appareil_id')
    type_alerte = data.get('type_alerte', 'vol')
    description = data.get('description', '')

    if not appareil_id:
        return jsonify({'error': 'appareil_id requis'}), 400

    appareil = db.session.get(Appareil, int(appareil_id))
    if not appareil or appareil.user_id != user.id:
        return jsonify({'error': 'Appareil introuvable'}), 404

    if type_alerte == 'vol':
        appareil.statut = 'volé'
    elif type_alerte == 'perte':
        appareil.statut = 'perdu'

    nouvelle_alerte = Alerte(
        user_id=user.id,
        appareil_id=appareil.id,
        type_alerte=type_alerte,
        description=description,
        priorite='haute'
    )
    db.session.add(nouvelle_alerte)
    db.session.commit()

    return jsonify({
        'message': 'Alerte créée',
        'id': nouvelle_alerte.id
    }), 201


@api_bp.route('/alertes/<int:id>/resoudre', methods=['POST'])
def api_resoudre_alerte(id):
    """Résoudre une alerte."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    alerte = db.get_or_404(Alerte, id)
    if alerte.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    alerte.statut = 'traité'
    alerte.date_resolution = datetime.now(timezone.utc)

    appareil = db.session.get(Appareil, alerte.appareil_id)
    if appareil and appareil.statut in ('volé', 'perdu'):
        appareil.statut = 'actif'

    db.session.commit()
    return jsonify({'message': 'Alerte résolue'}), 200


# ─────────────────────────────────────────────
# FCM PUSH NOTIFICATIONS
# ─────────────────────────────────────────────
@api_bp.route('/fcm/register-token', methods=['POST'])
def register_fcm_token():
    """Enregistrer ou mettre à jour un token FCM pour l'utilisateur connecté."""
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Données manquantes'}), 400

    token = data.get('fcm_token')

    if not token:
        return jsonify({'error': 'fcm_token requis'}), 400

    existing = FcmToken.query.filter_by(token=token).first()
    if existing:
        existing.user_id = user.id
        existing.date_mise_a_jour = datetime.now(timezone.utc)
    else:
        new_token = FcmToken(
            user_id=user.id,
            token=token
        )
        db.session.add(new_token)

    db.session.commit()
    return jsonify({'message': 'Token enregistré'}), 200


# ─────────────────────────────────────────────
# COLLECTE AUTO INFOS TÉLÉPHONE (WEB)
# ─────────────────────────────────────────────
@api_bp.route('/phone-info/collect', methods=['POST'])
def api_collect_phone_info():
    """Collecte automatique des informations du téléphone depuis le navigateur."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Données manquantes'}), 400

    user = get_request_user()
    session_id = request.cookies.get('session', '')

    info = TelephoneCollecte(
        user_id=user.id if user else None,
        session_id=session_id,
        modele=data.get('modele', 'Inconnu'),
        marque=data.get('marque', 'Inconnu'),
        systeme_os=data.get('systeme_os', 'Inconnu'),
        version_os=data.get('version_os', 'Inconnue'),
        navigateur=data.get('navigateur', 'Inconnu'),
        ecran_largeur=data.get('ecran_largeur'),
        ecran_hauteur=data.get('ecran_hauteur'),
        langue=data.get('langue'),
        ip=request.remote_addr,
        consentement=data.get('consentement', False),
        date_collecte=datetime.now(timezone.utc)
    )
    db.session.add(info)
    db.session.commit()

    return jsonify({'message': 'Informations collectées', 'id': info.id}), 201


# ─────────────────────────────────────────────
# MOBILE — VERROUILLAGE NATIF
# ─────────────────────────────────────────────
@api_bp.route('/mobile/register', methods=['POST'])
def mobile_register():
    """Enregistrement d'un appareil Android (sans auth, via UUID unique)."""
    data = request.get_json()
    if not data or 'device_uuid' not in data:
        return jsonify({'error': 'device_uuid requis'}), 400

    device_uuid = data['device_uuid'].strip()
    if not device_uuid or len(device_uuid) < 8:
        return jsonify({'error': 'device_uuid invalide'}), 400

    existing = Appareil.query.filter_by(device_uuid=device_uuid).first()
    if existing:
        return jsonify({
            'message': 'Appareil déjà enregistré',
            'id': existing.id,
            'device_uuid': existing.device_uuid,
            'statut': existing.statut
        }), 200

    modele = data.get('modele', 'Inconnu')
    marque = data.get('marque', 'Inconnu')
    version_os = data.get('version_os', 'Inconnue')

    from app.models import Appareil
    import secrets
    nouveau = Appareil(
        user_id=1,  # admin par défaut
        imei=device_uuid[:20],
        modele=modele,
        marque=marque,
        systeme_os='Android',
        version_os=version_os,
        device_uuid=device_uuid,
        code_verrouillage=generer_code_verrouillage(),
        code_ussd=generer_code_pin(),
        statut='actif'
    )
    db.session.add(nouveau)
    db.session.commit()

    return jsonify({
        'message': 'Appareil enregistré',
        'id': nouveau.id,
        'device_uuid': nouveau.device_uuid,
        'code_verrouillage': nouveau.code_verrouillage,
        'statut': nouveau.statut
    }), 201


@api_bp.route('/mobile/status/<device_uuid>', methods=['GET'])
def mobile_status(device_uuid):
    """Vérifier le statut de verrouillage (sans auth)."""
    appareil = Appareil.query.filter_by(device_uuid=device_uuid).first()
    if not appareil:
        return jsonify({'error': 'Appareil introuvable'}), 404

    verrouille = appareil.statut in ('volé', 'verrouillé')

    return jsonify({
        'appareil_id': appareil.id,
        'statut': appareil.statut,
        'verrouille': verrouille,
        'code_verrouillage': appareil.code_verrouillage,
        'message': 'VERROUILLÉ' if verrouille else 'ACTIF'
    }), 200


@api_bp.route('/mobile/unlock', methods=['POST'])
def mobile_unlock():
    """Déverrouiller avec le code de verrouillage."""
    data = request.get_json()
    if not data or 'device_uuid' not in data or 'code' not in data:
        return jsonify({'error': 'device_uuid et code requis'}), 400

    appareil = Appareil.query.filter_by(device_uuid=data['device_uuid']).first()
    if not appareil:
        return jsonify({'error': 'Appareil introuvable'}), 404

    if not appareil.code_verrouillage:
        return jsonify({'error': 'Aucun code de verrouillage défini'}), 400

    if data['code'].strip() == appareil.code_verrouillage:
        appareil.statut = 'actif'
        db.session.commit()
        return jsonify({'message': 'Déverrouillé', 'statut': 'actif'}), 200

    return jsonify({'error': 'Code incorrect'}), 401


@api_bp.route('/mobile/lock/<device_uuid>', methods=['POST'])
def mobile_lock(device_uuid):
    """Verrouiller un appareil par UUID."""
    appareil = Appareil.query.filter_by(device_uuid=device_uuid).first()
    if not appareil:
        return jsonify({'error': 'Appareil introuvable'}), 404

    if appareil.statut in ('volé', 'verrouillé'):
        return jsonify({'error': 'Déjà verrouillé', 'statut': appareil.statut}), 409

    appareil.statut = 'verrouillé'
    db.session.commit()

    alerte = Alerte(
        user_id=appareil.user_id,
        appareil_id=appareil.id,
        type_alerte='perte',
        description='Verrouillé depuis l\'application Android',
        priorite='haute',
        statut='en_cours'
    )
    db.session.add(alerte)
    db.session.commit()

    return jsonify({'message': 'Appareil verrouillé', 'statut': 'verrouillé'}), 200

