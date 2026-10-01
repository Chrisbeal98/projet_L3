"""Fixtures partagées pour la suite de tests AntiVol.

La base de test est un fichier SQLite éphémère, recréé à chaque session.
Aucun test ne touche `antivol.db` ni les données de développement.
"""

import os
import sys

# Garantir que la racine du dépôt est importable avant tout import de `app`.
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RACINE not in sys.path:
    sys.path.insert(0, RACINE)

# Variables d'environnement minimales avant l'import de `config.py`.
os.environ.setdefault('SECRET_KEY', 'cle-de-test-uniquement-32-caracteres-min')
os.environ.setdefault('SESSION_COOKIE_SECURE', 'false')

import pytest  # noqa: E402

from app import create_app, db as _db, bcrypt as _bcrypt  # noqa: E402
from app.models import (  # noqa: E402
    User, Appareil, Alerte, Localisation, FcmToken,
)
from config import Config  # noqa: E402


class ConfigTest(Config):
    """Configuration de test : hérite de la production, surclasse le nécessaire.

    Hériter de `Config` est indispensable : `create_app` lit des clés comme
    `LANGUAGES` via `app.config.get(...)`, et une classe autonome ferait
    silencieusement retomber l'application sur ses valeurs par défaut.
    """

    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    WTF_CSRF_ENABLED = False          # le CSRF est testé séparément
    SESSION_COOKIE_SECURE = False
    NTFY_URL = 'https://ntfy.sh'
    # Aucun envoi réseau pendant les tests.
    FIREBASE_SERVICE_ACCOUNT = ''
    ANTIVOL_TEST_MODE = True          # court-circuite les envois push


@pytest.fixture(scope='session')
def _fichier_log_tmp(tmp_path_factory):
    """Redirige le log de requêtes vers un fichier temporaire.

    `create_app` ouvre un `FileHandler` sur `server_req.log` (racine du dépôt) :
    sans cette redirection, chaque exécution de la suite le remplirait — et
    le dépôt contient des données réelles dans ce fichier. Le chemin est
    désormais piloté par `ConfigTest.LOG_FILE`, ce qui supprime le besoin de
    manipuler le fichier du projet.
    """
    return str(tmp_path_factory.mktemp('logs') / 'requetes.log')


@pytest.fixture
def app(_fichier_log_tmp):
    """Application Flask isolée, base recréée pour chaque test."""
    class _Config(ConfigTest):
        LOG_FILE = _fichier_log_tmp

    instance = create_app(_Config)
    instance.config['TESTING'] = True

    with instance.app_context():
        _db.drop_all()
        _db.create_all()
        yield instance
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    """Session SQLAlchemy liée à l'application de test."""
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


# ─────────────────────────────── Fabriques d'objets ───────────────────────────────

def _password():
    return 'motdepasse-test'


@pytest.fixture
def fbcrypt():
    return _bcrypt


