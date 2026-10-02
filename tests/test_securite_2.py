"""
Tests de NON-régression de sécurité — lot 2.

Complète `test_securite.py` : celui-ci verrouille l'identité et le canal de
commande, celui-ci verrouille le durcissement HTTP et la facturation SMS.

Comme pour le fichier d'origine, le commentaire « AVANT » de chaque test
décrit l'état vulnérable que le test empêche de revenir.
"""

import json
import re

import pytest


# ─────────────────────────── 1. En-têtes de sécurité HTTP ───────────────────────────
# AVANT : `after_request` ne journalisait que les requêtes. Aucune réponse ne
# portait d'en-tête de durcissement. Le tableau de bord exposant la position
# d'un téléphone et son code PIN, il était intégrable dans une iframe
# (clickjacking sur les boutons de verrouillage) et le navigateur pouvait
# deviner le type d'une réponse.

@pytest.mark.parametrize('chemin', ['/', '/login'])
def test_entetes_securite_presents(client, chemin):
    r = client.get(chemin)
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'DENY'
    # Les positions et identifiants ne doivent pas fuir via le Referer.
    assert r.headers['Referrer-Policy'] == 'no-referrer'


def test_api_herite_des_entetes_de_securite(client):
    """La règle vaut aussi pour l'API : c'est elle que consomme le mobile."""
    r = client.get('/api/appareils')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'DENY'


def test_pas_de_hsts_en_http_de_dveloppement(client):
    """AVANT : poser `Strict-Transport-Security` inconditionnellement.

    Un navigateur qui reçoit cet en-tête sur `http://` cesse d'accepter le
    trafic en clair pour ce domaine : le cookie `Secure` ne serait plus
    jamais envoyé, et le serveur de développement local deviendrait
    inutilisable. L'en-tête n'a de sens que sur HTTPS.
    """
    r = client.get('/')
    assert 'Strict-Transport-Security' not in r.headers


def test_le_referer_ne_fuit_pas_la_page_de_carte(client):
    """AVANT : sans `Referrer-Policy`, le navigateur envoyait l'URL de la page
    — qui contient l'identifiant d'appareil — aux requêtes vers un CDN tiers
    (icônes, polices)."""
    r = client.get('/login')
    assert r.headers['Referrer-Policy'] == 'no-referrer'


# ─────────────────────────── 3. 401 JSON sur l'API ───────────────────────────
# AVANT : `@login_required` renvoyait 302 vers `/login`. Le client Android
# suivait la redirection et recevait la page HTML de connexion avec un **200**,
# que Gson ne pouvait pas désérialiser. L'application ne pouvait donc pas
# distinguer « session expirée » d'une panne réseau.

def test_api_sans_session_repond_401_json(client):
    r = client.get('/api/appareils')
    assert r.status_code == 401
    assert r.headers['Content-Type'].startswith('application/json')


def test_api_sans_session_ne_renvoie_pas_de_html(client):
    """Le point qui compte : le client mobile ne doit plus recevoir une page web.

    C'est ce retour HTML qui produisait une erreur de parsing côté Android au
    lieu d'un 401 exploitable.
    """
    r = client.get('/api/appareils')
    assert r.status_code == 401
    corps = r.get_data(as_text=True)
    assert '<html' not in corps.lower()
    assert 'csrf' not in corps.lower(), 'un formulaire de connexion ne doit pas fuiter vers l\'API'


def test_le_401_nomme_la_cause(client):
    # Le client doit pouvoir afficher un message adapté plutôt qu'une erreur
    # réseau générique.
    r = client.get('/api/appareils')
    corps = r.get_json()
    assert corps['succes'] is False
    assert corps['erreur'] == 'non_authentifie'


def test_une_page_web_reste_redirigee_vers_la_connexion(client):
    """Le comportement des pages ne doit pas changer : une redirection vers la
    connexion reste le bon UX pour un navigateur."""
    r = client.get('/dashboard')
    assert r.status_code in (302, 401)
    if r.status_code == 302:
        assert '/login' in r.headers['Location']


