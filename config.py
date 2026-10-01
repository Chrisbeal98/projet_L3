import os

basedir = os.path.abspath(os.path.dirname(__file__))

# Charger le .env du projet avant de lire les variables ci-dessous, afin que
# run.py, wsgi.py (gunicorn) et les tests obtiennent la meme configuration.
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(basedir, '.env'))
except ImportError:
    pass


# ─── Sécurité : aucun secret ne doit jamais être livré dans le dépôt ───
# SECRET_KEY est OBLIGATOIRE. Aucune valeur de repli n'est fournie : un secret
# de repli coderait en dur dans le code permettrait de forger des sessions.
# En développement, un secret éphémère est généré si rien n'est défini.
_ENV = os.environ.get('FLASK_ENV', 'production').lower()
_SECRET = os.environ.get('SECRET_KEY')
_SECRET_TEMPORAIRE = False
if not _SECRET:
    if _ENV in ('dev', 'development', 'test', 'local'):
        import secrets as _secrets
        _SECRET = _secrets.token_urlsafe(48)
        _SECRET_TEMPORAIRE = True
    else:
        raise RuntimeError(
            "SECRET_KEY est obligatoire. Definissez-la dans l'environnement "
            "(Render > Environment, ou un fichier .env local). "
            "Generatez-la avec : python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )


class Config:
    """Configuration de l'application Flask."""

    SECRET_KEY = _SECRET
    # Vrai uniquement si la clé a été générée à la volée (dev/test) : dans ce
    # cas les sessions sont invalidées à chaque redémarrage, ce qui est
    # acceptable en développement et JAMAIS acceptable en production.
    SECRET_KEY_EPHEMERAL = _SECRET_TEMPORAIRE


    # Base de données — utiliser DATABASE_URL en production (ex: PostgreSQL, MySQL)
    # Par défaut, SQLite local pour le développement
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///' + os.path.join(basedir, 'antivol.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configuration des notifications
    # NTFY_URL : Leave vide pour utiliser https://ntfy.sh (gratuit, sans inscription).
    # Pour un serveur ntfy auto-hébergé, définir NTFY_URL dans l'environnement.
    NTFY_URL = (os.environ.get('NTFY_URL') or 'https://ntfy.sh').rstrip('/')
    FCM_SERVER_KEY = os.environ.get('FCM_SERVER_KEY') or ''
    # FIREBASE_SERVICE_ACCOUNT : chemin du fichier de clé, ou le JSON lui-même
    # (Render). Un chemin relatif est résolu depuis la racine du projet pour
    # être indépendant du répertoire de travail de gunicorn.
    _fsa = os.environ.get('FIREBASE_SERVICE_ACCOUNT') or 'firebase-service-account.json'
    FIREBASE_SERVICE_ACCOUNT = (
        _fsa if _fsa.lstrip().startswith('{')
        else os.path.join(basedir, _fsa)
    )
    SMS_API_KEY = os.environ.get('SMS_API_KEY') or ''

    # Twilio — SMS d'urgence vers les contacts d'urgence.
    # Les trois variables doivent être définies ENSEMBLE pour que l'envoi soit
    # tenté ; sinon la fonctionnalité est désactivée proprement (aucun secret
    # deviné, aucun appel réseau inutile).
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID') or ''
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN') or ''
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER') or ''

    # Secret de signature des commandes push (voir app/commandes.py).
    # Si absent, un secret est dérivé de SECRET_KEY : les messages restent
    # signés, mais la rotation de SECRET_KEY invalide les commandes en cours.
    COMMAND_SIGNING_KEY = os.environ.get('COMMAND_SIGNING_KEY') or _SECRET

    # Sécurité
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    # Anti-CSRF cross-site : indispensable car la même API est appelée depuis
    # le site web ET depuis l'application mobile (cross-origin).
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    # Cookie en HTTPS par défaut (Render/production). Mettre SESSION_COOKIE_SECURE=false
    # dans l'environnement pour autoriser le développement local en HTTP.
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'true').strip().lower() not in (
        '0', 'false', 'non', 'no',
    )
    # Durée de vie de la session « se souvenir de moi » (30 jours).
    REMEMBER_COOKIE_DURATION = 30 * 24 * 3600
    # Durée de vie de la session navigateur (12 h).
    PERMANENT_SESSION_LIFETIME = 12 * 3600

    # Origines autorisées à appeler l'API (CORS). Plusieurs domaines peuvent
    # être fournis, séparés par des virgules.
    CORS_ORIGINS = [
        o.strip() for o in (
            os.environ.get('CORS_ORIGINS')
            or 'https://antivol.onrender.com'
        ).split(',') if o.strip()
    ]

    # En-têtes de sécurité HTTP. they are set in create_app().
    SECURITY_HEADERS = True

    # Active le mode test : court-circuite les appels réseau (ntfy, FCM, Twilio).
    ANTIVOL_TEST_MODE = os.environ.get('ANTIVOL_TEST_MODE', '').strip().lower() in (
        '1', 'true', 'yes', 'on',
    )

    # Internationalisation — toutes les langues du monde
    BABEL_DEFAULT_LOCALE = 'fr'
    LANGUAGES = [
        'fr', 'en', 'es', 'pt', 'de', 'it', 'nl', 'ru', 'zh', 'ja',
        'ko', 'ar', 'hi', 'bn', 'pa', 'ta', 'te', 'mr', 'gu', 'kn',
        'ml', 'or', 'as', 'mai', 'ne', 'si', 'ur', 'fa', 'ps', 'ku',
        'tr', 'az', 'uz', 'kk', 'ky', 'tk', 'mn', 'ka', 'hy', 'he',
        'am', 'ti', 'om', 'so', 'sw', 'ha', 'yo', 'ig', 'zu', 'xh',
        'af', 'st', 'tn', 'ss', 'nr', 'rw', 'rn', 'lg',
        'ny', 'mg', 'sg', 'ee', 'bm', 'ff', 'wo', 'gn', 'ay', 'qu',
        'nv', 'oj', 'cr', 'iu', 'kl', 'sm', 'to', 'mi', 'haw', 'fj',
        'gl', 'ca', 'eu', 'oc', 'co', 'sc', 'rm', 'wa', 'fy', 'li',
        'lb', 'nds', 'als', 'vec', 'pms', 'lmo', 'nap', 'scn', 'srd',
        'ro', 'bg', 'mk', 'sr', 'hr', 'sl', 'bs', 'sq', 'el', 'pl',
        'cs', 'sk', 'hu', 'et', 'lv', 'lt', 'fi', 'sv', 'no', 'da',
        'is', 'ga', 'gd', 'cy', 'br', 'kw', 'gv', 'mt', 'be', 'uk',
        'th', 'lo', 'my', 'km', 'vi', 'tl', 'id', 'ms', 'jw', 'su',
        'ceb', 'ilo', 'hil', 'war', 'pam', 'pag', 'mrw', 'tsg', 'ak',
        'bem', 'tum', 'lua', 'lun',         'nso', 'ch', 'bcl',
        'mfe', 'ht', 'gcr', 'pap', 'jam', 'srn', 'nov', 'ina', 'epo'
    ]

    LANGUAGE_NAMES = {
        'fr': 'Français', 'en': 'English', 'es': 'Español', 'pt': 'Português',
        'de': 'Deutsch', 'it': 'Italiano', 'nl': 'Nederlands', 'ru': 'Русский',
        'zh': '中文', 'ja': '日本語', 'ko': '한국어', 'ar': 'العربية',
        'hi': 'हिन्दी', 'bn': 'বাংলা', 'pa': 'ਪੰਜਾਬੀ', 'ta': 'தமிழ்',
        'te': 'తెలుగు', 'mr': 'मराठी', 'gu': 'ગુજરાતી', 'kn': 'ಕನ್ನಡ',
        'ml': 'മലയാളം', 'or': 'ଓଡ଼ିଆ', 'as': 'অসমীয়া', 'mai': 'मैथिली',
        'ne': 'नेपाली', 'si': 'සිංහල', 'ur': 'اردو', 'fa': 'فارسی',
        'ps': 'پښتو', 'ku': 'Kurdî', 'tr': 'Türkçe', 'az': 'Azərbaycanca',
        'uz': "O'zbek", 'kk': 'Қазақша', 'ky': 'Кыргызча', 'tk': 'Türkmen',
        'mn': 'Монгол', 'ka': 'ქართული', 'hy': 'Հայերեն', 'he': 'עברית',
        'am': 'አማርኛ', 'ti': 'ትግርኛ', 'om': 'Afaan Oromoo', 'so': 'Soomaali',
        'sw': 'Kiswahili', 'ha': 'Hausa', 'yo': 'Yorùbá', 'ig': 'Igbo',
        'zu': 'isiZulu', 'xh': 'isiXhosa', 'af': 'Afrikaans', 'st': 'Sesotho',
        'tn': 'Setswana', 'ts': 'Xitsonga', 'ss': 'SiSwati', 've': 'Tshivenḓa',
        'nr': 'isiNdebele', 'rw': 'Kinyarwanda', 'rn': 'Kirundi', 'lg': 'Luganda',
        'ny': 'Chichewa', 'mg': 'Malagasy', 'sg': 'Sängö', 'ee': 'Eʋegbe',
        'bm': 'Bamanankan', 'ff': 'Fulfulde', 'wo': 'Wolof', 'gn': 'Guarani',
        'ay': 'Aymara', 'qu': 'Runasimi', 'nv': 'Diné bizaad', 'oj': 'Ojibwemowin',
        'cr': 'ᓀᐦᐃᔭᐍᐏᐣ', 'iu': 'ᐃᓄᒃᑎᑐᑦ', 'kl': 'Kalaallisut',
        'sm': 'Gagana Samoa', 'to': 'Lea faka-Tonga', 'mi': 'Te Reo Māori',
        'haw': 'ʻŌlelo Hawaiʻi', 'fj': 'Na Vosa Vakaviti',
        'gl': 'Galego', 'ca': 'Català', 'eu': 'Euskara', 'oc': 'Occitan',
        'co': 'Corsu', 'sc': 'Sardu', 'rm': 'Rumantsch', 'wa': 'Walon',
        'fy': 'Frysk', 'li': 'Limburgs', 'lb': 'Lëtzebuergesch',
        'nds': 'Plattdüütsch', 'als': 'Alemannisch', 'vec': 'Vèneto',
        'pms': 'Piemontèis', 'lmo': 'Lombard', 'nap': 'Napulitano',
        'scn': 'Sicilianu', 'srd': 'Sardu',
        'ro': 'Română', 'bg': 'Български', 'mk': 'Македонски',
        'sr': 'Српски', 'hr': 'Hrvatski', 'sl': 'Slovenščina',
        'bs': 'Bosanski', 'sq': 'Shqip', 'el': 'Ελληνικά', 'pl': 'Polski',
        'cs': 'Čeština', 'sk': 'Slovenčina', 'hu': 'Magyar',
        'et': 'Eesti', 'lv': 'Latviešu', 'lt': 'Lietuvių',
        'fi': 'Suomi', 'sv': 'Svenska', 'no': 'Norsk', 'da': 'Dansk',
        'is': 'Íslenska', 'ga': 'Gaeilge', 'gd': 'Gàidhlig', 'cy': 'Cymraeg',
        'br': 'Brezhoneg', 'kw': 'Kernewek', 'gv': 'Gaelg', 'mt': 'Malti',
        'be': 'Беларуская', 'uk': 'Українська',
        'th': 'ไทย', 'lo': 'ລາວ', 'my': 'မြန်မာဘာသာ', 'km': 'ខ្មែរ',
        'vi': 'Tiếng Việt', 'tl': 'Tagalog', 'id': 'Bahasa Indonesia',
        'ms': 'Bahasa Melayu', 'jw': 'Basa Jawa', 'su': 'Basa Sunda',
        'ceb': 'Cebuano', 'ilo': 'Iloko', 'hil': 'Hiligaynon',
        'war': 'Winaray', 'pam': 'Kapampangan', 'pag': 'Pangasinan',
        'mrw': 'Maguindanao', 'tsg': 'Tausug', 'ak': 'Akan',
        'bem': 'Ichibemba', 'tum': 'Chitumbuka', 'lua': 'Tshiluba',
        'lun': 'ChiLunda', 'nso': 'Sesotho sa Leboa',
        'ch': 'Chamoru', 'bcl': 'Bicolano',
        'mfe': 'Kreol Morisien', 'ht': 'Kreyòl Ayisyen',
        'gcr': 'Kriyòl Gwiyannen', 'pap': 'Papiamentu',
        'jam': 'Jamaican Creole', 'srn': 'Sranantongo',
        'nov': 'Novial', 'ina': 'Interlingua', 'epo': 'Esperanto'
    }
