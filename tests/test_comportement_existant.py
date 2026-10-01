"""Tests de caractérisation — ils décrivent le comportement ACTUEL de l'existant.

Objectif : garantir qu'aucune correction ultérieure ne casse une fonctionnalité
déjà réalisée. Ils doivent être lus comme une spécification rétrospective.

Toute modification intentionnelle du comportement doit être accompagnée d'un
nouveau test explicite, et ce fichier doit rester vert.
"""

import pytest


# ─────────────────────────── Application et cycle de vie ───────────────────────────

def test_create_app_expose_toutes_les_blueprints(app):
    blueprints = set(app.blueprints)
    assert {'auth', 'dashboard', 'api'} <= blueprints


def test_accueil_public_sert_la_page_welcome(client):
    r = client.get('/')
    assert r.status_code == 200
    assert b'<html' in r.data.lower()


def test_pages_publiques_accessibles_sans_session(client):
    for url in ('/login', '/register', '/reset-password', '/download'):
        assert client.get(url).status_code == 200, url


def test_pages_privees_redirigent_vers_login(client):
    for url in ('/dashboard', '/appareils', '/alertes', '/carte', '/profil'):
        r = client.get(url)
        assert r.status_code in (301, 302), url
        assert '/login' in r.headers.get('Location', ''), url


def test_page_404_servie_pour_url_inconnue(client):
    r = client.get('/route-inexistante-xyz')
    assert r.status_code == 404


# ─────────────────────────────── Authentification ───────────────────────────────

def test_inscription_web_cree_un_compte(client, db, anti_bot):
    from app.models import User
    r = client.post('/register', data={
        'nom': 'Aya', 'prenom': 'Kone', 'email': 'aya@test.ci',
        'telephone': '+225 07 11 22 33', 'password': 'secret123',
        'confirm_password': 'secret123', 'website': '',
        **anti_bot(),
    }, follow_redirects=False)
    assert r.status_code in (200, 302)
    assert User.query.filter_by(email='aya@test.ci').first() is not None


def test_mot_de_passe_stocke_hache_et_non_en_clair(client, db, anti_bot):
    from app.models import User
    from app import bcrypt
    client.post('/register', data={
        'nom': 'Aya', 'prenom': 'Kone', 'email': 'hachage@test.ci',
        'telephone': '+225 07 11 22 33', 'password': 'secret123',
        'confirm_password': 'secret123', 'website': '', **anti_bot(),
    })
    u = User.query.filter_by(email='hachage@test.ci').first()
    assert u is not None
    hachage = u.password_hash
    if isinstance(hachage, bytes):
        hachage = hachage.decode()
    assert 'secret123' not in hachage
    assert bcrypt.check_password_hash(u.password_hash, 'secret123')


def test_utilisateur_ne_peut_pas_agir_sur_appareil_dautrui(client, factory):
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a = factory.appareil(bob, statut='actif')
    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})

    r = client.post(f'/appareils/{a.id}/verrouiller', follow_redirects=False)
    assert r.status_code in (302, 403, 404)
    assert a.statut == 'actif', 'un utilisateur ne doit pas verrouiller un appareil tiers'


def test_api_register_puis_api_login(client, db):
    from app.models import User
    r = client.post('/api/auth/register', json={
        'nom': 'Bakary', 'prenom': 'Diarra', 'email': 'bakary@test.ci',
        'telephone': '+225 05 44 55 66', 'password': 'secret123',
    })
    assert r.status_code == 201, r.get_json()
    assert User.query.filter_by(email='bakary@test.ci').first() is not None

    r = client.get('/api/auth/login', follow_redirects=False)  # méthode non autorisée
    assert r.status_code == 405

    r = client.post('/api/auth/login', json={
        'email': 'bakary@test.ci', 'password': 'secret123',
    })
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['user']['email'] == 'bakary@test.ci'


def test_api_login_refuse_mauvais_mot_de_passe(client, factory):
    u = factory.user(password='bonmotdepasse')
    r = client.post('/api/auth/login', json={
        'email': u.email, 'password': 'mauvais',
    })
    assert r.status_code == 401
    assert 'error' in r.get_json()


# ─────────────────────────── Gestion des appareils ───────────────────────────

