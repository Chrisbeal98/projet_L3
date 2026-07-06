import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Configuration de l'application Flask."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'antivol-systeme-secret-key-2026'

    # Base de données SQLite (pas de mot de passe, facile pour le développement)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'antivol.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Configuration des notifications
    NTFY_URL = os.environ.get('NTFY_URL') or 'https://ntfy.sh'
    # Pour ntfy.sh, définir la variable d'environnement NTFY_URL
    # Laisser vide pour utiliser https://ntfy.sh (gratuit, sans inscription)
    FCM_SERVER_KEY = os.environ.get('FCM_SERVER_KEY') or ''
    SMS_API_KEY = os.environ.get('SMS_API_KEY') or ''

    # Sécurité
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True

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
