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
