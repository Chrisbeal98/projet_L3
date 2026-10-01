"""
Tests de NON-régression de sécurité.

Chaque test de ce fichier verrouille une correction précise. Ils échouent si
la faille est réintroduite. Les commentaires « AVANT » décrivent l'état
vulnérable d'origine, afin qu'on puisse vérifier d'un coup d'œil ce que le
test protège.

Ces tests complètent `test_comportement_existant.py` (qui décrit ce que le
système fait) — ici, on décrit ce qu'il ne doit PAS faire.
"""

import pytest


# ══════════════════════════════════════════════════════════════════
# 1. IDENTITÉ — le client ne peut pas choisir qui il est
# ══════════════════════════════════════════════════════════════════

def test_user_id_dans_le_json_ne_donne_pas_la_session(client, factory):
    """AVANT : get_request_user() lisait `user_id` dans le corps JSON.

    Conséquence : n'importe quel client pouvait envoyer l'identifiant d'un
    tiers et agir en son nom. C'était une usurpation d'identité complète.
    """
    victime = factory.user(password='secret123')
    a = factory.appareil(victime)

    r = client.post('/api/appareils/register', json={
        'user_id': victime.id, 'imei': '351111111111111',
    })
    assert r.status_code == 401

    from app.models import Appareil
    assert Appareil.query.filter_by(imei='351111111111111').first() is None


def test_user_id_administrateur_ne_donne_pas_les_privileges_admin(client, factory):
    """Élévation de privilèges : viser un admin via `user_id`."""
    admin = factory.admin(password='secret123')
    a = factory.appareil(admin, statut='actif')

    r = client.post('/api/dashboard/stats', json={'user_id': admin.id})
    assert r.status_code == 401


def test_session_par_requete_ne_fonctionne_pas(client, factory):
    """Un `user_id` absent mais un cookie forgé ne donne rien non plus."""
    r = client.get('/api/dashboard/stats', json={'user_id': 1})
    assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════
# 2. FUITE DE SECRETS — aucun code de verrouillage n'est exposé
# ══════════════════════════════════════════════════════════════════

def test_statut_appareil_ne_renvoie_plus_les_codes(client, factory):
    """AVANT : `/api/appareils/<id>/statut` était public ET renvoyait
    `code_verrouillage` et `code_pin` en clair.

    Conséquence : lecture des codes de n'importe quel téléphone en itérant
    sur les identifiants, puis déverrouillage à distance.
    """
    u = factory.user(password='secret123')
    a = factory.appareil(u)
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.get(f'/api/appareils/{a.id}/statut')
    assert r.status_code == 200
    corps = r.get_json()
    assert 'code_verrouillage' not in corps
    assert 'code_pin' not in corps
    # Le statut utile est bien là : le téléphone peut agir dessus.
    assert corps['verrouille'] is False


def test_statut_appareil_refuse_a_un_tiers(client, factory):
    """Un tiers ne doit même pas voir le statut d'un appareil qui n'est pas
    le sien : le statut « volé » est lui-même une information sensible."""
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a = factory.appareil(bob, statut='volé')

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.get(f'/api/appareils/{a.id}/statut')
    assert r.status_code == 403


def test_statut_appareil_est_accessible_a_son_proprietaire(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u, statut='volé')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})
    r = client.get(f'/api/appareils/{a.id}/statut')
    assert r.status_code == 200
    assert r.get_json()['verrouille'] is True


def test_mobile_status_ne_renvoie_plus_le_code(client, factory):
    """AVANT : `/api/mobile/status/<uuid>` public, code en clair."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, device_uuid='uuid-secret-1234')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.get('/api/mobile/status/uuid-secret-1234')
    assert r.status_code == 200
    assert 'code_verrouillage' not in r.get_json()


def test_les_codes_ne_sont_pas_dans_les_journaux(client, factory, capsys):
    """AVANT : le code saisi ET le code attendu étaient écrits dans les
    journaux en cas d'échec. Les journaux partent chez l'hébergeur et sont
    conservés : c'était une fuite complète du secret."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    client.post(f'/api/appareils/{a.id}/verifier-code', json={'code': 'ZZZZ9999'})

    sortie = capsys.readouterr()
    assert 'ZZZZ9999' not in sortie.out
    assert 'ABCD2345' not in sortie.out


# ══════════════════════════════════════════════════════════════════
# 3. FORCE BRUTE SUR LES CODES
# ══════════════════════════════════════════════════════════════════

def test_verifier_code_refuse_sans_authentification(client, factory):
    """AVANT : endpoint public. 4 chiffres = 10 000 essais."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345', statut='verrouillé')

    r = client.post(f'/api/appareils/{a.id}/verifier-code', json={'code': 'ABCD2345'})
    assert r.status_code == 403

    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'verrouillé', \
        "un appel non authentifié a déverrouillé l'appareil"


def test_verifier_code_est_limite_en_taux(client, factory):
    """Au-delà de la limite, l'endpoint doit répondre 429 et non continuer
    à tester des codes."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    codes = []
    for _ in range(10):
        r = client.post(f'/api/appareils/{a.id}/verifier-code', json={'code': 'FAUX0000'})
        codes.append(r.status_code)

    assert 429 in codes, f"aucune limitation de taux : {codes}"
    assert codes[-1] == 429


