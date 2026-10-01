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
from app.models import User, Appareil, Alerte, Localisation, FcmToken, TelephoneCollecte, ZoneRisque
from app.device_auth import (
    appareil_authentifie, appareil_est_actif, enroller_appareil,
    generer_device_token, secret_de,
)
from datetime import datetime, timezone
from flask import current_app

api_bp = Blueprint('api', __name__)


# Alphabet sans caractères ambigus : 0/O, 1/I/L, 2/Z, 5/S, 8/B. Un code lu au
# téléphone ou recopié depuis un écran ne doit jamais prêter à confusion.
_ALPHABET_CODE = '34679ACDEFGHJKMNPQRTUVWXY'


def generer_code_verrouillage():
    """Génère un code de verrouillage unique.

    AVANT : 4 chiffres, soit 10 000 possibilités — trouvables en force brute
    sur l'endpoint `/verifier-code` (et sur `/verrouiller-par-code` avant son
    correctif). MAINTENANT : 8 caractères d'un alphabet de 25, soit environ
    1,5 × 10^11 possibilités. L'interface de saisie est unchanged côté client :
    le champ accepte une chaîne.

    Les appareils déjà enregistrés conservent leur ancien code court : c'est
    sans danger tant que la vérification exige l'authentification, et cela
    évite de casser un téléphone volé dont le propriétaire a noté le code.
    """
    while True:
        code = ''.join(secrets.choice(_ALPHABET_CODE) for _ in range(8))
        if not Appareil.query.filter_by(code_verrouillage=code).first():
            return code


def generer_code_pin():
    """Génère un code PIN de 6 chiffres.

    AVANT : 4 chiffres, donc 10 000 codes possibles pour un code censé
    protéger l'accès au contenu du téléphone. 6 chiffres portent l'espace à
    un million : combined avec la limitation de taux et l'authentification,
    l'attaque en ligne devient impraticable.
    """
    while True:
        code = ''.join(secrets.choice(string.digits) for _ in range(6))
        if not Appareil.query.filter_by(code_ussd=code).first():
            return code


def get_request_user():
    """Retourne l'utilisateur de la requête.

    SOURCE D'IDENTITE UNIQUE : la session serveur (Flask-Login).

    Historiquement cette fonction acceptait un `user_id` dans le corps JSON.
    C'était une faille critique : n'importe quel client pouvait envoyer
    l'identifiant d'un autre utilisateur et agir en son nom (usurpation, et
    élévation de privilèges si la cible était un administrateur). Le
    `user_id` du client n'est désormais JAMAIS utilisé comme identité.

    Note : le client mobile se connecte via `/api/auth/login`, qui appelle
    `login_user()` et pose donc une vraie session serveur.
    """
    if current_user.is_authenticated:
        return current_user
    return None


def exiger_proprietaire(appareil, user=None):
    """Renvoie l'appareil si l'utilisateur courant en est le propriétaire.

    Un administrateur est autorisé à agir sur n'importe quel appareil.
    """
    user = user or (current_user if current_user.is_authenticated else None)
    if not user or not appareil:
        return None
    if getattr(user, 'role', None) == 'admin' or appareil.user_id == user.id:
        return appareil
    return None


# ─── Anti-bot : limiteur de taux API ───
from datetime import datetime, timedelta
_tentatives_api_login = {}
_tentatives_api_register = {}
_tentatives_api_code = {}      # essais de code de déverrouillage
_tentatives_api_code_vk = {}   # verrouillage par code (force brute du code)

# Paliers d'attente après N échecs, en secondes. Le dernier palier est
# volontairement très long : au-delà, les essais restants deviennent
# irréalistes même en répartissant l'attaque sur plusieurs adresses IP.
_PALIERS_VERROUILLAGE = (0, 15, 60, 300, 900, 3600, 21600)
_ECHECS_MAX = len(_PALIERS_VERROUILLAGE) - 1

_CLE_EXTENSIONS = 'antivol_blocages_code'


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


class BlocagesCode:
    """Verrouillage progressif des essais de code, par APPAREIL.

    Indexé par l'identifiant de l'appareil et non par l'adresse IP : c'est la
    seule clé qui résiste à une attaque distribuée (rotation d'IP, proxies,
    VPN). Un limiteur par IP se contourne en changeant d'adresse ; celui-ci
    s'attache au code qu'on cherche à deviner.

    Le temps d'attente croît à chaque échec (15 s, 1 min, 5 min, 15 min,
    1 h, 6 h) ; un code correct remet le compteur à zéro.

    IMPORTANT — un code correct n'est jamais refusé. Le blocage retarde les
    essais, il ne les condamne pas : sinon cinq erreurs d'un attaquant
    rendraient le téléphone inutilisable pour son propriétaire pendant six
    heures, ce qui est un déni de service gratuit. La comparaison a lieu
    dans tous les cas, donc un attaquant n'en apprend rien de plus.

    L'état appartient à l'application (`current_app.extensions`) et non au
    module : deux applications coexistent dans les tests et ne partagent
    ainsi aucun historique d'échecs. L'horloge est injectable pour que les
    paliers soient testables sans dormir pendant deux heures.
    """

    def __init__(self, horloge=None):
        self._blocages = {}
        self._horloge = horloge or (lambda: datetime.now())

    def secondes_restantes(self, appareil_id):
        maintenant = self._horloge()
        entree = self._blocages.get(appareil_id)
        if not entree:
            return 0
        if entree['jusqua'] <= maintenant:
            # Palier expiré : un nouvel essai est autorisé, mais le COMPTEUR
            # d'échecs est conservé. Le purger ici rendrait le verrouillage
            # inopérant : il suffirait d'attendre 15 s pour repartir de zéro
            # et essayer les 10^6 PIN à un rythme de 4 essais par minute.
            return 0
        return int((entree['jusqua'] - maintenant).total_seconds())

    def autorise(self, appareil_id):
        return self.secondes_restantes(appareil_id) == 0

    def echec(self, appareil_id):
        maintenant = self._horloge()
        entree = self._blocages.get(appareil_id) or {'echecs': 0, 'jusqua': maintenant}
        entree['echecs'] += 1
        palier = min(entree['echecs'], _ECHECS_MAX)
        entree['jusqua'] = maintenant + timedelta(seconds=_PALIERS_VERROUILLAGE[palier])
        self._blocages[appareil_id] = entree
        return _PALIERS_VERROUILLAGE[palier]

    def reussite(self, appareil_id):
        self._blocages.pop(appareil_id, None)


def _blocages():
    """Instance de `BlocagesCode` propre à l'application courante."""
    extensions = current_app.extensions
    if _CLE_EXTENSIONS not in extensions:
        extensions[_CLE_EXTENSIONS] = BlocagesCode()
    return extensions[_CLE_EXTENSIONS]


def _secondes_restantes(appareil_id):
    return _blocages().secondes_restantes(appareil_id)


def _enregistrer_echec_code(appareil_id):
    return _blocages().echec(appareil_id)