def test_ajout_appareil_web_puis_presente_au_dashboard(client, factory):
    u, _ = None, None
    u = factory.user(password='secret123')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post('/appareils/ajouter', data={
        'marque': 'Xiaomi', 'modele': 'Redmi Note 13', 'imei': '351234567890999',
        'systeme_os': 'Android', 'operateur': 'MTN CI', 'numero_telephone': '+225 07 00 00 00',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Redmi Note 13' in r.data

    from app.models import Appareil
    a = Appareil.query.filter_by(imei='351234567890999').first()
    assert a is not None
    # Les deux codes sont générés automatiquement.
    assert a.code_verrouillage and len(a.code_verrouillage) == 8
    assert a.code_ussd and len(a.code_ussd) == 6


def test_imei_duplique_refuse(client, factory):
    from app.models import Appareil
    u = factory.user(password='secret123')
    a = factory.appareil(u, imei='351111111111111')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post('/appareils/ajouter', data={
        'marque': 'X', 'modele': 'Y', 'imei': a.imei,
    }, follow_redirects=True)
    assert r.status_code == 200
    # Une seule ligne pour cet IMEI.
    assert Appareil.query.filter_by(imei=a.imei).count() == 1


def test_api_appareils_register_retourne_les_codes(client, factory):
    u = factory.user(password='secret123')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})
    r = client.post('/api/appareils/register', json={
        'imei': '352222222222222', 'modele': 'Pixel 8', 'marque': 'Google',
    })
    assert r.status_code == 201, r.get_json()
    data = r.get_json()
    assert data['id']
    # 8 caractères : 4 chiffres ne donnaient que 10 000 codes, donc
    # déverrouillables par force brute sur un endpoint public.
    assert len(data['code_verrouillage']) == 8
    assert len(data['code_pin']) == 6
    assert 'code_pin' in data   # clé attendue par le client v0/WebView
    # Le secret d'appareil est remis une seule fois, à l'enregistrement.
    assert data['device_token']


def test_secret_appareil_est_stocke_pour_pouvoir_signer_les_commandes(client, factory):
    """Le secret d'appareil est stocké en clair : voir app/device_auth.py.

    C'est un choix assumé (le serveur doit pouvoir re-signer les messages
    ntfy), encadré par trois propriétés : haute entropie, révocable, et
    strictement limité aux appels D'APPAREIL — il ne donne jamais accès à
    une session de compte.
    """
    from app.models import Appareil
    u = factory.user(password='secret123')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})
    r = client.post('/api/appareils/register', json={
        'imei': '353333333333333', 'modele': 'Pixel 8', 'marque': 'Google',
    })
    secret = r.get_json()['device_token']
    a = Appareil.query.filter_by(imei='353333333333333').first()
    assert a.device_secret == secret
    # Haute entropie : 32 octets en base64url, jamais 4 chiffres.
    assert len(secret) >= 40


# ───────────────────────────── Géolocalisation ─────────────────────────────
# Le téléphone s'authentifie avec son PROPRE secret (X-Device-Token), pas avec
# une session ni avec un user_id : c'est lui qui signale SA position.

def test_api_localisation_update_stocke_une_position(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u, secret_connu='secret-appareil-1')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post('/api/localisation/update', headers={'X-Device-Token': 'secret-appareil-1'}, json={
        'appareil_id': a.id, 'latitude': 5.33, 'longitude': -4.07,
        'precision_m': 12.5, 'source': 'gps',
    })
    assert r.status_code == 200
    from app.models import Localisation
    assert Localisation.query.filter_by(appareil_id=a.id).count() == 1


def test_api_localisation_sans_secret_refusee(client, factory):
    """Sans secret d'appareil, aucune position n'est acceptée.

    Avant la correction, cet endpoint était public : n'importe qui pouvait
    injecter une fausse position pour n'importe quel appareil.
    """
    u = factory.user(password='secret123')
    a = factory.appareil(u)
    r = client.post('/api/localisation/update', json={
        'appareil_id': a.id, 'latitude': 5.33, 'longitude': -4.07,
    })
    assert r.status_code == 401
    from app.models import Localisation
    assert Localisation.query.count() == 0


def test_api_localisation_ignore_le_user_id_du_client(client, factory):
    """Un user_id dans le corps JSON ne vaut pas authentification."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, secret_connu='secret-appareil-1')
    r = client.post('/api/localisation/update', json={
        'user_id': u.id, 'appareil_id': a.id,
        'latitude': 5.33, 'longitude': -4.07,
    })
    assert r.status_code == 401
    from app.models import Localisation
    assert Localisation.query.count() == 0


def test_api_localisation_refusee_pour_un_autre_appareil(client, factory):
    """Un appareil authentifié ne peut pas signaler la position d'un tiers."""
    u = factory.user(password='secret123')
    mien = factory.appareil(u, secret_connu='secret-mien')
    autre = factory.appareil(u, secret_connu='secret-autre')

    r = client.post('/api/localisation/update', headers={'X-Device-Token': 'secret-mien'}, json={
        'appareil_id': autre.id, 'latitude': 5.33, 'longitude': -4.07,
    })
    assert r.status_code == 403
    from app.models import Localisation
    assert Localisation.query.count() == 0