def test_les_pages_et_api_ne_se_confondent_pas(client):
    """Deux routes du même nom logique, deux contrats de réponse distincts."""
    page = client.get('/appareils', follow_redirects=False)
    api = client.get('/api/appareils')
    assert page.status_code in (200, 302)
    assert api.status_code == 401
# ───────────────────────── 2. Content-Security-Policy ─────────────────────────
# AVANT : aucune politique. L'échappement Jinja protégeait les gabarits, mais
# toute fuite suffirait à faire exécuter un script sans entrave. La politique
# n'autorise rien en ligne : seuls les scripts porteurs du nonce de la
# réponse peuvent s'exécuter.

def test_csp_est_presente(client):
    r = client.get('/login')
    assert 'Content-Security-Policy' in r.headers


def test_script_src_n_accepte_pas_inline(client):
    """C'est LA condition qui rend la politique utile.

    Avec `'unsafe-inline'` dans `script-src`, le navigateur exécute le premier
    script trouvé sur la page, y compris injecté : la politique n'apporte plus
    rien. Son absence est ce qui bloque réellement une XSS.
    """
    r = client.get('/login')
    script_src = [p for p in r.headers['Content-Security-Policy'].split('; ')
                  if p.startswith('script-src')][0]
    assert 'unsafe-inline' not in script_src, script_src
    assert "'nonce-" in script_src, script_src


def test_style_src_peut_conserver_inline(client):
    """125 attributs `style=` en ligne interdisent de resserrer `style-src`
    sans refonte des gabarits. Le test documente ce reste à faire au lieu de
    le laisser passer inaperçu."""
    r = client.get('/login')
    assert 'style-src' in r.headers['Content-Security-Policy']


def test_le_nonce_du_script_en_ligne_est_autorise(client):
    """Les scripts en ligne des gabarits ne doivent PAS être bloqués par la
    politique qu'on vient d'ajouter : sans cela, toute la page est morte.

    Le nonce se lit sur la réponse qui a servi à rendre la page — en prendre
    une deuxième donnerait un nonce différent, par construction.
    """
    r = client.get('/login')
    nonce = r.headers['Content-Security-Policy'].split("'nonce-")[1].split("'")[0]
    assert ('nonce="%s"' % nonce) in r.text


def test_le_nonce_change_a_chaque_reponse(client):
    """Un nonce fixe ou réutilisé perdrait toute valeur : il doit être tiré
    par réponse."""
    a = client.get('/login').headers['Content-Security-Policy']
    b = client.get('/login').headers['Content-Security-Policy']
    assert a != b


def test_la_politique_ferme_object_base_et_iframe(client):
    csp = client.get('/login').headers['Content-Security-Policy']
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "form-action 'self'" in csp


def test_les_origines_reelles_sont_autorisees(client):
    """Les gabarits chargent Lucide, Leaflet et Chart.js, les polices Google,
    un QR code et des tuiles OpenStreetMap. Les oublier viderait la carte et
    casseraient les icônes : la politique doit les nommer."""
    csp = client.get('/login').headers['Content-Security-Policy']
    for origine in ('https://unpkg.com', 'https://cdn.jsdelivr.net',
                    'https://fonts.googleapis.com', 'https://fonts.gstatic.com',
                    'https://api.qrserver.com', 'https://*.tile.openstreetmap.org'):
        assert origine in csp, origine


def test_aucun_script_inline_ne_reste_sans_nonce(app):
    """Porte la sortie : un gabarit oublié casserait sa page en silence."""
    import pathlib
    dossiers = pathlib.Path(app.root_path).parent / 'templates'
    trouves = []
    for gabarit in dossiers.glob('*.html'):
        for numero, ligne in enumerate(gabarit.read_text(encoding='utf-8').splitlines(), 1):
            if '<script>' in ligne:
                trouves.append('%s:%d' % (gabarit.name, numero))
    assert not trouves, 'scripts en ligne sans nonce : %s' % trouves