def test_verifier_code_accepte_le_proprietaire(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345', statut='verrouillé')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post(f'/api/appareils/{a.id}/verifier-code', json={'code': 'ABCD2345'})
    assert r.status_code == 200
    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'actif'


def test_verrouiller_par_code_exige_une_session(client, factory):
    """AVANT : `/api/appareils/verrouiller-par-code` sans authentification.

    Conséquence : n'importe quel visiteur pouvait verrouiller n'importe quel
    téléphone du service en connaissant son code, et faire partir une alerte
    de vol au nom du propriétaire.
    """
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345', statut='actif')

    r = client.post('/api/appareils/verrouiller-par-code', json={'code': 'ABCD2345'})
    assert r.status_code == 401

    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'actif'


def test_verrouiller_par_code_refuse_le_code_dautrui(client, factory):
    """Même connecté, on ne verrouille pas le téléphone d'un autre avec son
    code — sinon deviner un code suffit à prendre le contrôle d'un tiers."""
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a = factory.appareil(bob, code_verrouillage='ABCD2345', statut='actif')

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.post('/api/appareils/verrouiller-par-code', json={'code': 'ABCD2345'})
    assert r.status_code == 404

    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'actif'


def test_verrouiller_par_code_accepte_le_proprietaire(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345', statut='actif')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post('/api/appareils/verrouiller-par-code', json={'code': 'ABCD2345'})
    assert r.status_code == 200
    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'verrouillé'


# ══════════════════════════════════════════════════════════════════
# 3 bis. VERROUILLAGE PROGRESSIF DES ESSAIS DE CODE
# ══════════════════════════════════════════════════════════════════
# Le limiteur de taux par IP ne suffit pas : il se contourne en changeant
# d'adresse IP (rotation, proxy, VPN, botnet). Le code de verrouillage et le
# PIN restent alors trouvables. Le blocage progressif s'attache à l'APPAREIL
# — c'est-à-dire au secret recherché — et croît à chaque échec.


class _Horloge:
    """Horloge manuelle : évite de dormir deux heures pour tester les paliers."""

    def __init__(self, depart):
        self.t = depart

    def __call__(self):
        return self.t

    def avancer(self, secondes):
        from datetime import timedelta
        self.t = self.t + timedelta(seconds=secondes)


@pytest.fixture
def horloge(app):
    """Remplace l'horloge du verrouillage progressif de l'application."""
    from datetime import datetime
    from app.routes import api

    faux = _Horloge(datetime(2026, 1, 1, 12, 0, 0))
    api._blocages()._horloge = faux
    return faux


def test_le_verrouillage_progressif_resiste_a_la_rotation_dip(client, factory, horloge):
    """Cinq erreurs depuis cinq IP différentes, puis le bon code.

    Sans verrouillage par appareil, chacune de ces erreurs passerait : le
    limiteur par IP est contourné par construction.
    """
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345', statut='verrouillé')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    for i in range(5):
        # On avance l'horloge : sans cela, le palier expirerait tout seul et
        # le test ne mesurerait que le limiteur d'IP.
        horloge.avancer(3600)
        r = client.post(
            f'/api/appareils/{a.id}/verifier-code',
            json={'code': 'FAUX0000'},
            environ_base={'REMOTE_ADDR': f'10.0.0.{i + 1}'},
        )
        assert r.status_code == 401, f'essai {i} : {r.status_code}'

    # Sixième essai, cette fois avec le VRAI code, depuis une IP vierge.
    r = client.post(
        f'/api/appareils/{a.id}/verifier-code',
        json={'code': 'ABCD2345'},
        environ_base={'REMOTE_ADDR': '203.0.113.9'},
    )
    assert r.status_code == 200
    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'actif'


def test_une_rotation_dip_ne_permet_pas_de_boucler(client, factory, horloge):
    """Le scénario réel : on itère des codes faux en changeant d'IP, sans
    jamais attendre. Au bout de quelques essais, l'API doit répondre 429 —
    c'est le seul frein, et il doit tenir."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345', statut='verrouillé')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    codes = []
    for i in range(8):
        r = client.post(
            f'/api/appareils/{a.id}/verifier-code',
            json={'code': f'FAUX{i:04d}'},
            environ_base={'REMOTE_ADDR': f'10.9.{i}.1'},
        )
        codes.append(r.status_code)
        # L'attaquant n'attend pas : il enchaîne.
    assert 429 in codes, f'la rotation d\'IP contourne le verrouillage : {codes}'


def test_les_paliers_de_blocage_croissent(client, factory, horloge):
    """Chaque échec coûte plus cher que le précédent, si on respecte l'attente."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    delais = []
    for i in range(4):
        r = client.post(
            f'/api/appareils/{a.id}/verifier-code',
            json={'code': 'FAUX0000'},
            environ_base={'REMOTE_ADDR': f'10.1.0.{i + 1}'},
        )
        delais.append(r.get_json()['reessai_dans_s'])
        horloge.avancer(delais[-1])  # l'attaquant respecte le délai

    assert delais == sorted(delais) and len(set(delais)) == 4, f'paliers non croissants : {delais}'


def test_un_code_correct_reinitialise_le_compteur(client, factory, horloge):
    """Réussir annule l'historique : le propriétaire légitime n'est pas
    sanctionné par les erreurs d'un attaquant."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345', statut='verrouillé')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    delais = []
    for i in range(3):
        horloge.avancer(7200)
        r = client.post(
            f'/api/appareils/{a.id}/verifier-code',
            json={'code': 'FAUX0000'},
            environ_base={'REMOTE_ADDR': f'10.2.0.{i + 1}'},
        )
        delais.append(r.get_json()['reessai_dans_s'])

    r = client.post(
        f'/api/appareils/{a.id}/verifier-code',
        json={'code': 'ABCD2345'},
        environ_base={'REMOTE_ADDR': '10.2.0.99'},
    )
    assert r.status_code == 200

    # Le compteur repart de zéro : le palier suivant est de nouveau le premier.
    r = client.post(
        f'/api/appareils/{a.id}/verifier-code',
        json={'code': 'FAUX0000'},
        environ_base={'REMOTE_ADDR': '10.2.0.98'},
    )
    assert r.status_code == 401
    assert r.get_json()['reessai_dans_s'] == delais[0], 'compteur non remis à zéro'


def test_le_blocage_ne_concerne_qu_un_appareil(client, factory, horloge):
    """Bloquer l'appareil A ne doit pas empêcher de déverrouiller l'appareil B
    du même propriétaire — sinon un attaquant peut neutraliser le service
    d'un compte sans jamais trouver un code."""
    u = factory.user(password='secret123')
    a1 = factory.appareil(u, code_verrouillage='ABCD2345', statut='verrouillé')
    a2 = factory.appareil(u, code_verrouillage='WXYZ6789', statut='verrouillé')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    for i in range(5):
        horloge.avancer(7200)
        client.post(
            f'/api/appareils/{a1.id}/verifier-code',
            json={'code': 'FAUX0000'},
            environ_base={'REMOTE_ADDR': f'10.3.0.{i + 1}'},
        )

    r = client.post(f'/api/appareils/{a2.id}/verifier-code', json={'code': 'WXYZ6789'})
    assert r.status_code == 200


def test_le_pin_est_verrouille_progressivement(client, factory, horloge):
    """Le PIN ne fait que 6 chiffres (10^6 possibilités) : il doit être
    verrouillé lui aussi, sans quoi il est trouvable par force brute."""
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_ussd='123456', statut='actif')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    codes = []
    for i in range(8):
        r = client.post(
            f'/api/appareils/{a.id}/verrouiller-pin',
            json={'code_pin': '000000'},
            environ_base={'REMOTE_ADDR': f'10.4.0.{i + 1}'},
        )
        codes.append(r.status_code)

    assert 429 in codes, f'le PIN n\'est pas protégé par un verrouillage progressif : {codes}'
    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'actif', 'un PIN faux a verrouillé l\'appareil'


def test_les_codes_sont_compares_en_temps_constant(client, factory):
    """La comparaison des codes ne doit pas utiliser `==`, qui s'arrête au
    premier caractère différent et révèle la longueur du préfixe correct."""
    import inspect

    from app.routes import api

    source = inspect.getsource(api)
    interdits = [
        'code_verrouillage ==',
        '== code_verrouillage',
        'code_attendu ==',
        '== code_attendu',
        'code_ussd ==',
        '== code_ussd',
        'code_pin_saisi ==',
        '== code_pin_saisi',
    ]
    for motif in interdits:
        assert motif not in source, f'comparaison non constante : {motif!r}'


# ══════════════════════════════════════════════════════════════════
# 4. L'ALERTE COMMUNAUTAIRE NE VERROUILLE JAMAIS
# ══════════════════════════════════════════════════════════════════

def test_lalerte_communautaire_ne_verrouille_pas_les_tiers(client, factory, monkeypatch):
    """Règle non négociable : un signalement communautaire est une ALERTE.

    AVANT : la notification communautaire portait `"command": "LOCK"`. Un
    simple faux signalement de vol faisait donc verrouiller le téléphone de
    tous les autres utilisateurs du service.
    """
    import app
    from app import db as _db
    from app.models import FcmToken

    # On intercepte les envois push pour observer leur contenu.
    envois = []
    monkeypatch.setattr(app, 'envoyer_notification_push',
                        lambda user_id, titre, corps, data: envois.append(
                            (user_id, titre, data)))

    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_alice = factory.appareil(alice, statut='actif')
    a_bob = factory.appareil(bob, statut='actif')

    # Bob a accepté le partage sur l'appareil d'Alice.
    _db.session.add(FcmToken(user_id=bob.id, token='tok-bob'))
    _db.session.add(__import__('app.models', fromlist=['Alerte']).Alerte(
        user_id=bob.id, appareil_id=a_alice.id, type_alerte='vol',
        partage_accepte=True, partage_precision='approximatif',
    ))
    _db.session.commit()

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.post(f'/api/appareils/{a_alice.id}/verrouiller')
    assert r.status_code == 200

    communautaires = [d for (_uid, _t, d) in envois
                      if d.get('type') == 'community_alert']
    assert communautaires, "aucune alerte communautaire émise"
    for d in communautaires:
        assert d.get('command') == 'ALERT', (
            f"une alerte communautaire porte une commande {d.get('command')!r} : "
            "elle verrouillerait le téléphone des tiers")

    # Et surtout : le téléphone de Bob reste actif.
    from app.models import Appareil
    assert Appareil.query.get(a_bob.id).statut == 'actif'


# ══════════════════════════════════════════════════════════════════
# 5. ISOLATION ENTRE UTILISATEURS
# ══════════════════════════════════════════════════════════════════

def test_appareils_ne_fuit_pas_les_appareils_dautrui(client, factory):
    """AVANT : `/api/appareils` renvoyait tout appareil ayant un
    `device_uuid`, avec IMEI et code de verrouillage.

    Conséquence : il suffisait d'être inscrit pour inventorier et
    déverrouiller les téléphones des autres.
    """
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_alice = factory.appareil(alice)
    a_bob = factory.appareil(bob, device_uuid='uuid-bob')

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.get('/api/appareils')
    assert r.status_code == 200

    ids = {a['id'] for a in r.get_json()}
    assert a_alice.id in ids
    assert a_bob.id not in ids, "l'appareil d'un autre utilisateur est exposé"


def test_appareil_dautruin_ne_fuit_pas_son_imei(client, factory):
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_bob = factory.appareil(bob, device_uuid='uuid-bob', imei='351234567890099')

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.get('/api/appareils')
    assert r.status_code == 200
    for a in r.get_json():
        assert a.get('imei') != '351234567890099'
        assert a.get('code_verrouillage') is None or a['id'] != a_bob.id


def test_localisations_latest_ne_localise_pas_les_tiers(client, factory):
    """AVANT : `/api/localisations/latest` renvoyait la position de tous les
    téléphones du service. Géolocalisation continue de tiers."""
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_alice = factory.appareil(alice)
    a_bob = factory.appareil(bob, device_uuid='uuid-bob')
    factory.localisation(a_alice, lat=5.3600, lng=-4.0083)
    # Position très précise de Bob : ne doit jamais sortir de chez lui.
    factory.localisation(a_bob, lat=5.3721, lng=-3.9847)

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.get('/api/localisations/latest')
    assert r.status_code == 200

    ids = {d['appareil_id'] for d in r.get_json()}
    assert a_bob.id not in ids, "la position d'un appareil tiers est exposée"


def test_partage_explicite_rend_visible_mais_approximatif(client, factory):
    """Le partage, quand il est accordé, reste flou : ~1 km, jamais au mètre."""
    from app.models import Alerte
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_alice = factory.appareil(alice)
    from app import db as _db
    _db.session.add(Alerte(
        user_id=bob.id, appareil_id=a_alice.id, type_alerte='vol',
        partage_accepte=True, partage_precision='approximatif',
    ))
    factory.localisation(a_alice, lat=5.3600, lng=-4.0083)
    _db.session.commit()

    client.post('/api/auth/login', json={'email': bob.email, 'password': 'secret123'})
    r = client.get('/api/localisations/latest')
    entree = next(d for d in r.get_json() if d['appareil_id'] == a_alice.id)

    assert entree['precision'] == 'approximatif'
    assert entree['latitude'] == round(5.3600, 2)
    assert entree['imei'] is None, "l'IMEI ne doit jamais être partagé"


def test_partage_refuse_par_defaut(client, factory):
    """Sans consentement explicite du propriétaire, rien n'est partagé —
    même quand l'appareil est tracé par une alerte de vol."""
    from app.models import Alerte
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_alice = factory.appareil(alice)
    factory.alerte(bob, a_alice, type_alerte='vol')  # partage_accepte=False
    factory.localisation(a_alice, lat=5.3600, lng=-4.0083)

    client.post('/api/auth/login', json={'email': bob.email, 'password': 'secret123'})
    r = client.get('/api/localisations/latest')
    ids = {d['appareil_id'] for d in r.get_json()}
    assert a_alice.id not in ids


def test_historique_localisations_refuse_les_tiers(client, factory):
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_bob = factory.appareil(bob)
    factory.localisation(a_bob, lat=5.3600, lng=-4.0083)

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.get(f'/api/localisations/historique/{a_bob.id}')
    assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════
# 6. ENDPOINTS « MOBILE » PUBLIQUES
# ══════════════════════════════════════════════════════════════════

def test_mobile_lock_refuse_un_tiers(client, factory):
    """AVANT : `/api/mobile/lock/<uuid>` public.

    Conséquence : un script pouvait mettre en état « verrouillé » et
    déclencher une fausse alerte de vol sur n'importe quel téléphone connu.
    """
    alice = factory.user(password='secret123')
    a = factory.appareil(alice, device_uuid='uuid-alice', statut='actif')

    r = client.post('/api/mobile/lock/uuid-alice')
    assert r.status_code in (401, 404)

    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'actif'


def test_mobile_stolen_alert_refuse_un_tiers(client, factory):
    """AVANT : public. N'importe qui pouvait marquer un téléphone comme volé
    et y injecter une fausse position GPS — faire accuser un innocent."""
    alice = factory.user(password='secret123')
    a = factory.appareil(alice, device_uuid='uuid-alice', statut='actif')

    r = client.post('/api/mobile/stolen-alert', json={
        'device_uuid': 'uuid-alice', 'latitude': 5.3721, 'longitude': -3.9847,
    })
    assert r.status_code in (401, 404)

    from app.models import Appareil, Localisation
    assert Appareil.query.get(a.id).statut == 'actif'
    assert Localisation.query.count() == 0


def test_mobile_claim_exige_une_preuve_de_possession(client, factory):
    """AVANT : `device_uuid` seul suffisait pour s'attribuer la propriété
    d'un téléphone, y compris volé. L'UUID n'est pas un secret."""
    alice = factory.user(password='secret123')
    a = factory.appareil(alice, device_uuid='uuid-alice')

    bob = factory.user(password='secret123')
    client.post('/api/auth/login', json={'email': bob.email, 'password': 'secret123'})
    r = client.post('/api/mobile/claim', json={'device_uuid': 'uuid-alice'})
    assert r.status_code == 403

    from app.models import Appareil
    assert Appareil.query.get(a.id).user_id == alice.id


def test_mobile_register_ne_rattache_plus_au_compte_numero_1(client, factory):
    """AVANT : `user_id = user.id if user else 1`.

    Concrètement, un appel anonyme rattachait le téléphone au compte numéro 1
    du tout premier utilisateur créé.
    """
    premier = factory.user(email='premier@victime.ci', password='secret123')

    r = client.post('/api/mobile/register', json={'device_uuid': 'uuid-anonyme'})
    assert r.status_code == 401

    from app.models import Appareil
    assert Appareil.query.filter_by(device_uuid='uuid-anonyme').first() is None


def test_community_alerts_exige_authentification(client):
    """AVANT : endpoint public exposant la position de tous les téléphones
    volés du service."""
    r = client.get('/api/mobile/community-alerts')
    assert r.status_code == 401


def test_community_alerts_ne_donne_pas_l_imei(client, factory):
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a = factory.appareil(bob, device_uuid='uuid-bob', statut='volé',
                         imei='351234567890088')

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.get('/api/mobile/community-alerts')
    assert r.status_code == 200
    for alerte in r.get_json()['alertes']:
        assert 'imei' not in alerte
        assert 'device_uuid' not in alerte


# ══════════════════════════════════════════════════════════════════
# 7. SECRET D'APPAREIL
# ══════════════════════════════════════════════════════════════════

def test_le_secret_dappareil_est_oblige_pour_signaler_une_position(client, factory):
    u = factory.user(password='secret123')
    factory.appareil(u, secret_connu='secret-valide')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post('/api/localisation/update', json={'latitude': 5.33, 'longitude': -4.07})
    assert r.status_code == 401


def test_le_secret_dappareil_ne_donne_pas_acces_aux_requetes_utilisateur(client, factory):
    """Le secret d'un téléphone ne vaut PAS session de compte.

    Sinon, un voleur possessing le téléphone déverrouillé pourrait agir sur
    le compte du propriétaire (changement d'e-mail, suppression…)."""
    u = factory.user(password='secret123')
    factory.appareil(u, secret_connu='secret-valide')

    r = client.post('/api/alertes', headers={'X-Device-Token': 'secret-valide'})
    assert r.status_code == 401


def test_secret_inconnu_est_rejete(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u, secret_connu='secret-valide')
    r = client.post('/api/localisation/update',
                    headers={'X-Device-Token': 'secret-faux'},
                    json={'latitude': 5.33, 'longitude': -4.07})
    assert r.status_code == 401
    from app.models import Localisation
    assert Localisation.query.count() == 0


# ══════════════════════════════════════════════════════════════════
# 8. DONNÉES SENSIBLES EN BASE
# ══════════════════════════════════════════════════════════════════

def test_le_cookie_de_session_nest_plus_stocke(client, factory):
    """AVANT : `session_id = request.cookies['session']` était enregistré en
    base. C'était un jeton d'accès complet : le renvoyer dans un navigateur
    suffisait à se connecter comme la victime."""
    from app.models import TelephoneCollecte
    u = factory.user(password='secret123')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    cookie = client.get_cookie('session')
    assert cookie is not None

    r = client.post('/api/phone-info/collect', json={
        'modele': 'Pixel', 'marque': 'Google', 'consentement': True,
    })
    assert r.status_code == 201

    info = TelephoneCollecte.query.order_by(TelephoneCollecte.id.desc()).first()
    assert info.session_id != cookie.value
    assert len(info.session_id or '') <= 32


def test_collecte_telephone_exige_un_consentement(client):
    """AVANT : la collecte était inconditionnelle, le champ `consentement`
    existant déjà dans le modèle mais n'étant jamais lu."""
    r = client.post('/api/phone-info/collect', json={'modele': 'Pixel'})
    assert r.status_code == 403

    from app.models import TelephoneCollecte
    assert TelephoneCollecte.query.count() == 0


# ══════════════════════════════════════════════════════════════════
# 9. INTERCEPTION DU CANAL DE NOTIFICATION
# ══════════════════════════════════════════════════════════════════

def test_un_token_fcm_ne_peut_pas_etre_ajoute_au_compte_dautrui(client, factory):
    """AVANT : à défaut de session, l'identité venait du `device_uuid` du
    corps. Un attaquant pouvait enregistrer son token FCM sur le compte d'une
    victime et recevoir ses alertes antivol (position, ordres de verrouillage).
    """
    victime = factory.user(password='secret123')
    a = factory.appareil(victime, device_uuid='uuid-victime')

    r = client.post('/api/fcm/register-token', json={
        'fcm_token': 'fcm_token_de_l_attaquant_tres_long_0123456789',
        'device_uuid': 'uuid-victime',
    })
    assert r.status_code == 401

    from app.models import FcmToken
    assert FcmToken.query.count() == 0


# ══════════════════════════════════════════════════════════════════
# 10. QUALITÉ DES DONNÉES ENTRANTES
# ══════════════════════════════════════════════════════════════════

def test_type_alerte_invalide_refuse(client, factory):
    """Sans liste blanche, un type arbitraire part en base et casse les
    filtres de l'interface."""
    u = factory.user(password='secret123')
    a = factory.appareil(u)
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post('/api/alertes/signaler', json={
        'appareil_id': a.id, 'type_alerte': '<script>alert(1)</script>',
    })
    assert r.status_code == 400


def test_appareil_id_non_numerique_ne_provoque_pas_une_erreur_500(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u)
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post('/api/alertes/signaler', json={
        'appareil_id': 'ceci-n-est-pas-un-entier', 'type_alerte': 'vol',
    })
    assert r.status_code == 400


def test_signaler_une_alerte_refuse_un_appareil_dautrui(client, factory):
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_bob = factory.appareil(bob, statut='actif')

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.post('/api/alertes/signaler', json={
        'appareil_id': a_bob.id, 'type_alerte': 'vol',
    })
    assert r.status_code == 404

    from app.models import Appareil
    assert Appareil.query.get(a_bob.id).statut == 'actif'


# ══════════════════════════════════════════════════════════════════
# 11. ROUTES WEB — mêmes règles, pas d'exception
# ══════════════════════════════════════════════════════════════════

def test_lock_by_code_web_exige_la_connexion(client, factory):
    """AVANT : la page `/lock-by-code` était accessible sans authentification.

    Elle permettait à un visiteur anonyme de verrouiller un téléphone ou de le
    déclarer volé, et déclenchait une alerte chez le propriétaire. Le tout
    depuis un simple formulaire HTML, sans aucune trace d'audit exploitable.
    """
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345', statut='actif')

    r = client.post('/lock-by-code', data={'code': 'ABCD2345', 'action': 'lock'},
                    follow_redirects=True)
    # Sans session, on est renvoyé vers la page de connexion.
    assert r.status_code == 200
    assert b'Code invalide' not in r.data, "un appel anonyme a traité le code"

    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'actif'


def test_lock_by_code_web_refuse_le_code_dautrui(client, factory):
    """Connecté, on ne verrouille pas le téléphone d'un autre avec son code."""
    alice = factory.user(password='secret123')
    bob = factory.user(password='secret123')
    a_bob = factory.appareil(bob, code_verrouillage='ABCD2345', statut='actif')

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    r = client.post('/lock-by-code', data={'code': 'ABCD2345', 'action': 'lock'},
                    follow_redirects=True)
    assert r.status_code == 200
    assert 'Code invalide' in r.data.decode('utf-8', 'replace')

    from app.models import Appareil
    assert Appareil.query.get(a_bob.id).statut == 'actif'


def test_lock_by_code_web_fonctionne_pour_son_propre_appareil(client, factory):
    u = factory.user(password='secret123')
    a = factory.appareil(u, code_verrouillage='ABCD2345', statut='actif')
    client.post('/api/auth/login', json={'email': u.email, 'password': 'secret123'})

    r = client.post('/lock-by-code', data={'code': 'ABCD2345', 'action': 'lock'},
                    follow_redirects=True)
    assert r.status_code == 200

    from app.models import Appareil
    assert Appareil.query.get(a.id).statut == 'verrouillé'


def test_reclamer_appareil_refuse_un_compte_actif(client, factory):
    """AVANT : `/appareils/reclamer` ne demandait que le code.

    Connaître le code de verrouillage d'un téléphone suffisait à le détacher
    du compte de son propriétaire : il perdait l'accès à son téléphone, à ses
    alertes et à son historique.
    """
    ancien = factory.user(password='secret123')
    nouveau = factory.user(password='secret123')
    a = factory.appareil(ancien, code_verrouillage='ABCD2345', secret_connu='secret-bob')

    client.post('/api/auth/login', json={'email': nouveau.email, 'password': 'secret123'})
    r = client.post('/appareils/reclamer', data={'code': 'ABCD2345'},
                    follow_redirects=True)
    assert r.status_code == 200

    from app.models import Appareil
    assert Appareil.query.get(a.id).user_id == ancien.id, \
        "le compte d'un appareil actif a été détourné"


def test_reclamer_appareil_avec_preuve_de_possession(client, factory):
    """Le téléphone qui prouve sa possession peut être rattaché."""
    ancien = factory.user(password='secret123')
    nouveau = factory.user(password='secret123')
    a = factory.appareil(ancien, code_verrouillage='ABCD2345', secret_connu='secret-bob')

    client.post('/api/auth/login', json={'email': nouveau.email, 'password': 'secret123'})
    r = client.post('/appareils/reclamer',
                    data={'code': 'ABCD2345'},
                    headers={'X-Device-Token': 'secret-bob'},
                    follow_redirects=True)
    assert r.status_code == 200

    from app.models import Appareil
    assert Appareil.query.get(a.id).user_id == nouveau.id


def test_reclamer_libere_un_appareil_abandonne(client, factory):
    """Un appareil inactif depuis plus de 90 jours peut être repris."""
    from datetime import datetime, timezone, timedelta
    ancien = factory.user(password='secret123')
    nouveau = factory.user(password='secret123')
    a = factory.appareil(ancien, code_verrouillage='ABCD2345',
                         date_enregistrement=datetime.now(timezone.utc) - timedelta(days=200))

    client.post('/api/auth/login', json={'email': nouveau.email, 'password': 'secret123'})
    client.post('/appareils/reclamer', data={'code': 'ABCD2345'}, follow_redirects=True)

    from app.models import Appareil
    db_a = Appareil.query.get(a.id)
    assert db_a.user_id == nouveau.id
    # L'ancien secret ne doit plus fonctionner : le nouveau détenteur ne
    # doit pas hériter du contrôle à distance laissé par l'ancien.
    assert db_a.device_secret is None


# ══════════════════════════════════════════════════════════════════
# 12. CANAL DE COMMANDE — plus de topic public devinable
# ══════════════════════════════════════════════════════════════════

def test_le_topic_ntfy_ne_depend_plus_du_numero_utilisateur():
    """AVANT : `topic = 'antivol-u' + str(user_id)`.

    ntfy.sh est public : un topic devinable = une commande « LOCK » que
    n'importe qui peut injecter, et un fil que n'importe qui peut lire.
    Le topic doit dépendre du SECRET de l'appareil, pas d'un identifiant
    numérique séquentiel.
    """
    from app.commandes import topic_pour_secret

    topic = topic_pour_secret('secret-de-telephone-1')
    assert topic is not None
    assert 'u1' not in topic
    assert topic.startswith('antivol-a')
    assert 'secret' not in topic


def test_deux_appareils_ont_des_topics_differents():
    from app.commandes import topic_pour_secret
    assert topic_pour_secret('secret-a') != topic_pour_secret('secret-b')


def test_un_topic_est_stable_pour_un_meme_secret():
    """Le téléphone doit retrouver son topic à chaque redémarrage, sans que
    le serveur ait à le lui rappeler."""
    from app.commandes import topic_pour_secret
    assert topic_pour_secret('secret-stable') == topic_pour_secret('secret-stable')


def test_les_commandes_sont_signees():
    """Un message non signé ne doit jamais être publié : c'est la garantie
    qu'un topic découvert ne suffit pas à piloter le téléphone."""
    from app.commandes import signer, verifier

    secret = 'secret-de-telephone-1'
    message = signer(secret, {'command': 'LOCK', 'appareil_id': '7'})
    assert message is not None
    assert 'sig' in message and 'ts' in message
    assert verifier(secret, message)


def test_une_signature_forgee_est_rejetee():
    """Le scénario d'attaque : l'attaquant découvre le topic et publie
    lui-même un ordre de verrouillage, avec un horodatage valide."""
    from app.commandes import verifier
    import time

    message = {'command': 'LOCK', 'appareil_id': '7', 'v': 'v1',
               'ts': int(time.time()), 'sig': 'signature-fabriquee'}
    assert verifier('le-vrai-secret', message) is False


def test_un_message_modifie_apres_signature_est_rejete():
    """Modifier le contenu après signature doit invalider la signature."""
    from app.commandes import signer, verifier

    secret = 'secret-de-telephone-1'
    message = signer(secret, {'command': 'ALERT', 'appareil_id': '7'})

    # L'attaquant intercepte et remplace ALERT par LOCK.
    message['command'] = 'LOCK'
    assert verifier(secret, message) is False


def test_un_message_ancien_est_rejete_comme_rejeu():
    """Rejouer un « verrouille » émis il y a 24 h sur un téléphone récupéré
    doit être sans effet."""
    from app.commandes import signer, verifier
    import time

    secret = 'secret-de-telephone-1'
    ancien = time.time() - 86400
    message = signer(secret, {'command': 'LOCK'}, horodatage=ancien)
    assert verifier(secret, message) is False


def test_le_secret_dun_autre_appareil_ne_signe_pas_valablement():
    from app.commandes import signer, verifier
    message = signer('secret-appareil-1', {'command': 'LOCK'})
    assert verifier('secret-appareil-2', message) is False


def test_rien_nest_publie_sur_un_topic_devinable(app, factory, monkeypatch):
    """Test d'intégration : aucun envoi ne doit mentionner `antivol-u<id>`
    ni le topic global `antivol-community`."""
    import app as app_module
    from app.commandes import topic_pour_secret

    u = factory.user(password='secret123')
    factory.appareil(u, secret_connu='secret-de-telephone-1')
    # Un appareil non enrôlé ne doit, lui, rien recevoir.
    factory.appareil(u, imei='350000000000001')

    publie = []
    monkeypatch.setattr(app_module, '_envoyer_ntfy',
                        lambda topic, message, titre, corps: publie.append((topic, message)))
    # `ConfigTest` court-circuite les envois ; on le désactive pour observer.
    monkeypatch.setitem(app.config, 'ANTIVOL_TEST_MODE', False)

    app_module.envoyer_notification_push(u.id, 'Alerte', 'Vol détecté', {'command': 'LOCK'})

    assert publie, "aucun message ntfy publié : la commande ne peut plus rien déclencher"
    for topic, _message in publie:
        assert not topic.startswith('antivol-u'), f"topic devinable publié : {topic}"
        assert topic != 'antivol-community', "diffusion globale rétablie"
        assert topic == topic_pour_secret('secret-de-telephone-1')
    # Un seul message : celui de l'appareil enrôlé, pas celui de l'appareil nu.
    assert len(publie) == 1
    assert publie[0][1]['sig'], "le message publié doit être signé"


def test_les_messages_publies_sont_signes_avec_le_secret_de_lappareil(app, factory, monkeypatch):
    """Le récepteur doit pouvoir authentifier le message avec son seul
    secret : c'est ce que fera l'application Android."""
    import app as app_module
    from app.commandes import verifier

    u = factory.user(password='secret123')
    factory.appareil(u, secret_connu='secret-de-telephone-1')

    publie = []
    monkeypatch.setattr(app_module, '_envoyer_ntfy',
                        lambda topic, message, titre, corps: publie.append(message))
    monkeypatch.setitem(app.config, 'ANTIVOL_TEST_MODE', False)

    app_module.envoyer_notification_push(u.id, 'Alerte', 'Vol détecté', {'command': 'LOCK'})

    assert len(publie) == 1
    message = publie[0]
    assert verifier('secret-de-telephone-1', message) is True
    assert verifier('un-autre-secret', message) is False


# ══════════════════════════════════════════════════════════════════
# 13. PARITÉ PYTHON / KOTLIN — le téléphone doit comprendre le serveur
# ══════════════════════════════════════════════════════════════════

_VECTEURS = 'app/antivol-mobile-v2/app/src/test/resources/commande_vecteur.json'


def _charger_vecteurs():
    import json
    import os
    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(racine, _VECTEURS), encoding='utf-8') as f:
        return json.load(f)