def test_localisation_incoherente_refusee(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u, secret_connu='secret-appareil-1')
    r = client.post('/api/localisation/update', headers={'X-Device-Token': 'secret-appareil-1'}, json={
        'appareil_id': a.id, 'latitude': 5.33,
    })
    assert r.status_code == 400


def test_localisation_hors_bornes_refusee(client, factory):
    """999 n'est pas une latitude : on ne pollue pas la base avec du bruit."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, secret_connu='secret-appareil-1')
    r = client.post('/api/localisation/update', headers={'X-Device-Token': 'secret-appareil-1'}, json={
        'appareil_id': a.id, 'latitude': 999, 'longitude': -4.07,
    })
    assert r.status_code == 400


# ─────────────────────────────── Alertes ───────────────────────────────

def test_api_alertes_signaler_cree_une_alerte(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u)
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post('/api/alertes/signaler', json={
        'appareil_id': a.id, 'type_alerte': 'vol', 'description': 'Vol au marché',
    })
    assert r.status_code in (200, 201), r.get_json()
    from app.models import Alerte
    assert Alerte.query.filter_by(appareil_id=a.id, type_alerte='vol').count() == 1


def test_api_alertes_resoudre_passe_en_traite(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u)
    alerte = factory.alerte(u, a)
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post(f'/api/alertes/{alerte.id}/resoudre', json={'user_id': u.id})
    assert r.status_code == 200, r.get_json()
    assert alerte.statut == 'traité'


# ───────────────────── Verrouillage / déverrouillage (web) ─────────────────────

def test_web_verrouiller_puis_deverrouiller_un_appareil(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u, statut='actif')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post(f'/appareils/{a.id}/verrouiller', follow_redirects=True)
    assert r.status_code == 200
    assert a.statut == 'verrouillé'

    r = client.post(f'/appareils/{a.id}/deverrouiller', follow_redirects=True)
    assert r.status_code == 200
    assert a.statut == 'actif'


def test_admin_peut_agir_sur_appareil_dautrui(client, factory):
    admin = factory.admin(password='secret123')
    u = factory.user(password='secret123')
    a = factory.appareil(u, statut='actif')
    client.post('/api/auth/login', json={'email': admin.email, 'password': 'secret123'})

    r = client.post(f'/appareils/{a.id}/verrouiller', follow_redirects=True)
    assert r.status_code == 200
    assert a.statut == 'verrouillé'


# ───────────────────────────── Suppression / admin ─────────────────────────────

def test_page_admin_reservee_au_role_admin(client, factory):
    u = factory.user(password='secret123')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})
    r = client.get('/admin')
    assert r.status_code in (301, 302)
    assert '/dashboard' in r.headers.get('Location', '')


def test_admin_accede_a_la_page_admin(client, factory):
    admin = factory.admin(password='secret123')
    client.post('/api/auth/login', json={'email': admin.email, 'password': 'secret123'})
    r = client.get('/admin')
    assert r.status_code == 200


def test_admin_ne_peut_pas_supprimer_son_propre_compte(client, factory):
    admin = factory.admin(password='secret123')
    client.post('/api/auth/login', json={'email': admin.email, 'password': 'secret123'})
    r = client.post(f'/admin/utilisateurs/{admin.id}/supprimer', follow_redirects=True)
    assert r.status_code == 200
    from app.models import User
    assert User.query.get(admin.id) is not None


# ───────────────────────────── Commande de localisation (FR-CMD-05) ─────────────────────────────
# Demande d'une position immédiate à UN téléphone. Sans elle, le propriétaire
# n'a que la dernière position connue, envoyée toutes les 30 s.

def test_localiser_exige_une_session(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u)

    r = client.post(f'/api/appareils/{a.id}/localiser')
    assert r.status_code == 401


def test_localiser_refuse_le_telephone_de_tiers(client, factory):
    """Demander la position d'un téléphone qui n'est pas le sien reviendrait à
    suivre un tiers sans son accord."""
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_bob = factory.appareil(bob)

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.post(f'/api/appareils/{a_bob.id}/localiser')
    assert r.status_code == 403


def test_localiser_envoie_une_commande_ciblee(client, factory, monkeypatch):
    """La commande doit viser CE téléphone et porter l'action `locate`.

    Deux raisons, vérifiées ici :
    - l'`appareil_id` permet aux autres téléphones du compte d'ignorer
      l'ordre au lieu d'envoyer eux aussi leur position ;
    - l'action canonique `locate` est ce que le client sait traduire.
    """
    u = factory.user(password='secret123')
    a = factory.appareil(u, secret_connu='secret-appareil-locate')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    captes = []

    def _fake(appareil, commande, titre=None, corps=None):
        captes.append((appareil.id, commande))
        return True

    monkeypatch.setattr('app.envoyer_commande_appareil', _fake)

    r = client.post(f'/api/appareils/{a.id}/localiser')
    assert r.status_code == 200, r.get_json()
    assert captes == [(a.id, 'LOCATE')]


def test_localiser_signale_l_absence_de_canal(client, factory, monkeypatch):
    """Sans secret d'appareil ni jeton FCM, le téléphone ne peut rien recevoir.

    Répondre 200 « envoyé » serait un mensonge : le propriétaire attendrait
    une position qui n'arrivera jamais.
    """
    u = factory.user(password='secret123')
    a = factory.appareil(u)
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    monkeypatch.setattr('app.envoyer_commande_appareil', lambda *a, **k: False)

    r = client.post(f'/api/appareils/{a.id}/localiser')
    assert r.status_code == 503
    assert 'error' in r.get_json()


def test_localiser_ne_cree_aucune_alerte(client, factory, monkeypatch):
    """Demander une position n'est pas signaler un vol : le statut du
    téléphone et la liste des alertes doivent rester inchangés."""
    from app.models import Alerte, Appareil

    u = factory.user(password='secret123')
    a = factory.appareil(u, statut='actif')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    monkeypatch.setattr('app.envoyer_commande_appareil', lambda *a, **k: True)

    client.post(f'/api/appareils/{a.id}/localiser')

    assert Appareil.query.get(a.id).statut == 'actif'
    assert Alerte.query.count() == 0


def test_locate_est_bien_une_commande_data_only():
    """Une commande envoyée en mode `notification` est perdue en arrière-plan.

    Depuis Android 10, un message FCM de type `notification` est affiché par
    le système sans réveiller l'application : le téléphone n'exécute alors
    jamais la commande. C'est pour cela que lock, unlock ET locate doivent
    partir en `data-only`.
    """
    from app import _ACTIONS_DATA_ONLY, _COMMANDES_ACTIONS

    assert 'locate' in _ACTIONS_DATA_ONLY, \
        'locate partirait en mode notification et serait ignorée en arrière-plan'
    assert _COMMANDES_ACTIONS['LOCATE'] == 'locate'
    assert _COMMANDES_ACTIONS['LOCALISER'] == 'locate'


def test_le_serveur_et_le_client_reconnaissent_les_memes_commandes():
    """Le serveur envoie des alias, le client les traduit.

    Si le serveur envoie un alias que le client ignore, la commande est
    perdue sans le moindre message d'erreur : le téléphone ne fait rien et
    le propriétaire croit avoir verrouillé. Les deux tables doivent donc
    rester alignées.
    """
    import re

    from app import _COMMANDES_ACTIONS

    source = open(
        'app/antivol-mobile-v2/app/src/main/java/com/antivol/mobile/service/CommandeHandler.kt',
        encoding='utf-8',
    ).read()

    # On isole le bloc COMMANDES = mapOf(...) du client.
    bloc = re.search(r'val COMMANDES = mapOf\((.*?)\n    \)', source, re.S)
    assert bloc, 'table COMMANDES introuvable dans CommandeHandler.kt'

    alias_client = set(re.findall(r'"([A-Z_]+)"\s+to\s+ACTION_', bloc.group(1)))
    alias_serveur = set(_COMMANDES_ACTIONS)

    # Le client connaît en plus COMMUNITY_ALERT, que le serveur n'émet pas
    # comme commande mais comme marqueur d'alerte communautaire.
    assert alias_serveur <= alias_client, \
        f'commandes émises par le serveur mais inconnues du client : {alias_serveur - alias_client}'
    assert 'COMMUNITY_ALERT' in alias_client


# ─────────────────────────────── Zones à risque ───────────────────────────────

def test_api_zones_risque_est_publique(client):
    r = client.get('/api/zones-risque')
    assert r.status_code == 200
    assert isinstance(r.get_json(), list)


# ─────────────────────────────── Internationalisation ───────────────────────────────

def test_changement_de_langue_puis_page_suivie(client):
    r = client.get('/set-language/en', follow_redirects=False)
    assert r.status_code in (200, 302)
    with client.session_transaction() as sess:
        assert sess.get('lang') == 'en'
