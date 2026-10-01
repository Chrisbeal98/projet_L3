"""
Authentification des appels effectués PAR un téléphone.

Deux mécanismes distincts, jamais interchangeables :

1. `utilisateur_authentifie()` — la session Flask-Login. C'est l'identité
   d'une personne (site web ou application mobile après connexion).

2. `appareil_authentifie()` — un secret partagé propre à chaque téléphone,
   transmis dans l'en-tête `X-Device-Token`. C'est l'identité d'un
   *appareil*, et elle est indispensable pour les appels que le téléphone
   effectue pour lui-même : lire son statut, transmettre sa position,
   vérifier le code de déverrouillage.

Pourquoi un secret par appareil ?
Les appels d'appareil doivent continuer à fonctionner quand le téléphone est
seul (verrouillé au fond d'une poche, propriétaire absent) et sans dépendre
d'une session navigateur qui peut expirer. En revanche, la session ne doit
PAS suffire pour un appareil : n'importe qui peut se connecter avec le compte
du propriétaire depuis un autre téléphone.

POURQUOI LE SECRET EST EN CLAIR EN BASE
---------------------------------------
Il serait normalement hachable — sauf que le serveur doit aussi SIGNER les
messages ntfy envoyés au téléphone (voir `app/commandes.py`), et qu'une
empreinte SHA-256 est à sens unique : une fois l'appareil enregistré, il
serait impossible de produire un message valide.

C'est la même situation qu'un jeton d'API applicative, ou que les jetons FCM
déjà conservés en clair dans cette base. Le secret est donc :
  - à haute entropie (32 octets, `secrets.token_urlsafe`) ;
  - révocable instantanément (le renouveler suffit) ;
  - strictement limité aux appels D'APPAREIL — il ne donne jamais accès à une
    session de compte, donc pas au changement d'e-mail ni à la suppression.
Un secret volé en base ne vole pas un compte ; il permet, au pire, de faire
passer un attaquant pour un téléphone qu'il n'est pas.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import request
from flask_login import current_user

# Fenêtre au-delà de laquelle un appareil qui s'est manifesté depuis trop
# longtemps n'est plus considéré comme « vivant » pour l'exécution d'une
# commande à distance (évite d'envoyer un verrou à un téléphone revendu).
ACTIVITE_FRAICHE_MAX = timedelta(days=7)


# ─────────────────────────────────────────────
# GÉNÉRATION ET VÉRIFICATION
# ─────────────────────────────────────────────
def generer_device_token():
    """Nouveau secret d'appareil, en clair, à transmettre une seule fois."""
    return secrets.token_urlsafe(32)


def hacher_device_token(token):
    """Empreinte non réversible d'un secret.

    Utilisée pour les empreintes de session à ne pas stocker, et pour
    comparer deux jetons de façon stable. Ne PAS l'utiliser pour stocker un
    secret d'appareil : cela rendrait la signature ntfy impossible.
    """
    if not token:
        return None
    return hashlib.sha256(token.strip().encode('utf-8')).hexdigest()


def _token_de_requete():
    """Extrait le secret transmis par le téléphone, en-têtes d'abord."""
    token = request.headers.get('X-Device-Token')
    if not token:
        # Repli : corps JSON, pour les clients qui ne savent pas envoyer
        # d'en-têtes. On ne fait PAS confiance à un user_id ici.
        data = request.get_json(silent=True) or {}
        token = data.get('device_token')
    return (token or '').strip() or None


def appareil_authentifie(appareil_id=None, exiger_actif=True):
    """Retourne l'appareil si la requête est porteuse d'un secret valide.

    `appareil_id` : restreint la validation à un appareil donné (sinon le
    secret est cherché partout — utile pour /localisation/update où le
    téléphone ne connaît pas forcément son identifiant).

    `exiger_actif` : si vrai, l'appareil doit s'être manifesté récemment.
    Cela empêche qu'un vieux téléphone vendu continue de recevoir et
    d'exécuter des commandes.
    """
    from app.models import Appareil

    token = _token_de_requete()
    if not token:
        return None

    appareil = Appareil.query.filter_by(device_secret=token).first()
    if not appareil:
        return None
    if appareil_id is not None and appareil.id != appareil_id:
        return None

    # Comparaison en temps constant : même si un attaquant devine juste, le
    # coût ne varie pas et il ne peut pas mesurer une correspondance partielle.
    if not hmac.compare_digest(appareil.device_secret or '', token):
        return None

    if exiger_actif and not appareil_est_actif(appareil):
        return None

    appareil.derniere_activite = datetime.now(timezone.utc)
    return appareil


def appareil_est_actif(appareil):
    """L'appareil s'est-il manifesté assez récemment pour qu'on lui fasse confiance ?"""
    if not appareil or not appareil.derniere_activite:
        return False
    activite = appareil.derniere_activite
    if activite.tzinfo is None:
        activite = activite.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - activite <= ACTIVITE_FRAICHE_MAX


def enroller_appareil(appareil, nouveau_secret=None):
    """Attribue (ou renouvelle) le secret d'un appareil.

    Retourne le secret en clair, à transmettre au client. Renouveler un
    secret invalide immédiatement l'ancien : c'est le mécanisme de révocation
    (le topic ntfy du téléphone change lui aussi, du même coup).
    """
    secret = nouveau_secret or generer_device_token()
    appareil.device_secret = secret
    appareil.derniere_activite = datetime.now(timezone.utc)
    return secret


def oublier_appareil(appareil_id):
    """Invalide le secret d'un appareil (suppression, changement de mains)."""
    from app.models import Appareil
    appareil = Appareil.query.get(appareil_id)
    if appareil:
        appareil.device_secret = None
        appareil.derniere_activite = None


def secret_de(appareil):
    """Secret en clair d'un appareil, pour signer une commande ntfy."""
    return getattr(appareil, 'device_secret', None) or None