def test_le_fichier_de_vecteurs_est_lisible():
    """Point d'entrée de la parité inter-langages."""
    vecteurs = _charger_vecteurs()
    assert vecteurs['cas'], "aucun vecteur : la parité Python/Kotlin ne teste rien"
    assert 'CommandeProtocoleTest' in open(
        'app/antivol-mobile-v2/app/src/test/java/com/antivol/mobile/data/CommandeProtocoleTest.kt',
        encoding='utf-8',
    ).read(), "le test Kotlin doit consommer le même fichier de vecteurs"


def test_python_signe_exactement_comme_le_telephone_le_calcule():
    """`CommandeProtocoleTest.kt` (Kotlin) rejoue ces mêmes vecteurs.

    Si Python produit une chaîne canonique différente, le téléphone
    calculera une autre signature et refusera tous les ordres : c'est donc un
    test bloquant, pas une commodité.
    """
    from app.commandes import topic_pour_secret, verifier

    for cas in _charger_vecteurs()['cas']:
        assert topic_pour_secret(cas['secret']) == cas['topic'], cas['nom']
        message = dict(cas['message'])
        assert verifier(cas['secret'], message, maintenant=cas['ts']) is True, cas['nom']
        # Et le serveur refuse bien un message entaché par un autre secret.
        assert verifier('autre-secret', message, maintenant=cas['ts']) is False, cas['nom']


