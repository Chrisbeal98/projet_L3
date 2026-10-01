"""
Canal de commande entre le serveur et le téléphone (ntfy).

CONTEXTE — la faille que ce module corrige
------------------------------------------
Le canal ntfy était configuré ainsi :

    topic = "antivol-u" + str(user_id)
    POST  https://ntfy.sh/   {"topic": topic, "command": "LOCK", ...}

ntfy.sh est un service public : n'importe qui peut publier ET s'abonner à
n'importe quel topic dont il connaît le nom. Comme le nom ne contenait que
l'identifiant numérique de l'utilisateur, il était devinable en quelques
requêtes. Deux conséquences immédiates :

  1. INJECTION DE COMMANDE. Un attaquant pouvait publier
     `{"topic": "antivol-u5", "command": "LOCK"}` et faire verrouiller le
     téléphone d'une victime à distance, sans jamais connaître son compte.
  2. INTERCEPTION. Il suffisait de s'abonner à `antivol-u1` pour recevoir
     toutes les alertes d'un utilisateur : y compris sa position GPS.

Il s'y ajoutait un topic global `antivol-community` — un fil public
d'annonces de vols pour tout le service, difficile à justifier et impossible
à restreindre.

CE QUE FAIT CE MODULE
---------------------
1. Un topic par APPAREIL, non devinable. Son nom est dérivé du secret du
   téléphone : `antivol-a` + empreinte du secret. Le téléphone calcule le
   sien lui-même à partir du secret qu'il possède ; personne d'autre ne peut
   le deviner ni l'énumérer.

2. Les messages sont SIGNÉS (HMAC-SHA-256) avec le secret de l'appareil. Même
   si un topic était découvert, un message forgé n'est pas signé
   correctement et le téléphone l'ignore. La signature couvre le contenu
   utile ET l'horodatage, ce qui empêche de rejouer un ancien ordre de
   verrouillage.

3. Aucun topic global. L'information ne circule que vers les appareils
   réellement concernés.

LIMITE ASSUMÉE
--------------
Sans compte ntfy, on ne peut pas poser de jetons d'accès ni restreindre la
lecture au niveau du serveur ntfy : la protection repose donc sur le secret
du topic et la signature, pas sur une autorisation du service. Sur un serveur
ntfy auto-hébergé, définir un `Authorization: Bearer <token>` en plus
(recommandé, voir `.env.example`).
"""

import hashlib
import hmac
import json
import time

# Version du format : permet de faire évoluer la signature sans casser les
# téléphones déjà déployés (un ancien téléphone ignore un format qu'il ne
# connaît pas, au lieu d'exécuter un ordre qu'il ne sait pas authentifier).
VERSION_SIGNATURE = 'v1'

# Fenêtre de tolérance sur l'horodatage. Au-delà, le message est considéré
# comme un rejeu d'un ordre ancien (par exemple un « verrouille » émis le mois
# dernier, rejoué aujourd'hui sur un téléphone récupéré).
TOLERANCE_HORLOGE_S = 300


# ─────────────────────────────────────────────
# TOPIC — non devinable, un par appareil
# ─────────────────────────────────────────────
def topic_pour_secret(secret):
    """Topic ntfy correspondant à un secret d'appareil.

    Le téléphone appelle cette fonction lui-même : il possède le secret, donc
    il peut retrouver son topic sans que le serveur ait à le lui rappeler. Le
    topic ne change pas tant que le secret ne change pas.
    """
    if not secret:
        return None
    empreinte = hashlib.sha256(('antivol-topic:' + secret).encode('utf-8')).hexdigest()
    return 'antivol-a' + empreinte[:32]


def topic_pour_appareil(appareil):
    """Topic ntfy d'un appareil, recalculé depuis son secret.

    Le serveur a le secret en clair (voir `app/device_auth.py` pour le
    pourquoi) : il peut donc toujours retrouver le bon topic, sans cache et
    sans colonne supplémentaire en base.
    """
    from app.device_auth import secret_de
    secret = secret_de(appareil)
    return topic_pour_secret(secret) if secret else None


# ─────────────────────────────────────────────
# SIGNATURE
# ─────────────────────────────────────────────
def _a_signer(secret, donnees):
    """Chaîne canonique signée. L'ordre des clés est fixé pour que le client
    calcule exactement la même chaîne (JSON trié, séparateurs stables)."""
    charge = dict(donnees)
    charge['v'] = VERSION_SIGNATURE
    charge['ts'] = int(charge.get('ts') or 0)
    return json.dumps(charge, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def signer(secret, donnees, horodatage=None):
    """Ajoute `sig` et `ts` à un message. Retourne le message à publier."""
    if not secret:
        return None
    message = dict(donnees)
    message['ts'] = int(horodatage if horodatage is not None else time.time())
    message['v'] = VERSION_SIGNATURE
    signature = hmac.new(
        secret.encode('utf-8'),
        _a_signer(secret, message),
        hashlib.sha256,
    ).hexdigest()
    message['sig'] = signature
    return message


def verifier(secret, message, maintenant=None):
    """Vérifie la signature d'un message reçu par le téléphone.

    Miroir exact de `signer` : c'est ce que l'application Android doit
    reproduire. Les tests vérifient que les deux sides sont d'accord.
    """
    if not secret or not isinstance(message, dict):
        return False
    signature_recue = message.get('sig')
    horodatage = message.get('ts')
    if not signature_recue or not isinstance(horodatage, int):
        return False

    maintenant = maintenant if maintenant is not None else time.time()
    if abs(maintenant - horodatage) > TOLERANCE_HORLOGE_S:
        # Rejeu d'un message ancien.
        return False

    sans_signature = {k: v for k, v in message.items() if k != 'sig'}
    attendu = hmac.new(
        secret.encode('utf-8'),
        _a_signer(secret, sans_signature),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(attendu, signature_recue)