def _reussir_essai_code(appareil_id):
    _blocages().reussite(appareil_id)


def _hmac_compare(a, b):
    """Comparaison en temps constant de deux secrets.

    `==` s'arrête au premier caractère différent : la durée de la comparaison
    renseigne l'attaquant sur le nombre de caractères corrects, ce qui réduit
    une recherche exhaustive de 10^8 combinaisons à quelques milliers
    d'essais. Tout code de déverrouillage passe par ici.
    """
    import hmac as _hmac
    return _hmac.compare_digest((a or '').encode('utf-8'), (b or '').encode('utf-8'))


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

    current_app.logger.warning("Échec de connexion API : %s", email)
    return jsonify({'error': 'Email ou mot de passe incorrect'}), 401


# ─────────────────────────────────────────────
# APPAREILS API
# ─────────────────────────────────────────────
@api_bp.route('/appareils', methods=['GET'])
@login_required
def get_appareils():
    """Récupère les appareils de l'utilisateur connecté.

    Avant cette correction, la requête renvoyait TOUS les appareils ayant un
    `device_uuid` (c'est-à-dire tous les téléphones enregistrés par les
    autres utilisateurs), avec leur IMEI et leur code de verrouillage. C'était
    une fuite de données massive : il suffisait d'être inscrit pour inventorier
    et déverrouiller les téléphones des autres.

    Le partage entre utilisateurs est désormais OPT-IN et explicite : il repose
    sur la table `alertes`, et ne partage que des métadonnées publiques — jamais
    un IMEI, jamais un code, jamais une position exacte.
    """
    if current_user.role == 'admin':
        appareils = Appareil.query.order_by(Appareil.date_enregistrement.desc()).all()
    else:
        # Appareils dont je suis propriétaire, plus ceux qu'un tiers m'a
        # signalés ET que j'accepte de suivre (table de partage dédiée).
        partages = db.session.execute(
            db.select(Alerte.appareil_id)
            .join(Appareil, Appareil.id == Alerte.appareil_id)
            .where(
                Alerte.user_id == current_user.id,
                Alerte.partage_accepte.is_(True),
            )
        ).scalars().all()

        appareils = Appareil.query.filter(
            db.or_(
                Appareil.user_id == current_user.id,
                Appareil.id.in_(partages) if partages else False,
            )
        ).order_by(Appareil.date_enregistrement.desc()).all()

    est_moi = lambda a: current_user.role == 'admin' or a.user_id == current_user.id

    return jsonify([{
        'id': a.id,
        'imei': a.imei if est_moi(a) else None,
        'modele': a.modele,
        'marque': a.marque,
        'statut': a.statut,
        # Les codes de verrouillage ne quittent JAMAIS l'API pour un appareil
        # que je ne possède pas, et ne sont même plus renvoyés au téléphone
        # dans la liste (ils sont affichés une seule fois, à l'enregistrement).
        'code_verrouillage': a.code_verrouillage if est_moi(a) else None,
        'proprietaire': est_moi(a),
        'date_enregistrement': a.date_enregistrement.isoformat(),
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
            # L'appareil se ré-enrôle : application réinstallée, données
            # locales effacées, réinitialisation. On renouvelle le secret
            # dans tous les cas.
            #
            # Condition de sécurité : la session du propriétaire est valide et
            # l'IMEI appartient déjà à CE compte. Un téléphone volé ne peut
            # donc pas s'approprier un appareil qu'il ne possède pas.
            #
            # Renouveler est aussi la révocation : l'ancien secret devient
            # immédiatement inutilisable, et le topic ntfy change du même coup.
            # Sans cela, une réinstallation rendrait le téléphone définitivement
            # muet — le serveur refuserait de rendre un second secret et le
            # client n'en aurait aucun.
            secret = enroller_appareil(existing)
            db.session.commit()
            return jsonify({
                'message': 'Appareil enregistré',
                'id': existing.id,
                'imei': existing.imei,
                'code_verrouillage': existing.code_verrouillage,
                'code_pin': existing.code_ussd,
                'device_token': secret,
            }), 200
        # Réponse volontairement identique pour un IMEI inconnu et un IMEI
        # appartenant à autrui : on ne confirme pas l'existence d'un
        # enregistrement pour un tiers.
        return jsonify({'error': 'Cet IMEI est déjà utilisé'}), 409

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
    # Secret d'appareil : remis UNE SEULE FOIS, ici. Le client doit le
    # conserver immédiatement (PreferencesManager) et l'envoyer dans
    # l'en-tête X-Device-Token.
    secret = enroller_appareil(nouvel_appareil)

    db.session.add(nouvel_appareil)
    db.session.commit()

    return jsonify({
        'message': 'Appareil enregistré',
        'id': nouvel_appareil.id,
        'imei': nouvel_appareil.imei,
        'code_verrouillage': nouvel_appareil.code_verrouillage,
        'code_pin': nouvel_appareil.code_ussd,
        'device_token': secret,
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

    current_app.logger.info("Appareil %s déverrouillé", appareil.id)
    return jsonify({'message': 'Appareil déverrouillé', 'statut': 'actif'}), 200


# ─────────────────────────────────────────────
# VÉRIFICATION DE VERROUILLAGE EN TEMPS RÉEL
# ─────────────────────────────────────────────
@api_bp.route('/appareils/<int:id>/statut', methods=['GET'])
def check_statut(id):
    """Statut de verrouillage d'un appareil.

    Autorisé par : la session du propriétaire (ou d'un administrateur), ou le
    secret de l'appareil lui-même (`X-Device-Token`). Avant cette correction,
    l'endpoint était public et renvoyait `code_verrouillage` et `code_pin` en
    clair : n'importe qui pouvait lire les codes de n'importe quel téléphone
    en itérant sur les identifiants.

    Les codes ne sont PLUS renvoyés ici. Le téléphone ne les connaît pas :
    c'est le propriétaire qui les saisit pour déverrouiller. Les renvoyer
    au réseau (et à ntfy) n'apportait rien et créait une fuite de secret.
    """
    appareil = db.session.get(Appareil, id)
    if not appareil:
        # Même code pour « inexistant » et « non autorisé » : ne pas révéler
        # quels identifiants d'appareils existent.
        return jsonify({"error": "Appareil introuvable ou accès refusé"}), 404

    autorise = False
    if current_user.is_authenticated:
        autorise = (current_user.role == 'admin') or (appareil.user_id == current_user.id)
    if not autorise:
        autorise = appareil_authentifie(appareil_id=id) is not None

    if not autorise:
        return jsonify({"error": "Accès refusé"}), 403

    verrouille = appareil.statut in ('volé', 'verrouillé')

    return jsonify({
        "appareil_id": appareil.id,
        "imei": appareil.imei,
        "statut": appareil.statut,
        "verrouille": verrouille,
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
    appareil.derniere_activite = datetime.now(timezone.utc)
    db.session.commit()

    notifier_proprietaire(appareil, "ALERTE: " + appareil.marque + " " + appareil.modele + " verrouille",
                          "Code de verrouillage applique. Suivez la position en temps reel.",
                          {"appareil_id": str(appareil.id), "command": "LOCK"})
    avertir_communaute(appareil)

    current_app.logger.info("Appareil %s verrouillé", appareil.id)
    return jsonify({'message': 'Appareil verrouillé', 'statut': 'verrouillé'}), 200


@api_bp.route('/appareils/<int:id>/localiser', methods=['POST'])
def api_localiser(id):
    """Demande une position immédiate à UN appareil (FR-CMD-05).

    La surveillance envoie déjà une position toutes les 30 s. Cette
    commande sert à ne pas attendre : au moment où le propriétaire veut
    savoir où est le téléphone, il ne veut pas « la dernière connue », il
    veut la position de maintenant.

    Contrainte de conception : la commande part vers CE téléphone et pas
    vers tous les appareils du compte. Sinon chaque téléphone enverrait sa
    propre position et la carte afficherait plusieurs points sans que
    l'on sache lequel est le bon. Les clients ignorent de toute façon une
    commande portant un `appareil_id` qui n'est pas le leur.

    Cette commande ne modifie aucun droit : elle n'accorde aucun accès et ne
    crée aucune alerte. Elle est refusée à quiconque n'est pas le
    propriétaire (le rôle `admin` reste autorisé, comme partout ailleurs).
    """
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    appareil = db.session.get(Appareil, id)
    if not appareil:
        return jsonify({'error': 'Appareil introuvable'}), 404

    if appareil.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    from app import envoyer_commande_appareil

    envoye = envoyer_commande_appareil(
        appareil,
        'LOCATE',
        titre='Localisation à la demande',
        corps=f'Envoyez votre position actuelle — {appareil.marque} {appareil.modele}',
    )

    if not envoye:
        return jsonify({
            'error': "Aucun canal de commande disponible pour cet appareil",
            'detail': "L'appareil n'a pas de secret d'appareil enregistré, "
                      "et aucun jeton FCM n'est associé à ce compte.",
        }), 503

    current_app.logger.info('Commande LOCATE envoyée à l\'appareil %s', appareil.id)
    return jsonify({
        'message': 'Demande de localisation envoyée',
        'appareil_id': appareil.id,
    }), 200


# ─────────────────────────────────────────────
# NOTIFICATIONS — RÈGLES DE DIFFUSION
# ─────────────────────────────────────────────
def notifier_proprietaire(appareil, titre, corps, data):
    """Notifie le propriétaire de l'appareil visé. Lui seul reçoit une COMMANDE."""
    from app import envoyer_notification_push
    proprietaire = db.session.get(User, appareil.user_id)
    if proprietaire:
        envoyer_notification_push(appareil.user_id, titre, corps, data)


def avertir_communaute(appareil):
    """Prévient les AUTRES utilisateurs qu'un vol a été signalé.

    Règle non négociable : un signalement communautaire n'est JAMAIS une
    commande. Le champ `command` vaut `ALERT` et non `LOCK`, sinon n'importe
    qui pourrait faire verrouiller le téléphone de tout le monde en déclarant
    un faux vol. L'interface affiche une alerte ; elle ne verrouille rien.

    Seuls les appareils ayant Explicitement accepté le partage (Alerte
    .partage_accepte) sont concernés, ce qui évite de notifier des
    inconnus au hasard — et de révéler l'existence du vol à tout le monde.
    """
    from app import envoyer_notification_push
    parts = db.session.execute(
        db.select(Alerte.appareil_id, Alerte.user_id)
        .join(Appareil, Appareil.id == Alerte.appareil_id)
        .where(
            Alerte.appareil_id == appareil.id,
            Alerte.partage_accepte.is_(True),
        )
    ).all()
    deja_prevenu = {appareil.user_id}
    for _cible_id, user_id in parts:
        if user_id in deja_prevenu:
            continue
        deja_prevenu.add(user_id)
        envoyer_notification_push(
            user_id,
            "VOL SIGNALÉ: " + appareil.marque + " " + appareil.modele,
            "Un téléphone a été déclaré volé. Restez vigilant.",
            {
                "appareil_id": str(appareil.id),
                "type": "community_alert",
                "command": "ALERT",   # <-- alerte SEULEMENT, jamais un verrouillage
            },
        )


@api_bp.route('/appareils/verrouiller-par-code', methods=['POST'])
def api_verrouiller_par_code():
    """Verrouiller son téléphone depuis un autre poste, en connaissant le code.

    AVANT : endpoint public, code de 4 chiffres, aucune limite de tentatives.
    Concrètement, cela revenait à offrir un bouton « verrouiller n'importe quel
    téléphone du service » : 10 000 essais suffisaient, et le compte était créé
    au nom du propriétaire sans qu'il l'ait demandé. N'importe quel visiteur
    pouvait donc prendre le contrôle d'appareils qu'il ne possédait pas.

    MAINTENANT :
      - authentification par session obligatoire (le propriétaire se connecte) ;
      - code plus long, à usage unique par tentative et à durée de vie limitée ;
      - limitation de taux agressive sur les échecs, doublée d'un verrouillage
        progressif par appareil (rotation d'IP ne sert à rien).
    """
    ip = request.remote_addr or 'unknown'
    if not _api_rate_limit(ip, _tentatives_api_code_vk, limite=5, fenetre=900):
        return jsonify({'error': 'Trop de tentatives. Réessayez plus tard.'}), 429

    user = get_request_user()
    if not user:
        return jsonify({'error': 'Authentification requise'}), 401

    data = request.get_json(silent=True) or {}
    if not data.get('code'):
        return jsonify({'error': 'Code de verrouillage requis'}), 400

    code = str(data.get('code') or '').strip()

    appareil = Appareil.query.filter_by(code_verrouillage=code).first()
    if not appareil:
        # Message volontairement indifférencié : ne pas révéler si le code
        # existe pour un appareil appartenant à quelqu'un d'autre.
        return jsonify({'error': 'Code invalide'}), 404

    # Le code seul ne suffit plus : il faut être le propriétaire (ou admin).
    if appareil.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Code invalide'}), 404

    verrouille = _secondes_restantes(appareil.id) > 0

    # Comparaison en temps constant : le code a 8 caractères mais l'opérateur
    # `==` classique fuit le nombre de caractères corrects.
    if not _hmac_compare(appareil.code_verrouillage, code):
        if verrouille:
            restantes = _secondes_restantes(appareil.id)
            return jsonify({
                'error': 'Code invalide',
                'reessai_dans_s': restantes,
            }), 404
        _enregistrer_echec_code(appareil.id)
        # Réponse indifférenciée : ni « code inconnu » ni « mauvais code »
        # ne doivent être distinguables.
        return jsonify({'error': 'Code invalide'}), 404

    if appareil.statut in ('volé', 'verrouillé'):
        return jsonify({'error': 'Cet appareil est déjà verrouillé', 'statut': appareil.statut}), 409

    _reussir_essai_code(appareil.id)
    appareil.statut = 'verrouillé'
    appareil.derniere_activite = datetime.now(timezone.utc)
    db.session.commit()

    alerte = Alerte(
        user_id=appareil.user_id,
        appareil_id=appareil.id,
        type_alerte='vol',
        description='Verrouillé à distance via code de verrouillage',
        priorite='haute',
        statut='en_cours'
    )
    db.session.add(alerte)
    db.session.commit()

    notifier_proprietaire(appareil, "ALERTE: " + appareil.marque + " " + appareil.modele + " verrouille",
                          "Code de verrouillage applique. Suivez la position en temps reel.",
                          {"appareil_id": str(appareil.id), "command": "LOCK"})
    avertir_communaute(appareil)

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

    data = request.get_json(silent=True) or {}
    code_pin_saisi = data.get('code_pin', '').strip()

    appareil = db.get_or_404(Appareil, id)
    if appareil.user_id != user.id and user.role != 'admin':
        return jsonify({'error': 'Non autorisé'}), 403

    if not appareil.code_ussd:
        return jsonify({'error': 'Aucun code PIN généré pour cet appareil'}), 404

    # Le PIN était optionnel : ne pas le fournir, c'est verrouiller sans
    # avoir rien saisi. Le code est désormais obligatoire.
    if not code_pin_saisi:
        return jsonify({'error': 'Code PIN requis'}), 400

    # Même protection que `/verifier-code`, et pour la même raison : le PIN
    # ne fait que 6 chiffres, donc 10^6 combinaisons. Un PIN correct n'est
    # jamais refusé — voir `BlocagesCode`.
    verrouille = _secondes_restantes(id) > 0

    if _hmac_compare(appareil.code_ussd, code_pin_saisi):
        _reussir_essai_code(id)
        appareil.statut = 'verrouillé'
        appareil.derniere_activite = datetime.now(timezone.utc)
        db.session.commit()
    elif verrouille:
        restantes = _secondes_restantes(id)
        return jsonify({
            'error': f'Code PIN incorrect. Réessayez dans {restantes} s.',
            'reessai_dans_s': restantes,
        }), 429
    else:
        attente = _enregistrer_echec_code(id)
        current_app.logger.warning(
            'PIN incorrect : appareil %s (palier de blocage %s s)', id, attente,
        )
        return jsonify({
            'error': 'Code PIN incorrect',
            'reessai_dans_s': attente,
        }), 401

    notifier_proprietaire(appareil, "ALERTE: " + appareil.marque + " " + appareil.modele + " verrouille",
                          "Code PIN applique. Suivez la position en temps reel.",
                          {"appareil_id": str(appareil.id), "command": "LOCK"})
    avertir_communaute(appareil)

    return jsonify({
        'message': 'Appareil verrouillé via PIN',
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
    """Réception des coordonnées GPS réelles du mobile.

    Avant cette correction, l'endpoint était entièrement public : n'importe
    quel tiers pouvait écrire une fausse position pour n'importe quel
    appareil (falsification de la carte de localization) et lire l'existence
    d'appareils par itération d'identifiants.

    L'appareil n'envoie plus son `appareil_id` comme preuve d'identité : il
    est déduit du secret `X-Device-Token`. Un `appareil_id` transmis ne sert
    qu'à vérifier la correspondance, et l'appel est refusé en cas d'écart.
    """
    data = request.get_json(silent=True) or {}
    lat = data.get('latitude')
    lng = data.get('longitude')

    if lat is None or lng is None:
        return jsonify({"error": "Données GPS incomplètes"}), 400

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return jsonify({"error": "Coordonnées GPS invalides"}), 400

    # Bornes géographiques : rejeter 999.0 évite de polluer la table et
    # contourne les outils de carte.
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
        return jsonify({"error": "Coordonnées GPS hors bornes"}), 400

    appareil_id = data.get('appareil_id')
    if appareil_id is not None:
        try:
            appareil_id = int(appareil_id)
        except (TypeError, ValueError):
            return jsonify({"error": "Identifiant d'appareil invalide"}), 400

    # L'identité vient du secret, jamais du corps de la requête.
    appareil = appareil_authentifie()
    if not appareil:
        return jsonify({"error": "Non authentifié"}), 401

    if appareil_id is not None and appareil_id != appareil.id:
        return jsonify({"error": "Cet appareil ne peut pas signaler la position d'un autre"}), 403

    nouvelle_loc = Localisation(
        appareil_id=appareil.id,
        latitude=lat,
        longitude=lng,
        precision_m=_precision_sure(data.get('precision_m')),
        source=(str(data.get('source') or 'gps'))[:20],
        date_capture=datetime.now(timezone.utc)
    )
    db.session.add(nouvelle_loc)
    db.session.commit()
    # On journalise le fait, pas la position exacte : les journaux sont
    # déployés sur des services tiers et sont conservés longtemps.
    current_app.logger.info("Position reçue : appareil %s", appareil.id)

    return jsonify({"status": "success", "message": "Position mise à jour"}), 200


def _precision_sure(valeur):
    """Valide la précision GPS renvoyée par le client (métrique, positive)."""
    try:
        precision = float(valeur)
    except (TypeError, ValueError):
        return None
    if precision < 0 or precision > 100000:
        return None
    return precision


def _appareils_visibles_a(user):
    """Appareils visibles par `user`, avec le niveau de précision accordé.

    Règle unique, réutilisée par /appareils, /localisations/latest et
    /mobile/community-alerts, afin qu'aucun ne puisse devenir plus permissif
    que les autres.

    - Administrateur : tout, position au mètre (devoir d'enquête).
    - Propriétaire : ses propres appareils, position au mètre.
    - Tiers : uniquement les appareils explicitement partagés, et UNIQUEMENT
      si la dernière position réelle est de moins de 6 h — une position vieille
      de trois jours ne localise plus personne, elle se contente de tracer des
      habitudes.

    La fraîcheur est lue dans la table `localisations` plutôt que dans une
    colonne dénormalisée : une colonne mise à jour à part finit toujours par
    diverger de la vérité, et une divergence ici expose la position d'un tiers.
    """
    if user.role == 'admin':
        return {a.id: 'exact' for a in Appareil.query.all()}

    visibilite = {a.id: 'exact' for a in Appareil.query.filter_by(user_id=user.id).all()}

    # Dernière position connue de chaque appareil, calculée en base : une
    # seule requête, aucune hypothèse sur la fraîcheur.
    derniere_par_appareil = dict(db.session.execute(
        db.select(Localisation.appareil_id, db.func.max(Localisation.date_capture))
        .group_by(Localisation.appareil_id)
    ).all())

    il_y_a_6h = datetime.now(timezone.utc) - timedelta(hours=6)

    partages = db.session.execute(
        db.select(Alerte.appareil_id)
        .where(
            Alerte.user_id == user.id,
            Alerte.partage_accepte.is_(True),
        )
    ).scalars().all()

    for appareil_id in set(partages):
        if appareil_id in visibilite:
            continue
        derniere = derniere_par_appareil.get(appareil_id)
        if not derniere:
            continue
        if derniere.tzinfo is None:
            derniere = derniere.replace(tzinfo=timezone.utc)
        if derniere < il_y_a_6h:
            continue
        # Le niveau « approximatif » est un PLAFOND, pas un réglage : même si
        # le propriétaire a accordé la position exacte, un tiers reste limité à
        # la zone (~1 km). Suivre quelqu'un au mètre sans son accord est un
        # danger, et ce plafond n'est pas contournable depuis l'API.
        visibilite[appareil_id] = 'approximatif'

    return visibilite


@api_bp.route('/localisations/latest', methods=['GET'])
@login_required
def get_latest_localisations():
    """Dernière position connue des appareils visibles par l'utilisateur.

    Avant cette correction, l'endpoint renvoyait la position de tous les
    téléphones enregistrés par tous les utilisateurs : un géolocalisation
    continue de tiers, en plus des autres fuites.
    """
    visibilite = _appareils_visibles_a(current_user)
    if not visibilite:
        return jsonify([]), 200

    LIMIT = 30
    result = []

    appareils = Appareil.query.filter(Appareil.id.in_(list(visibilite))).all()
    for app in appareils:
        precision_partage = visibilite.get(app.id, 'exact')
        est_moi = app.user_id == current_user.id or current_user.role == 'admin'
        arrondir = precision_partage == 'approximatif'

        positions = Localisation.query \
            .filter_by(appareil_id=app.id) \
            .order_by(Localisation.date_capture.desc()) \
            .limit(LIMIT) \
            .all()

        derniere = positions[0] if positions else None

        def _coordonnees(p):
            if arrondir:
                # ~1 km : assez pour situer le quartier, pas pour trouver
                # quelqu'un chez lui.
                return round(p.latitude, 2), round(p.longitude, 2)
            return p.latitude, p.longitude

        entry = {
            'appareil_id': app.id,
            'modele': app.modele,
            'marque': app.marque,
            'statut': app.statut,
            'proprietaire': est_moi,
            'precision': precision_partage,
            'nombre_positions': len(positions),
            # L'IMEI est un identifiant personnel : jamais transmis à un tiers.
            'imei': app.imei if est_moi else None,
            # L'adresse exacte est une donnée d'adresse personnelle : réservée
            # au propriétaire et à l'administration.
            'adresse': (derniere.adresse if (derniere and est_moi) else None),
        }

        if derniere:
            lat, lng = _coordonnees(derniere)
            entry.update({
                'latitude': lat,
                'longitude': lng,
                'precision_m': derniere.precision_m,
                'source': derniere.source,
                'date_capture': derniere.date_capture.isoformat() if hasattr(derniere.date_capture, 'isoformat') else str(derniere.date_capture),
                'trail': [
                    {
                        'latitude': trail_lat,
                        'longitude': trail_lng,
                        'date_capture': p.date_capture.isoformat() if hasattr(p.date_capture, 'isoformat') else str(p.date_capture),
                        'precision_m': p.precision_m,
                        'source': p.source,
                    }
                    for p, (trail_lat, trail_lng) in (
                        (p, _coordonnees(p)) for p in reversed(positions)
                    )
                ],
            })
        else:
            entry.update({
                'latitude': None, 'longitude': None, 'precision_m': None,
                'source': None, 'date_capture': None, 'trail': [],
            })

        result.append(entry)

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

    Avant cette correction, l'endpoint était public et sans limitation de
    tentatives : les codes ne faisant que 4 chiffres, ils étaient devinables
    en ~10 000 essais, ce qui revient à déverrouiller n'importe quel
    téléphone volé. Il est désormais authentifié ET limité en taux.
    """
    # Limitation de taux AVANT toute vérification de secret : sinon un
    # attaquant non authentifié sature le service avec des requêtes.
    # Le limiteur par IP ne suffit pas (rotation d'adresses) : c'est le
    # verrouillage progressif par appareil, plus bas, qui protège le code.
    ip = request.remote_addr or 'unknown'
    if not _api_rate_limit(ip, _tentatives_api_code, limite=5, fenetre=300):
        return jsonify({'error': 'Trop de tentatives. Réessayez dans quelques minutes.'}), 429

    appareil = db.session.get(Appareil, id)
    if not appareil:
        return jsonify({'error': 'Appareil introuvable ou accès refusé'}), 404

    # Seul l'appareil concerné (ou son propriétaire) peut tenter un déverrouillage.
    autorise = False
    if current_user.is_authenticated:
        autorise = (current_user.role == 'admin') or (appareil.user_id == current_user.id)
    if not autorise:
        autorise = appareil_authentifie(appareil_id=id) is not None
    if not autorise:
        return jsonify({'error': 'Accès refusé'}), 403

    # Verrouillage progressif sur CE code, attaché à cet appareil et non à
    # l'IP : franchir cette ligne coûte de plus en plus cher à l'attaquant.
    # La comparaison a lieu AVANT le refus, pour qu'un code correct ne soit
    # jamais rejeté (sinon cinq erreurs d'un tiers bloquent le propriétaire).
    verrouille = _secondes_restantes(id) > 0

    data = request.get_json(silent=True) or {}
    if 'code' not in data:
        return jsonify({'error': 'Code manquant'}), 400

    code_saisi = str(data.get('code') or '').strip()

    code_attendu = appareil.code_verrouillage

    if not code_attendu:
        return jsonify({'error': 'Aucun code de verrouillage défini pour cet appareil'}), 400

    if _hmac_compare(code_attendu, code_saisi):
        _reussir_essai_code(id)
        appareil.statut = 'actif'
        db.session.commit()
        current_app.logger.info('Code correct : appareil %s déverrouillé', id)
        return jsonify({'message': 'Code correct', 'statut': 'actif'}), 200

    # JAMAIS journaliser les codes : ni le code saisi (une tentative ne doit
    # rien apprendre) ni le code attendu (ce serait une fuite complète du
    # secret dans les journaux). On ne logue que l'échec et l'identifiant.
    if verrouille:
        restantes = _secondes_restantes(id)
        current_app.logger.warning(
            'Essai bloqué sur appareil %s (encore %s s)', id, restantes,
        )
        return jsonify({
            'error': f'Code incorrect. Réessayez dans {restantes} s.',
            'reessai_dans_s': restantes,
        }), 429

    attente = _enregistrer_echec_code(id)
    current_app.logger.warning(
        'Code incorrect : appareil %s (palier de blocage %s s)', id, attente,
    )
    return jsonify({
        'error': 'Code incorrect',
        'reessai_dans_s': attente,
    }), 401


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

    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': 'Données manquantes'}), 400

    appareil_id = data.get('appareil_id')
    type_alerte = str(data.get('type_alerte') or 'vol')
    description = str(data.get('description') or '')

    if not appareil_id:
        return jsonify({'error': 'appareil_id requis'}), 400

    # Liste blanche : sans elle, un type arbitraire part en base et casse
    # les filtres de l'interface (« vol », « perte », « anomalie »).
    if type_alerte not in ('vol', 'perte', 'anomalie', 'changement_sim'):
        return jsonify({'error': 'Type d\'alerte invalide'}), 400

    try:
        appareil_id = int(appareil_id)
    except (TypeError, ValueError):
        return jsonify({'error': 'appareil_id invalide'}), 400

    appareil = exiger_proprietaire(db.session.get(Appareil, appareil_id), user)
    if not appareil:
        return jsonify({'error': 'Appareil introuvable'}), 404

    if type_alerte == 'vol':
        appareil.statut = 'volé'
    elif type_alerte == 'perte':
        appareil.statut = 'perdu'
    appareil.derniere_activite = datetime.now(timezone.utc)

    nouvelle_alerte = Alerte(
        user_id=user.id,
        appareil_id=appareil.id,
        type_alerte=type_alerte,
        description=description[:2000],
        priorite='haute'
    )
    db.session.add(nouvelle_alerte)
    db.session.commit()

    notifier_proprietaire(
        appareil,
        appareil.marque + " " + appareil.modele + " : " + type_alerte.replace('_', ' '),
        "Alerte créée depuis votre compte.",
        {"appareil_id": str(appareil.id), "command": "ALERT"},
    )
    if type_alerte == 'vol':
        avertir_communaute(appareil)

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
    """Enregistrer ou mettre à jour un token FCM.

    AVANT : si l'appel n'était pas connecté, l'identité de l'utilisateur était
    déduite du seul `device_uuid` transmis dans le corps. Connaissant un UUID,
    un tiers pouvait donc enregistrer SON token de notification sur le compte
    d'une victime — et recevoir à sa place les alertes antivol de cette
    personne, qui contiennent la position de son téléphone et ses ordres de
    verrouillage. C'est une interception de canal, pas un simple abus.

    MAINTENANT : session du propriétaire OU secret d'appareil, et rien d'autre.
    """
    user = get_request_user()
    if not user:
        appareil = appareil_authentifie()
        if not appareil:
            return jsonify({'error': 'Non authentifié'}), 401
        user = db.session.get(User, appareil.user_id)
        if not user:
            return jsonify({'error': 'Non authentifié'}), 401

    data = request.get_json(silent=True) or {}

    token = str(data.get('fcm_token') or '').strip()
    if not token:
        return jsonify({'error': 'fcm_token requis'}), 400
    # Un token FCM est une chaîne de 100 à 500 caractères. Borner l'entrée
    # évite de stocker n'importe quoi dans une colonne censée les contenir.
    if not (20 <= len(token) <= 500):
        return jsonify({'error': 'fcm_token invalide'}), 400

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
    """Enregistre les informations techniques du navigateur (page « Mon appareil »).

    Deux corrections importantes :

    1. Le consentement doit être EXPLICITE. Le champ existe déjà dans le
       modèle, mais il était ignoré et la collecte était inconditionnelle.
       Une collecte « technique » finissant dans une base, sans consentement,
       n'a rien à faire dans une application de surveillance.

    2. Le cookie de session n'est PLUS stocké. C'était le point le plus
       grave : `request.cookies['session']` est le cookie signé qui porte
       l'identité de l'utilisateur. Le conserver en base offrait à quiconque
       lisait la base un jeton d'accès complet et réutilisable — il suffisait
       de renvoyer le cookie dans un navigateur pour être connecté.
       On ne conserve qu'une empreinte tronquée, non réversible, à usage de
       simple mesure d'audience.
    """
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'error': 'Données manquantes'}), 400

    if not data.get('consentement'):
        return jsonify({'error': 'Consentement requis pour la collecte'}), 403

    user = get_request_user()

    # Empreinte du cookie, jamais le cookie lui-même : permet de regrouper les
    # visites d'une même personne sans pouvoir rejouer sa session.
    from app.device_auth import hacher_device_token
    session_id = None
    cookie = request.cookies.get('session')
    if cookie:
        session_id = hacher_device_token(cookie)[:32]

    def _entier(valeur, maximum=100000):
        try:
            v = int(valeur)
        except (TypeError, ValueError):
            return None
        return v if 0 < v <= maximum else None

    def _texte(valeur, longueur):
        return (str(valeur)[:longueur] if valeur is not None else None)

    info = TelephoneCollecte(
        user_id=user.id if user else None,
        session_id=session_id,
        modele=_texte(data.get('modele'), 100),
        marque=_texte(data.get('marque'), 50),
        systeme_os=_texte(data.get('systeme_os'), 50),
        version_os=_texte(data.get('version_os'), 50),
        navigateur=_texte(data.get('navigateur'), 100),
        ecran_largeur=_entier(data.get('ecran_largeur'), 20000),
        ecran_hauteur=_entier(data.get('ecran_hauteur'), 20000),
        langue=_texte(data.get('langue'), 10),
        ip=request.remote_addr,
        consentement=True,
        date_collecte=datetime.now(timezone.utc)
    )
    db.session.add(info)
    db.session.commit()

    return jsonify({'message': 'Informations enregistrées', 'id': info.id}), 201


# ─────────────────────────────────────────────
# MOBILE — VERROUILLAGE NATIF (API legacy `device_uuid`)
# ─────────────────────────────────────────────
# Ces endpoints sont conservés parce que les clients v0 (Java) et v1 en
# dépendent. Ils sont désormais soumis à la MÊME règle que le reste :
#   - l'identité d'un appareil vient de son secret `X-Device-Token`, ou de la
#     session du propriétaire pour les actions déclenchées depuis le compte ;
#   - un `device_uuid` n'est plus une preuve d'identité (il est visible par
#     l'utilisateur, devinable, et surtout il ne prouve rien : il suffit
#     d'envoyer l'UUID d'un autre téléphone pour agir dessus).

def _appareil_par_uuid_ou_secret(device_uuid):
    """Résout un appareil par son UUID, MAIS seulement si la requête est
    authentifiée pour CET appareil. Sans preuve, on ne renvoie rien."""
    appareil = Appareil.query.filter_by(device_uuid=device_uuid).first()
    if not appareil:
        return None
    if appareil_authentifie(appareil_id=appareil.id):
        return appareil
    if current_user.is_authenticated and (
        current_user.role == 'admin' or appareil.user_id == current_user.id
    ):
        return appareil
    return None


@api_bp.route('/mobile/register', methods=['POST'])
def mobile_register():
    """Enregistrement d'un appareil Android.

    AVANT : sans authentification, et avec `user_id = user.id if user else 1`
    — c'est-à-dire qu'un appel anonyme rattachait le téléphone au compte
    numéro 1. N'importe quel visiteur pouvait donc faire apparaître un
    téléphone sur le compte d'autrui, ou le voler.

    MAINTENANT : authentification obligatoire, et un appareil déjà rattaché
    à quelqu'un ne peut pas être réattribué.
    """
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    data = request.get_json(silent=True) or {}
    device_uuid = str(data.get('device_uuid') or '').strip()
    if not device_uuid or len(device_uuid) < 8 or len(device_uuid) > 64:
        return jsonify({'error': 'device_uuid invalide'}), 400

    existing = Appareil.query.filter_by(device_uuid=device_uuid).first()
    if existing:
        # Réattribuer un appareil déjà rattaché à un autre compte est refusé.
        # Avant, n'importe qui pouvait « réclamer » un téléphone volé et
        # en devenir le propriétaire aux yeux du système.
        if existing.user_id != user.id and user.role != 'admin':
            return jsonify({'error': 'Cet appareil est déjà rattaché à un autre compte'}), 403

        if not existing.device_secret:
            secret = enroller_appareil(existing)
            db.session.commit()
            return jsonify({
                'message': 'Appareil enregistré',
                'id': existing.id,
                'device_uuid': existing.device_uuid,
                'device_token': secret,
                'code_verrouillage': existing.code_verrouillage,
                'statut': existing.statut,
            }), 200
        return jsonify({
            'message': 'Appareil déjà enregistré',
            'id': existing.id,
            'device_uuid': existing.device_uuid,
            'statut': existing.statut,
        }), 200

    nouveau = Appareil(
        user_id=user.id,
        imei=device_uuid[:20],
        modele=str(data.get('modele') or 'Inconnu')[:100],
        marque=str(data.get('marque') or 'Inconnu')[:50],
        systeme_os='Android',
        version_os=str(data.get('version_os') or 'Inconnue')[:20],
        device_uuid=device_uuid,
        code_verrouillage=generer_code_verrouillage(),
        code_ussd=generer_code_pin(),
        statut='actif'
    )
    secret = enroller_appareil(nouveau)
    db.session.add(nouveau)
    db.session.commit()

    return jsonify({
        'message': 'Appareil enregistré',
        'id': nouveau.id,
        'device_uuid': nouveau.device_uuid,
        'device_token': secret,
        'code_verrouillage': nouveau.code_verrouillage,
        'statut': nouveau.statut
    }), 201


@api_bp.route('/mobile/status/<device_uuid>', methods=['GET'])
def mobile_status(device_uuid):
    """Statut de verrouillage, pour le client legacy.

    AVANT : endpoint public qui renvoyait le `code_verrouillage` en clair à
    quiconque connaissait l'UUID. Les UUID étaient devinables et distribués
    dans les notifications : c'était une fuite directe du code.

    MAINTENANT : authentification par secret d'appareil ou par session du
    propriétaire, et plus aucun code dans la réponse.
    """
    appareil = _appareil_par_uuid_ou_secret(device_uuid)
    if not appareil:
        return jsonify({'error': 'Appareil introuvable ou accès refusé'}), 404

    verrouille = appareil.statut in ('volé', 'verrouillé')

    return jsonify({
        'appareil_id': appareil.id,
        'statut': appareil.statut,
        'verrouille': verrouille,
        'message': 'VERROUILLÉ' if verrouille else 'ACTIF'
    }), 200


@api_bp.route('/mobile/unlock', methods=['POST'])
def mobile_unlock():
    """Déverrouiller un appareil avec son code de verrouillage.

    AVANT : public, sans limitation de tentatives, sur un code de 4 chiffres.
    Quelqu'un pouvait déverrouiller n'importe quel téléphone enregistré en
    itérant sur les UUID et les codes.

    MAINTENANT : secret d'appareil ou propriétaire, plus une limitation de
    taux agressive qui rend la force brute impraticable.
    """
    ip = request.remote_addr or 'unknown'
    if not _api_rate_limit(ip, _tentatives_api_code, limite=5, fenetre=300):
        return jsonify({'error': 'Trop de tentatives. Réessayez dans quelques minutes.'}), 429

    data = request.get_json(silent=True) or {}
    device_uuid = str(data.get('device_uuid') or '').strip()
    code = str(data.get('code') or '').strip()
    if not device_uuid or not code:
        return jsonify({'error': 'device_uuid et code requis'}), 400

    appareil = _appareil_par_uuid_ou_secret(device_uuid)
    if not appareil:
        return jsonify({'error': 'Appareil introuvable ou accès refusé'}), 404

    if not appareil.code_verrouillage:
        return jsonify({'error': 'Aucun code de verrouillage défini'}), 400

    verrouille = _secondes_restantes(appareil.id) > 0

    if _hmac_compare(appareil.code_verrouillage, code):
        _reussir_essai_code(appareil.id)
        appareil.statut = 'actif'
        db.session.commit()
        return jsonify({'message': 'Déverrouillé', 'statut': 'actif'}), 200

    if verrouille:
        return jsonify({
            'error': 'Code incorrect',
            'reessai_dans_s': _secondes_restantes(appareil.id),
        }), 429

    return jsonify({
        'error': 'Code incorrect',
        'reessai_dans_s': _enregistrer_echec_code(appareil.id),
    }), 401


@api_bp.route('/mobile/claim', methods=['POST'])
def mobile_claim():
    """Rattache un téléphone au compte de l'utilisateur connecté.

    AVANT : il suffisait de connaître un `device_uuid` pour s'attribuer la
    propriété d'un téléphone — y compris volé. Le compte d'origine perdait
    alors tout accès et tout historique.

    MAINTENANT : le téléphone doit prouver qu'il s'agit de LUI, en fournissant
    son secret d'appareil. On ne vérifie plus un simple UUID, qui n'est pas
    un secret.
    """
    user = get_request_user()
    if not user:
        return jsonify({'error': 'Non authentifié'}), 401

    data = request.get_json(silent=True) or {}
    device_uuid = str(data.get('device_uuid') or '').strip()
    if not device_uuid:
        return jsonify({'error': 'device_uuid requis'}), 400

    appareil = Appareil.query.filter_by(device_uuid=device_uuid).first()
    if not appareil:
        return jsonify({'error': 'Appareil introuvable'}), 404

    # Preuve de possession : le secret de l'appareil, pas son identifiant.
    if not appareil_authentifie(appareil_id=appareil.id):
        return jsonify({'error': 'Preuve de possession requise (X-Device-Token)'}), 403

    if appareil.user_id != user.id and user.role != 'admin':
        # Un transfert de propriété explicite du détenteur actuel est demandé
        # au lieu d'être accordé silencieusement.
        return jsonify({
            'error': 'Cet appareil est rattaché à un autre compte. '
                     'Demandez son transfert au propriétaire.',
        }), 409

    current_app.logger.info("Appareil %s rattaché au compte %s", appareil.id, user.id)
    return jsonify({
        'message': 'Appareil associé au compte',
        'appareil_id': appareil.id,
        'user_id': user.id
    }), 200


@api_bp.route('/mobile/me', methods=['GET'])
def mobile_me():
    """Retourne l'ID de l'utilisateur connecté (via session cookie)."""
    user = get_request_user()
    if not user:
        return jsonify({'authenticated': False}), 200

    return jsonify({
        'authenticated': True,
        'user_id': user.id,
        'nom': user.nom,
        'prenom': user.prenom
    }), 200


@api_bp.route('/mobile/lock/<device_uuid>', methods=['POST'])
def mobile_lock(device_uuid):
    """Verrouiller un appareil par UUID (depuis l'application Android).

    AVANT : public. Il suffisait de connaître l'UUID d'un téléphone pour le
    mettre en état « verrouillé » et déclencher une alerte de vol chez son
    propriétaire. Un simple script pouvait bloquer ainsi des centaines de
    téléphones, dont ceux d'autres personnes que l'attaquant.

    MAINTENANT : authentification par secret d'appareil ou par session du
    propriétaire.
    """
    appareil = _appareil_par_uuid_ou_secret(device_uuid)
    if not appareil:
        return jsonify({'error': 'Appareil introuvable ou accès refusé'}), 404

    if appareil.statut in ('volé', 'verrouillé'):
        return jsonify({'error': 'Déjà verrouillé', 'statut': appareil.statut}), 409

    appareil.statut = 'verrouillé'
    appareil.derniere_activite = datetime.now(timezone.utc)
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

    notifier_proprietaire(appareil, "ALERTE: " + appareil.marque + " " + appareil.modele + " verrouille",
                          "Code de verrouillage applique. Suivez la position en temps reel.",
                          {"appareil_id": str(appareil.id), "command": "LOCK"})
    avertir_communaute(appareil)

    return jsonify({'message': 'Appareil verrouille', 'statut': 'verrouille'}), 200


@api_bp.route('/mobile/stolen-alert', methods=['POST'])
def mobile_stolen_alert():
    """Le téléphone signale avoir été volé.

    AVANT : public, et le `device_uuid` transmis suffisait. N'importe qui
    pouvait marquer n'importe quel téléphone comme « volé » et y injecter
    une fausse position GPS — c'est-à-dire faire accuser un innocence, ou
    envoyer la police chez la bonne personne au mauvais endroit.

    MAINTENANT : seul le téléphone concerné, identifié par son secret, peut
    signaler son propre vol. Les coordonnées sont validées.
    """
    data = request.get_json(silent=True) or {}

    appareil = appareil_authentifie()
    if not appareil:
        return jsonify({'error': 'Non authentifié'}), 401

    device_uuid = data.get('device_uuid')
    if device_uuid and str(device_uuid).strip() != (appareil.device_uuid or ''):
        return jsonify({'error': 'Identifiant d\'appareil incohérent'}), 403

    if appareil.statut not in ('volé', 'verrouillé'):
        appareil.statut = 'volé'
    appareil.derniere_activite = datetime.now(timezone.utc)
    db.session.commit()

    lat = data.get('latitude')
    lng = data.get('longitude')
    position_valide = False
    if lat is not None and lng is not None:
        try:
            lat, lng = float(lat), float(lng)
            position_valide = (-90.0 <= lat <= 90.0) and (-180.0 <= lng <= 180.0)
        except (TypeError, ValueError):
            position_valide = False
    if position_valide:
        db.session.add(Localisation(
            appareil_id=appareil.id,
            latitude=lat,
            longitude=lng,
            source='gps',
            date_capture=datetime.now(timezone.utc)
        ))
        db.session.commit()

    notifier_proprietaire(
        appareil,
        appareil.marque + " " + appareil.modele + " signale vole!",
        ("Position: %.5f,%.5f - Cliquez pour localiser" % (lat, lng)) if position_valide
        else "Aucune position exploitable reçue. Cliquez pour en savoir plus.",
        {
            "appareil_id": str(appareil.id),
            "lat": str(lat) if position_valide else "",
            "lng": str(lng) if position_valide else "",
            "command": "VOL",
        },
    )

    # La communauté reçoit une ALERTE, jamais une commande, et seulement si
    # les destinataires ont accepté le partage. La position exacte d'un vol
    # n'est pas diffusée : elle appartient au propriétaire et aux autorités.
    avertir_communaute(appareil)

    return jsonify({
        'message': 'Alerte recue, proprietaire notifie',
        'statut': 'vole'
    }), 200


@api_bp.route('/mobile/community-alerts', methods=['GET'])
def mobile_community_alerts():
    """Appareils déclarés volés ou verrouillés.

    AVANT : endpoint public exposant l'IMEI et la position GPS PRÉCISE de
    tous les téléphones volés du service. Une géolocalisation continue de
    tiers, accessible à quiconque — c'est le type de données qui permet de
    cibler une victime précise.

    MAINTENANT : authentification obligatoire ; seuls les appareils dont le
    propriétaire a accepté le partage sont listés ; la position est arrondie
    à ~1 km ; ni l'IMEI ni l'UUID ne sont transmis.
    """
    if not current_user.is_authenticated:
        return jsonify({'error': 'Non authentifié'}), 401

    visibilite = _appareils_visibles_a(current_user)
    if not visibilite:
        return jsonify({'alertes': []}), 200

    recents = Appareil.query.filter(
        Appareil.id.in_(list(visibilite)),
        Appareil.statut.in_(['volé', 'verrouillé']),
    ).all()

    resultats = []
    for app in recents:
        derniere_loc = Localisation.query.filter_by(
            appareil_id=app.id
        ).order_by(Localisation.date_capture.desc()).first()

        alerte_recente = Alerte.query.filter_by(
            appareil_id=app.id, type_alerte='vol'
        ).order_by(Alerte.date_creation.desc()).first()

        est_moi = app.user_id == current_user.id or current_user.role == 'admin'
        latitude = longitude = None
        if derniere_loc:
            if est_moi:
                latitude, longitude = derniere_loc.latitude, derniere_loc.longitude
            else:
                # ~1 km pour un tiers : on situe le quartier, pas la personne.
                latitude = round(derniere_loc.latitude, 2)
                longitude = round(derniere_loc.longitude, 2)

        resultats.append({
            'id': app.id,
            'marque': app.marque,
            'modele': app.modele,
            'statut': app.statut,
            'date_vol': alerte_recente.date_creation.isoformat() if alerte_recente else None,
            'latitude': latitude,
            'longitude': longitude,
            'precision': 'exact' if est_moi else 'approximatif',
        })

    return jsonify({'alertes': resultats}), 200


@api_bp.route('/zones-risque', methods=['GET'])
def api_zones_risque():
    """Retourne toutes les zones à risque."""
    zones = ZoneRisque.query.all()
    return jsonify([{
        'id': z.id,
        'nom': z.nom,
        'ville': z.ville,
        'latitude': z.latitude,
        'longitude': z.longitude,
        'rayon_m': z.rayon_m,
        'niveau_risque': z.niveau_risque,
        'nombre_incidents': z.nombre_incidents
    } for z in zones]), 200