def test_toutes_les_pages_rendent_avec_leur_nonce(client, factory, db):
    """Rattrape les deux erreurs que la CSP peut produire en silence.

    1. Un gabarit qui rend encore mais dont le script n'a pas le nonce → la
       page se charge et **tout le JavaScript est bloqué** : tableau de bord
       sans carte ni graphiques, formulaire de connexion inerte.
    2. Un gabarit cassé par l'édition du nonce → erreur 500.

    On parcourt le site connecté, parce que `/` renvoie l'utilisateur selon son
    rôle : c'est la page la plus provável d'avoir divergé.
    """
    from flask_login import login_user
    import re

    utilisateur = factory.user()
    with client.session_transaction() as session:
        session['_user_id'] = str(utilisateur.id)
        session['_fresh'] = True

    # Liste réelle issue du url_map (hors API, statique et pages à paramètre) :
    # inventée à la main, elle contenait '/historique', qui n'existe pas.
    pages = ['/', '/dashboard', '/appareils', '/alertes', '/carte', '/profil',
             '/admin', '/lock-by-code', '/mobile', '/login', '/register',
             '/reset-password', '/download']
    for page in pages:
        r = client.get(page, follow_redirects=True)
        assert r.status_code == 200, '%s -> %d' % (page, r.status_code)
        # Une page protégée qui retombe sur /login passerait le 200 mais
        # n'aurait rien à tester : c'est le garde-fou contre un faux positif.
        assert r.request.path != '/login', \
            '%s a redirige vers la connexion : session non etablie' % page
        assert 'Content-Security-Policy' in r.headers, page
        nonce = r.headers['Content-Security-Policy'].split("'nonce-")[1].split("'")[0]
        # Chaque script en ligne de la page doit porter CE nonce.
        for numero in re.findall(r'<script(?! src)[^>]*>', r.text):
            assert 'nonce="%s"' % nonce in numero, \
                '%s : script sans le bon nonce -> %s' % (page, numero)


def test_le_telechargement_apk_sert_du_binaire(client):
    """`/download/apk` renvoie un APK, pas du HTML : il ne doit pas être
    décodé en UTF-8, ni framed par la CSP comme une page."""
    r = client.get('/download/apk')
    assert r.status_code in (200, 404, 503)
    if r.status_code == 200:
        assert not r.headers.get('Content-Type', '').startswith('text/html')



# ─────────────────── 2. Contacts d'urgence : format et borne ───────────────────
# AVANT : la liste était enregistrée telle quelle, sans validation ni borne.
# Chaque entrée devenait un SMS Twilio payant au déclenchement d'une alerte
# vol ou perte. Un compte pouvait donc en stocker des milliers, et déclarer
# son téléphone volé suffisait à faire facturer des milliers de messages à
# l'exploitant — ou à harceler les numéros choisis.

def test_contacts_urgents_rejette_les_non_numeros(client, factory, login):
    """AVANT : « abc » était enregistré, et partait en SMS au moment du vol."""
    u, _ = login()
    a = factory.appareil(u)

    client.post('/appareils/%d/contacts' % a.id,
                data={'contacts_urgents': 'abc\n0044 20 12 34 56 78'})

    assert a.contacts_urgents is None


def test_contacts_urgents_normalise_les_separateurs(client, factory, login):
    """AVANT : « +225 07 01 23 45 67 » était refusé à l'envoi, qui exige un
    international sans séparateur, alors que l'interface l'affichait comme
    pris en compte. Le contact partait silencieusement, sans SMS."""
    u, _ = login()
    a = factory.appareil(u)

    client.post('/appareils/%d/contacts' % a.id, data={
        'contacts_urgents': '+225 07 01 23 45 67\n+225-07-01-23-45-68'
    })

    assert json.loads(a.contacts_urgents) == ['+2250701234567', '+2250701234568']