@pytest.fixture
def factory(db, fbcrypt):
    """Fabriques d'utilisateurs et d'appareils pour les tests."""

    class Factory:
        def user(self, email=None, role='utilisateur', password=None, **kw):
            u = User(
                nom=kw.pop('nom', 'Testeur'),
                prenom=kw.pop('prenom', 'Jean'),
                email=email or f"user{_id()}@test.ci",
                telephone=kw.pop('telephone', '+225 07 00 00 00'),
                password_hash=fbcrypt.generate_password_hash(password or _password()).decode(),
                role=role,
                statut=kw.pop('statut', 'actif'),
                **kw,
            )
            db.session.add(u)
            db.session.commit()
            return u

        def admin(self, email=None, **kw):
            return self.user(email=email, role='admin', **kw)

        def appareil(self, user, imei=None, **kw):
            # `secret_connu` : secret d'appareil en clair à enregistrer. Utile
            # pour tester les endpoints authentifiés par X-Device-Token.
            secret_connu = kw.pop('secret_connu', None)
            a = Appareil(
                user_id=user.id,
                imei=imei or f"35{_id():013d}"[:15],
                modele=kw.pop('modele', 'Galaxy Test'),
                marque=kw.pop('marque', 'Samsung'),
                systeme_os=kw.pop('systeme_os', 'Android'),
                version_os=kw.pop('version_os', '14'),
                numero_telephone=kw.pop('numero_telephone', '+225 05 00 00 00'),
                operateur=kw.pop('operateur', 'Orange CI'),
                statut=kw.pop('statut', 'actif'),
                code_verrouillage=kw.pop('code_verrouillage', None),
                code_ussd=kw.pop('code_ussd', None),
                device_uuid=kw.pop('device_uuid', None),
                contacts_urgents=kw.pop('contacts_urgents', None),
                **kw,
            )
            if a.code_verrouillage is None:
                from app.routes.api import generer_code_verrouillage
                a.code_verrouillage = generer_code_verrouillage()
            if a.code_ussd is None:
                from app.routes.api import generer_code_pin
                a.code_ussd = generer_code_pin()
            if secret_connu is not None:
                from app.device_auth import enroller_appareil
                enroller_appareil(a, secret_connu)
            db.session.add(a)
            db.session.commit()
            return a

        def localisation(self, appareil, lat=5.3600, lng=-4.0083, **kw):
            from datetime import datetime, timezone
            loc = Localisation(
                appareil_id=appareil.id,
                latitude=kw.pop('latitude', lat),
                longitude=kw.pop('longitude', lng),
                precision_m=kw.pop('precision_m', 10.0),
                source=kw.pop('source', 'gps'),
                date_capture=kw.pop('date_capture', datetime.now(timezone.utc)),
                **kw,
            )
            db.session.add(loc)
            db.session.commit()
            return loc

        def alerte(self, user, appareil, type_alerte='vol', **kw):
            from datetime import datetime, timezone
            a = Alerte(
                user_id=user.id,
                appareil_id=appareil.id,
                type_alerte=type_alerte,
                description=kw.pop('description', 'Description de test'),
                statut=kw.pop('statut', 'en_cours'),
                priorite=kw.pop('priorite', 'haute'),
                date_creation=kw.pop('date_creation', datetime.now(timezone.utc)),
                **kw,
            )
            db.session.add(a)
            db.session.commit()
            return a

        def fcm_token(self, user, token=None):
            t = FcmToken(user_id=user.id, token=token or f"tok-{_id()}")
            db.session.add(t)
            db.session.commit()
            return t

    return Factory()


_COMPTEUR = iter(range(1, 10_000_000))


def _id():
    return next(_COMPTEUR)


# ─────────────────────────────── Helpers de session ───────────────────────────────

@pytest.fixture
def login(client, factory):
    """Connecte un utilisateur via l'API et renvoie (user, reponse)."""

    def _login(role='utilisateur'):
        u = factory.user(role=role, password='motdepasse-test')
        r = client.post('/api/auth/login', json={
            'email': u.email, 'password': 'motdepasse-test',
        })
        assert r.status_code == 200, r.get_json()
        return u, r

    return _login


# ───────────────────────── Anti-bot : utilitaires de test ─────────────────────────

def _js_challenge(age_secondes=5.0):
    """Reproduit le couple (_ts, _js) attendu par le challenge anti-bot.

    Le serveur exige (a) un horodatage situé au moins 1,5 s dans le passé et
    (b) la valeur hexadécimale de ``antivol-js-<ts>`` tronquée à 16 caractères.
    """
    import time as _t
    ts = f"{_t.time() - age_secondes:.6f}"
    brut = f"antivol-js-{ts}"
    js = ''.join(format(ord(c), '02x') for c in brut)[:16]
    return {'_ts': ts, '_js': js}


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Vide les limiteurs de taux en mémoire entre chaque test.

    Ils sont des dictionnaires de module : sans cette remise à zéro, la
    4ᵉ inscription d'un même test déclencherait le rate limiting (3 / 600 s).
    """
    from app.routes import auth as _auth
    from app.routes import api as _api
    for nom in ('_tentatives_connexion', '_tentatives_inscription',
                '_tentatives_reset'):
        if hasattr(_auth, nom):
            getattr(_auth, nom).clear()
    for nom in ('_tentatives_api_login', '_tentatives_api_register',
                '_tentatives_api_code', '_tentatives_api_code_vk'):
        if hasattr(_api, nom):
            getattr(_api, nom).clear()
    yield


@pytest.fixture
def anti_bot():
    """Expose le générateur de challenge anti-bot aux tests."""
    return _js_challenge
