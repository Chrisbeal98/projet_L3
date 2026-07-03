"""
Routes d'authentification.
Inscription, connexion, déconnexion.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import gettext as _
from app import db, bcrypt, log_activite
from app.models import User
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)

# ─── Anti-bot : limiteur de taux simple (IP → timestamp) ───
_tentatives_connexion = {}
_tentatives_inscription = {}

def _verifier_rate_limit(ip, stockage, limite=5, fenetre=300):
    """Vérifie si l'IP a dépassé la limite de tentatives."""
    maintenant = datetime.now()
    if ip in stockage:
        stockage[ip] = [t for t in stockage[ip] if maintenant - t < timedelta(seconds=fenetre)]
        if len(stockage[ip]) >= limite:
            return False
        stockage[ip].append(maintenant)
    else:
        stockage[ip] = [maintenant]
    return True

def _nettoyer_rate_limit(stockage, fenetre=300):
    """Nettoie les entrées expirées."""
    maintenant = datetime.now()
    a_supprimer = [ip for ip, ts in stockage.items() if maintenant - ts[-1] > timedelta(seconds=fenetre)]
    for ip in a_supprimer:
        del stockage[ip]

import time as _time

def _est_honeypot_rempli(form):
    """Vérifie si le champ honeypot caché a été rempli (par un robot)."""
    return bool(request.form.get('website', '').strip())

def _verifier_js_challenge(form):
    """Vérifie que le formulaire a été soumis avec JavaScript activé (anti-bot)."""
    js_val = form.get('_js', '').strip()
    ts_str = form.get('_ts', '').strip()
    if not js_val or not ts_str:
        return False
    try:
        ts_val = float(ts_str)
    except ValueError:
        return False
    if _time.time() - ts_val < 1.5:
        return False
    s = f"antivol-js-{ts_str}"
    attendu = ''.join(format(ord(c), '02x') for c in s)[:16]
    return js_val == attendu


@auth_bp.route('/')
def accueil():
    """Page d'accueil — Splash avec logo."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    return render_template('welcome.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        # Anti-bot : honeypot
        if _est_honeypot_rempli(request.form):
            flash(_('Tentative de robot détectée.'), 'danger')
            return render_template('login.html')

        # Anti-bot : validation JavaScript
        if not _verifier_js_challenge(request.form):
            flash(_('JavaScript requis. Veuillez activer JavaScript.'), 'danger')
            return render_template('login.html')

        # Anti-bot : rate limiting
        ip = request.remote_addr or 'unknown'
        if not _verifier_rate_limit(ip, _tentatives_connexion, limite=5, fenetre=300):
            flash(_('Trop de tentatives. Veuillez réessayer dans 5 minutes.'), 'danger')
            return render_template('login.html')

        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password_hash, password):
            _nettoyer_rate_limit(_tentatives_connexion)
            login_user(user, remember=True)
            log_activite(user.id, 'connexion', f'Connexion de {user.nom_complet}')
            next_page = request.args.get('next')
            flash(_('Connexion réussie ! Bienvenue.'), 'success')
            return redirect(next_page or url_for('dashboard.index'))
        else:
            flash(_('Email ou mot de passe incorrect.'), 'danger')

    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Page d'inscription."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        # Anti-bot : honeypot
        if _est_honeypot_rempli(request.form):
            flash(_('Tentative de robot détectée.'), 'danger')
            return render_template('register.html')

        # Anti-bot : validation JavaScript
        if not _verifier_js_challenge(request.form):
            flash(_('JavaScript requis. Veuillez activer JavaScript.'), 'danger')
            return render_template('register.html')

        # Anti-bot : rate limiting
        ip = request.remote_addr or 'unknown'
        if not _verifier_rate_limit(ip, _tentatives_inscription, limite=3, fenetre=600):
            flash(_('Trop de tentatives. Veuillez réessayer dans 10 minutes.'), 'danger')
            return render_template('register.html')

        nom = request.form.get('nom', '').strip()
        prenom = request.form.get('prenom', '').strip()
        email = request.form.get('email', '').strip()
        telephone = request.form.get('telephone', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validations
        errors = []
        if not nom or not prenom or not email or not password:
            errors.append(_('Tous les champs obligatoires doivent être remplis.'))
        if password != confirm_password:
            errors.append(_('Les mots de passe ne correspondent pas.'))
        if len(password) < 6:
            errors.append(_('Le mot de passe doit contenir au moins 6 caractères.'))
        if User.query.filter_by(email=email).first():
            errors.append(_('Cet email est déjà utilisé.'))

        if errors:
            for error in errors:
                flash(error, 'danger')
        else:
            hashed_pw = bcrypt.generate_password_hash(password)
            user = User(
                nom=nom,
                prenom=prenom,
                email=email,
                telephone=telephone,
                password_hash=hashed_pw
            )
            db.session.add(user)
            db.session.commit()
            log_activite(user.id, 'inscription', f'Nouveau compte : {user.email}')
            flash(_('Compte créé avec succès ! Connectez-vous.'), 'success')
            return redirect(url_for('auth.login'))

    return render_template('register.html')


@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Page de réinitialisation du mot de passe."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        # Anti-bot : honeypot
        if _est_honeypot_rempli(request.form):
            flash(_('Tentative de robot détectée.'), 'danger')
            return render_template('reset_password.html')

        # Anti-bot : validation JavaScript
        if not _verifier_js_challenge(request.form):
            flash(_('JavaScript requis. Veuillez activer JavaScript.'), 'danger')
            return render_template('reset_password.html')

        # Anti-bot : rate limiting
        ip = request.remote_addr or 'unknown'
        if not _verifier_rate_limit(ip, _tentatives_connexion, limite=3, fenetre=600):
            flash(_('Trop de tentatives. Veuillez réessayer dans 10 minutes.'), 'danger')
            return render_template('reset_password.html')

        email = request.form.get('email', '').strip()
        telephone = request.form.get('telephone', '').strip()
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        user = User.query.filter_by(email=email).first()

        # Vérifications
        errors = []
        if not user:
            errors.append(_('Aucun compte trouvé avec cet email.'))
        elif not user.telephone or user.telephone != telephone:
            errors.append(_('Le numéro de téléphone ne correspond pas à celui du compte.'))
        if not new_password:
            errors.append(_('Le nouveau mot de passe est obligatoire.'))
        elif len(new_password) < 6:
            errors.append(_('Le mot de passe doit contenir au moins 6 caractères.'))
        if new_password != confirm_password:
            errors.append(_('Les mots de passe ne correspondent pas.'))

        if errors:
            for error in errors:
                flash(error, 'danger')
        else:
            user.password_hash = bcrypt.generate_password_hash(new_password)
            db.session.commit()
            log_activite(user.id, 'reinitialisation_mdp', f'Mot de passe réinitialisé pour {user.email}')
            flash(_('Mot de passe réinitialisé avec succès ! Connectez-vous.'), 'success')
            return redirect(url_for('auth.login'))

    return render_template('reset_password.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Déconnexion."""
    log_activite(current_user.id, 'deconnexion', f'Déconnexion de {current_user.nom_complet}')
    logout_user()
    flash(_('Vous avez été déconnecté.'), 'info')
    return redirect(url_for('auth.login'))