def test_la_canoique_python_est_bien_celle_du_fichier_de_vecteurs():
    """Garde-fou contre une dérive silencieuse de `_a_signer`."""
    import json
    from app.commandes import _a_signer

    for cas in _charger_vecteurs()['cas']:
        sans_sig = {k: v for k, v in cas['message'].items() if k != 'sig'}
        canonique = _a_signer(cas['secret'], sans_sig).decode('utf-8')
        assert canonique == cas['canonique'], (
            f"dérive sur « {cas['nom']} »\n"
            f"  attendu : {cas['canonique']!r}\n"
            f"  obtenu  : {canonique!r}"
        )
        # Le fichier doit rester relisible : pas d'échappement ASCII superflu.
        assert json.loads(canonique) == sans_sig


def test_aucune_position_gps_dans_une_alerte_communautaire(client, factory, monkeypatch):
    """La position précise d'un vol appartient au propriétaire et aux
    autorités : elle ne doit jamais partir dans une alerte communautaire."""
    import app as app_module

    alice = factory.user(password='secret123')
    a = factory.appareil(alice, secret_connu='secret-alice')
    factory.localisation(a, lat=5.3600, lng=-4.0083)

    captures = []
    monkeypatch.setattr(app_module, '_envoyer_ntfy',
                        lambda topic, message, titre, corps: captures.append(str(message)))
    monkeypatch.setitem(client.application.config, 'ANTIVOL_TEST_MODE', False)

    client.post('/api/auth/login', json={'email': alice.email, 'password': 'secret123'})
    client.post(f'/api/appareils/{a.id}/verrouiller')

    assert captures, "aucune alerte communautaire émise"
    for texte in captures:
        assert '5.36' not in texte
        assert '-4.0083' not in texte