def test_contacts_urgents_sont_bornes(client, factory, login):
    """AVANT : aucune borne. 5 000 numéros = 5 000 SMS pour une seule alerte."""
    u, _ = login()
    a = factory.appareil(u)

    client.post('/appareils/%d/contacts' % a.id, data={
        'contacts_urgents': '\n'.join('+2250701234%03d' % i for i in range(500))
    })

    assert len(json.loads(a.contacts_urgents)) == 10


def test_la_borne_porte_sur_les_numeres_valides(client, factory, login):
    """Les lignes rejetées ne doivent pas consommer de place : sinon dix lignes
    invalides puis dix valides feraient dépasser la borne pour des contacts
    parfaitement légitimes."""
    u, _ = login()
    a = factory.appareil(u)

    client.post('/appareils/%d/contacts' % a.id, data={
        'contacts_urgents': '\n'.join(['pas un numero'] * 20 + ['+2250701234567'])
    })

    assert json.loads(a.contacts_urgents) == ['+2250701234567']


def test_aucun_contact_urgent_vide(client, factory, login):
    """AVANT : des lignes vides étaient stockées et comptées comme contacts."""
    u, _ = login()
    a = factory.appareil(u)

    client.post('/appareils/%d/contacts' % a.id,
                data={'contacts_urgents': '\n\n   \n\n'})

    assert a.contacts_urgents is None


def test_format_e164_trop_court_ou_trop_long_refuse(client, factory, login):
    """AVANT : toute chaîne non vide était conservée. Un international fait de
    1 chiffre ou de 20 n'en est pas un, et l'envoi le transmettait tel quel
    à Twilio."""
    u, _ = login()
    a = factory.appareil(u)

    client.post('/appareils/%d/contacts' % a.id, data={
        'contacts_urgents': '+1\n+2250701234567890\n+2250701234567'
    })

    assert json.loads(a.contacts_urgents) == ['+2250701234567']


def test_la_validation_refuse_un_suffixe_au_numero(client, factory, login):
    """AVANT : une validation par `startswith('+')` aurait accepté
    « +2250701234567abc », valeur ensuite réinjectée dans la liste stockée et
    réemployée comme destinataire. L'ancre de fin l'interdit."""
    u, _ = login()
    a = factory.appareil(u)

    client.post('/appareils/%d/contacts' % a.id, data={
        'contacts_urgents': '+2250701234567abc\n+2250701234567<script>'
    })

    assert a.contacts_urgents is None


def test_un_signe_interne_est_refuse(client, factory, login):
    u, _ = login()
    a = factory.appareil(u)

    client.post('/appareils/%d/contacts' % a.id,
                data={'contacts_urgents': '+22+50701234567'})

    assert a.contacts_urgents is None


def test_la_regex_est_anchoree_sur_les_deux_bouts():
    """La regex est la barrière. Testée directement : une régression
    silencieuse dans son équilibrage ne se verrait pas autrement."""
    motif = re.compile(r'\+\d{8,15}')

    for invalide in ['+2250701234567890', '+1234567', '2250701234567',
                     '+225 0701234567', '+225abc0701234', '+2250701234567x',
                     '', '+', '+2250701234-5', 'tel:+2250701234567']:
        assert not motif.fullmatch(invalide), invalide

    for valide in ['+2250701234567', '+33612345678', '+12345678901']:
        assert motif.fullmatch(valide), valide


# ─────────────────── 3. Un compte ne peut pas agir sur les autres ───────────────────

def test_contacts_urgents_d_un_appareil_autre_refuses(client, factory, login):
    """AVANT : la route ne vérifiait pas le propriétaire. Un utilisateur
    connecté pouvait réécrire la liste de contacts d'un appareil appartenant à
    quelqu'un d'autre, et décider que l'alerte de ce téléphone partirait vers
    le numéro de son choix."""
    alice = factory.user(password='x')
    a_vicime = factory.appareil(alice)

    login()  # un autre utilisateur
    r = client.post('/appareils/%d/contacts' % a_vicime.id,
                    data={'contacts_urgents': '+2250701234567'},
                    follow_redirects=True)

    assert 'Non autoris' in r.text
    assert a_vicime.contacts_urgents is None
