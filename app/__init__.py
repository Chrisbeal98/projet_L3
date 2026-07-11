"""
Package principal de l'application Anti-Vol Intelligent.
Utilise le pattern App Factory de Flask.
"""

from datetime import datetime, timezone

from flask import Flask, session, redirect, request, url_for, flash, render_template, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
from flask_babel import Babel, lazy_gettext as _l
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()
cors = CORS()
babel = Babel()


import logging
import os
import sys

# ─── Logger dédié pour les requêtes HTTP (indépendant de werkzeug) ───
_request_log = logging.getLogger('antivol.http')
_request_log.setLevel(logging.INFO)
if not _request_log.handlers:
    _handler = logging.StreamHandler(sys.__stdout__)
    _handler.setFormatter(logging.Formatter('%(message)s'))
    _request_log.addHandler(_handler)
_request_log.propagate = False

# ─── Forcer werkzeug à logger les requêtes via notre handler ───
logging.getLogger('werkzeug').setLevel(logging.WARNING)


def create_app(config_class=Config):
    """Crée et configure l'instance Flask."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialiser les extensions
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": ["https://antivol.onrender.com"]}})

    # Initialiser Babel (i18n)
    def get_locale():
        from babel.core import Locale, UnknownLocaleError
        def _is_valid_locale(locale):
            try:
                Locale.parse(locale)
                return True
            except UnknownLocaleError:
                return False
        lang = session.get('lang')
        if lang and lang in app.config.get('LANGUAGES', ['fr']) and _is_valid_locale(lang):
            return lang
        best = request.accept_languages.best_match(app.config.get('LANGUAGES', ['fr']))
        if best and _is_valid_locale(best):
            return best
        return app.config.get('BABEL_DEFAULT_LOCALE', 'fr')

    babel.init_app(app, locale_selector=get_locale)

    # ─── Log des requêtes HTTP dans le terminal ───
    import os as _os
    _logfile = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'server_req.log'), 'a', encoding='utf-8')
    @app.before_request
    def log_request_start():
        _logfile.write(f"[REQ] {request.method} {request.path}\n")
        _logfile.flush()
        print(f"[REQ] {request.method} {request.path}", file=sys.stderr)
    @app.after_request
    def log_request(response):
        method = request.method
        path = request.path
        code = response.status_code
        ip = request.remote_addr or '?'
        msg = f"  [{code}] {method} {path} [{ip}]"
        _logfile.write(msg + "\n")
        _logfile.flush()
        print(msg)
        return response

    # Injecter get_locale, langues et noms dans le contexte Jinja2
    @app.context_processor
    def inject_locale():
        current_lang = get_locale()
        return dict(
            get_locale=get_locale,
            current_lang=current_lang,
            LANGUAGES=app.config.get('LANGUAGES', ['fr']),
            LANGUAGE_NAMES=app.config.get('LANGUAGE_NAMES', {})
        )

    # ─── Historique de navigation ───
    ENDPOINT_INFO = {
        'dashboard.index':           {'titre': 'Tableau de bord', 'icone': 'layout-dashboard'},
        'dashboard.appareils':       {'titre': 'Appareils', 'icone': 'smartphone'},
        'dashboard.alertes':         {'titre': 'Alertes', 'icone': 'bell-ring'},
        'dashboard.carte':           {'titre': 'Géolocalisation', 'icone': 'map-pin'},
        'dashboard.admin':           {'titre': 'Administration', 'icone': 'settings'},
        'dashboard.profil':          {'titre': 'Profil', 'icone': 'user'},
        'dashboard.mobile':          {'titre': 'Simulation Mobile', 'icone': 'smartphone'},
        'dashboard.lock_by_code':    {'titre': 'Verrouillage par code', 'icone': 'lock'},
    }

    PAGES_EXCLUES = {'static', 'set_language', 'auth.login', 'auth.register', 'auth.reset_password'}

    @app.before_request
    def enregistrer_historique():
        from flask_login import current_user
        from app.models import HistoriqueNavigation
        if not current_user.is_authenticated:
            return
        endpoint = request.endpoint
        if not endpoint or endpoint in PAGES_EXCLUES or endpoint.startswith('api.'):
            return
        info = ENDPOINT_INFO.get(endpoint, {'titre': endpoint.split('.')[-1].replace('_', ' ').title(), 'icone': 'file-text'})
        try:
            # Supprimer les entrées dépassant la limite (max 15 par utilisateur)
            nb = HistoriqueNavigation.query.filter_by(user_id=current_user.id).count()
            if nb >= 15:
                trop_ancien = HistoriqueNavigation.query.filter_by(user_id=current_user.id)\
                    .order_by(HistoriqueNavigation.date_visite.asc()).first()
                if trop_ancien:
                    db.session.delete(trop_ancien)
            # Vérifier si la dernière entrée est identique (même page consécutive)
            dernier = HistoriqueNavigation.query.filter_by(user_id=current_user.id)\
                .order_by(HistoriqueNavigation.date_visite.desc()).first()
            if dernier and dernier.endpoint == endpoint:
                dernier.date_visite = datetime.now(timezone.utc)
            else:
                entry = HistoriqueNavigation(
                    user_id=current_user.id,
                    endpoint=endpoint,
                    titre=info['titre'],
                    icone=info['icone'],
                    url=request.path
                )
                db.session.add(entry)
            db.session.commit()
        except Exception:
            db.session.rollback()

    @app.context_processor
    def injecter_historique():
        from flask_login import current_user
        from app.models import HistoriqueNavigation
        historique = []
        if current_user.is_authenticated:
            historique = HistoriqueNavigation.query.filter_by(user_id=current_user.id)\
                .order_by(HistoriqueNavigation.date_visite.desc()).limit(10).all()
        return dict(historique_navigation=historique)

    # Config Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = _l('Veuillez vous connecter pour accéder à cette page.')
    login_manager.login_message_category = 'warning'

    # Enregistrer les blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    # Exempter l'API du CSRF pour les appels REST
    csrf.exempt(api_bp)

    # ─── Route changement de langue ───
    @app.route('/set-language/<lang>')
    def set_language(lang):
        if lang in app.config.get('LANGUAGES', ['fr']):
            session['lang'] = lang
        return redirect(request.referrer or url_for('dashboard.index'))

    # ─── Filtre Jinja2 « timeago » ───
    @app.template_filter('timeago')
    def timeago_filter(date):
        now = datetime.now(timezone.utc)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        diff = now - date
        secondes = int(diff.total_seconds())
        if secondes < 60:
            return _l('à l\'instant')
        minutes = secondes // 60
        if minutes < 60:
            return _l('il y a %(min)s min', min=minutes)
        heures = minutes // 60
        if heures < 24:
            return _l('il y a %(h)s h', h=heures)
        jours = heures // 24
        if jours < 7:
            return _l('il y a %(j)s j', j=jours)
        return date.strftime('%d/%m')

    # ─── Gestion des erreurs ───
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        _log_erreur('CSRF', request.url, str(e.description), request)
        flash('Le formulaire a expiré. Veuillez réessayer.', 'warning')
        return redirect(request.referrer or url_for('dashboard.index'))

    @app.errorhandler(404)
    def page_not_found(e):
        _log_erreur('404', request.url, 'Page non trouvée', request)
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Endpoint non trouvé'}), 404
        return render_template('base.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        _log_erreur('500', request.url, str(e), request)
        db.session.rollback()
        return render_template('base.html'), 500

    def _log_erreur(type_err, url, description, req):
        """Enregistre une erreur dans le journal."""
        try:
            from flask_login import current_user
            from app.models import JournalErreur
            erreur = JournalErreur(
                user_id=current_user.id if current_user.is_authenticated else None,
                type_erreur=type_err,
                url=url[:500] if url else '',
                description=description[:255] if description else '',
                adresse_ip=req.remote_addr,
                navigateur=str(req.user_agent)[:200]
            )
            db.session.add(erreur)
            db.session.commit()
        except Exception:
            db.session.rollback()

    return app


def envoyer_notification_push(user_id, title, body, data=None):
    """Envoie une notification push via ntfy.sh + FCM."""
    sent = False

    ntfy_url = current_app.config.get('NTFY_URL', 'https://ntfy.sh')
    topic = f"antivol-u{user_id}"

    ntfy_title = title
    if data and data.get('command'):
        ntfy_title = data['command']

    payload = {
        "topic": topic,
        "title": ntfy_title,
        "message": body,
        "priority": 5,
    }

    try:
        import requests as req
        req.post(ntfy_url, json=payload, timeout=5)

        if data and data.get('type') == 'community_alert':
            community_payload = {**payload, "topic": "antivol-community", "title": title}
            req.post(ntfy_url, json=community_payload, timeout=5)

        sent = True
    except Exception:
        pass

    try:
        _envoyer_fcm_push(user_id, title, body, data)
        sent = True
    except Exception:
        pass

    return sent


def _envoyer_fcm_push(user_id, title, body, data=None):
    """Envoie une notification push FCM via firebase-admin."""
    import os

    service_account_json = current_app.config.get('FIREBASE_SERVICE_ACCOUNT', '')
    if not service_account_json:
        return

    try:
        import firebase_admin
        from firebase_admin import credentials, messaging

        if not firebase_admin._apps:
            if os.path.exists(service_account_json):
                cred = credentials.Certificate(service_account_json)
            else:
                import tempfile, json as json_mod
                sa_info = json_mod.loads(service_account_json)
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json_mod.dump(sa_info, f)
                    cred = credentials.Certificate(f.name)
            firebase_admin.initialize_app(cred)

        from app.models import FcmToken
        tokens = FcmToken.query.filter_by(user_id=user_id).all()
        if not tokens:
            return

        fcm_tokens = [t.token for t in tokens]

        command = data.get('command') if data else None

        notification = messaging.Notification(title=title, body=body)
        android_config = messaging.AndroidConfig(
            priority='high',
            notification=messaging.AndroidNotification(
                title=title,
                body=body,
                click_action='OPENMainActivity',
            ),
        )
        data_payload = {}
        if command:
            data_payload['command'] = command
        if data:
            for k, v in data.items():
                if v is not None:
                    data_payload[str(k)] = str(v)

        response = messaging.send_each(
            messaging.MulticastMessage(
                notification=notification,
                android=android_config,
                data=data_payload,
                tokens=fcm_tokens,
            )
        )

        if response.failure_count > 0:
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    from app import db
                    db.session.delete(tokens[idx])
            db.session.commit()

    except Exception:
        pass


def log_activite(user_id, action, details=None):
    """Enregistre une activité utilisateur. À appeler depuis les routes."""
    from flask import request
    from app.models import ActiviteUtilisateur
    try:
        activite = ActiviteUtilisateur(
            user_id=user_id,
            action=action,
            details=details[:255] if details else None,
            adresse_ip=request.remote_addr,
            navigateur=str(request.user_agent)[:200]
        )
        db.session.add(activite)
        db.session.commit()
    except Exception:
        db.session.rollback()
