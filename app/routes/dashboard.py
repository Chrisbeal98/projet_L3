"""
Routes du tableau de bord et des fonctionnalités principales.
Inclut toutes les vues : dashboard, appareils, alertes, carte, profil, admin.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_babel import gettext as _
import secrets
import random
import string
from app import db, bcrypt, log_activite, envoyer_notification_push
from app.models import (
    User, Appareil, Alerte, Notification,
    ZoneRisque, ActiviteUtilisateur, JournalErreur, FcmToken
)
from datetime import datetime, timezone, timedelta

def generer_code_verrouillage():
    """Génère un code de verrouillage unique à 4 chiffres."""
    while True:
        code = ''.join(random.choices(string.digits, k=4))
        if not Appareil.query.filter_by(code_verrouillage=code).first():
            return code


def generer_code_pin():
    """Génère un code PIN unique à 4 chiffres."""
    while True:
        code = ''.join(random.choices(string.digits, k=4))
        if not Appareil.query.filter_by(code_ussd=code).first():
            return code


dashboard_bp = Blueprint('dashboard', __name__)


# ═══════════════════════════════════════════════
# TABLEAU DE BORD
# ═══════════════════════════════════════════════
@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Page d'accueil — Vue d'ensemble."""
    if current_user.role == 'admin':
        total_appareils = Appareil.query.count()
        total_alertes = Alerte.query.filter_by(statut='en_cours').count()
        total_verrouilles = Appareil.query.filter_by(statut='verrouillé').count()
        total_voles = Appareil.query.filter_by(statut='volé').count()
        total_utilisateurs = User.query.count()
        alertes_recentes = Alerte.query.order_by(Alerte.date_creation.desc()).limit(10).all()
        appareils_recents = Appareil.query.order_by(Appareil.date_enregistrement.desc()).limit(10).all()
    else:
        total_appareils = Appareil.query.filter_by(user_id=current_user.id).count()
        total_alertes = Alerte.query.filter_by(user_id=current_user.id, statut='en_cours').count()
        total_verrouilles = Appareil.query.filter_by(user_id=current_user.id, statut='verrouillé').count()
        total_voles = Appareil.query.filter_by(user_id=current_user.id, statut='volé').count()
        total_utilisateurs = None
        alertes_recentes = (
            Alerte.query.filter_by(user_id=current_user.id)
            .order_by(Alerte.date_creation.desc())
            .limit(10)
            .all()
        )
        appareils_recents = (
            Appareil.query.filter_by(user_id=current_user.id)
            .order_by(Appareil.date_enregistrement.desc())
            .all()
        )

    # Erreurs récentes (admin seulement)
    if current_user.role == 'admin':
        erreurs_recentes = JournalErreur.query.filter_by(resolu=False).order_by(JournalErreur.date.desc()).limit(5).all()
        erreurs_non_resolues = JournalErreur.query.filter_by(resolu=False).count()
        erreurs_data = [{
            'id': e.id,
            'type_erreur': e.type_erreur,
            'url': e.url,
            'description': e.description,
            'adresse_ip': e.adresse_ip,
            'navigateur': e.navigateur,
            'date': e.date.strftime('%d/%m/%Y %H:%M') if e.date else '—',
            'resolu': e.resolu,
            'utilisateur': {
                'prenom': e.utilisateur.prenom,
                'nom': e.utilisateur.nom
            } if e.utilisateur else None
        } for e in erreurs_recentes]
    else:
        erreurs_recentes = []
        erreurs_non_resolues = 0
        erreurs_data = []

    return render_template('dashboard.html',
                           total_appareils=total_appareils,
                           total_alertes=total_alertes,
                           total_verrouilles=total_verrouilles,
                           total_voles=total_voles,
                           total_utilisateurs=total_utilisateurs,
                           alertes_recentes=alertes_recentes,
                           appareils=appareils_recents,
                           erreurs_recentes=erreurs_recentes,
                           erreurs_data=erreurs_data,
                           erreurs_non_resolues=erreurs_non_resolues)


# ═══════════════════════════════════════════════
# GESTION DES APPAREILS
# ═══════════════════════════════════════════════
@dashboard_bp.route('/appareils')
@login_required
def appareils():
    """Page listant les appareils — utilise le template moderne devices.html."""
    if current_user.role == 'admin':
        appareils_liste = Appareil.query.all()
    else:
        appareils_liste = Appareil.query.filter_by(user_id=current_user.id).all()

    # Générer les codes pour les appareils qui n'en ont pas encore
    modifie = False
    for a in appareils_liste:
        if not a.code_verrouillage:
            a.code_verrouillage = generer_code_verrouillage()
            modifie = True
        if not a.code_ussd:
            a.code_ussd = generer_code_pin()
            modifie = True
    if modifie:
        db.session.commit()

    return render_template('devices.html', appareils=appareils_liste)


@dashboard_bp.route('/appareils/ajouter', methods=['POST'])
@login_required
def ajouter_appareil():
    """Ajouter un nouvel appareil."""
    marque = request.form.get('marque', '').strip()
    modele = request.form.get('modele', '').strip()
    imei = request.form.get('imei', '').strip()
    systeme_os = request.form.get('systeme_os', '').strip()
    operateur = request.form.get('operateur', '').strip()
    numero_telephone = request.form.get('numero_telephone', '').strip()

    # Validations
    if not marque or not modele or not imei:
        flash(_('La marque, le modèle et l\'IMEI sont obligatoires.'), 'danger')
        return redirect(url_for('dashboard.appareils'))

    if Appareil.query.filter_by(imei=imei).first():
        flash(_('Un appareil avec cet IMEI existe déjà.'), 'danger')
        return redirect(url_for('dashboard.appareils'))

    appareil = Appareil(
        user_id=current_user.id,
        marque=marque,
        modele=modele,
        imei=imei,
        systeme_os=systeme_os or None,
        operateur=operateur or None,
        numero_telephone=numero_telephone or None,
        code_verrouillage=generer_code_verrouillage(),
        code_ussd=generer_code_pin()
    )
    db.session.add(appareil)
    db.session.commit()

    log_activite(current_user.id, 'ajout_appareil', f'{marque} {modele} (IMEI: {imei})')
    flash(_('Appareil enregistré avec succès !'), 'success')
    return redirect(url_for('dashboard.appareils'))


@dashboard_bp.route('/appareils/<int:id>/verrouiller', methods=['POST'])
@login_required
def verrouiller_appareil(id):
    """Verrouiller un appareil à distance."""
    appareil = db.get_or_404(Appareil, id)

    # Vérifier que l'utilisateur est le propriétaire ou admin
    if appareil.user_id != current_user.id and current_user.role != 'admin':
        flash(_('Vous n\'êtes pas autorisé à effectuer cette action.'), 'danger')
        return redirect(url_for('dashboard.appareils'))

    appareil.statut = 'verrouillé'
    db.session.commit()

    envoyer_notification_push(
        appareil.user_id,
        "ALERTE: " + appareil.marque + " " + appareil.modele + " verrouille",
        "Code de verrouillage applique depuis le tableau de bord. Suivez la position en temps reel.",
        {"appareil_id": str(appareil.id)}
    )

    tous = Appareil.query.filter(Appareil.id != appareil.id, Appareil.device_uuid != None).all()
    for autre in tous:
        if autre.user_id:
            envoyer_notification_push(
                autre.user_id,
                "VOL SIGNALE: " + appareil.marque + " " + appareil.modele,
                "Un telephone a ete declare vole! Restez vigilant.",
                {"appareil_id": str(appareil.id), "type": "community_alert"}
            )

    log_activite(current_user.id, 'verrouillage_appareil', f'{appareil.marque} {appareil.modele} verrouillé')
    flash(_('Appareil verrouillé à distance avec succès.'), 'success')
    return redirect(url_for('dashboard.appareils'))


@dashboard_bp.route('/appareils/<int:id>/deverrouiller', methods=['POST'])
@login_required
def deverrouiller_appareil(id):
    """Déverrouiller un appareil."""
    appareil = db.get_or_404(Appareil, id)

    if appareil.user_id != current_user.id and current_user.role != 'admin':
        flash(_('Vous n\'êtes pas autorisé à effectuer cette action.'), 'danger')
        return redirect(url_for('dashboard.appareils'))

    appareil.statut = 'actif'
    db.session.commit()

    log_activite(current_user.id, 'deverrouillage_appareil', f'{appareil.marque} {appareil.modele} déverrouillé')
    flash(_('Appareil déverrouillé avec succès.'), 'success')
    return redirect(url_for('dashboard.appareils'))


@dashboard_bp.route('/appareils/<int:id>/supprimer', methods=['POST'])
@login_required
def supprimer_appareil(id):
    """Supprimer un appareil."""
    appareil = db.get_or_404(Appareil, id)

    if appareil.user_id != current_user.id and current_user.role != 'admin':
        flash(_('Vous n\'êtes pas autorisé à effectuer cette action.'), 'danger')
        return redirect(url_for('dashboard.appareils'))

    nom_appareil = f'{appareil.marque} {appareil.modele}'
    db.session.delete(appareil)
    db.session.commit()

    log_activite(current_user.id, 'suppression_appareil', f'{nom_appareil} supprimé')
    flash(_('Appareil supprimé.'), 'success')
    return redirect(url_for('dashboard.appareils'))


@dashboard_bp.route('/appareils/reclamer', methods=['POST'])
@login_required
def reclamer_appareil():
    """Réclamer un appareil mobile en entrant son code de verrouillage."""
    code = request.form.get('code', '').strip()
    if not code:
        flash(_('Veuillez entrer un code de verrouillage.'), 'danger')
        return redirect(url_for('dashboard.appareils'))

    appareil = Appareil.query.filter_by(code_verrouillage=code).first()
    if not appareil:
        flash(_('Code invalide. Aucun appareil trouvé avec ce code.'), 'danger')
        return redirect(url_for('dashboard.appareils'))

    if appareil.user_id == current_user.id:
        flash(_('Cet appareil vous appartient déjà.'), 'info')
        return redirect(url_for('dashboard.appareils'))

    old_user = appareil.user_id
    appareil.user_id = current_user.id
    db.session.commit()

    log_activite(current_user.id, 'reclamation_appareil', f'{appareil.marque} {appareil.modele} (ancien user: {old_user})')
    flash(_('%(marque)s %(modele)s a été réclamé avec succès !', marque=appareil.marque, modele=appareil.modele), 'success')
    return redirect(url_for('dashboard.appareils'))


# ═══════════════════════════════════════════════
# GESTION DES ALERTES
# ═══════════════════════════════════════════════
@dashboard_bp.route('/alertes')
@login_required
def alertes():
    """Page listant les alertes — utilise le template moderne alerts.html."""
    if current_user.role == 'admin':
        alertes_liste = Alerte.query.order_by(Alerte.date_creation.desc()).all()
    else:
        alertes_liste = Alerte.query.filter_by(user_id=current_user.id).order_by(Alerte.date_creation.desc()).all()

    # Pré-calculer les stats pour éviter les problèmes avec selectattr Jinja
    en_cours = sum(1 for a in alertes_liste if a.statut == 'en_cours')
    traitees = sum(1 for a in alertes_liste if a.statut == 'traité')
    total = len(alertes_liste)

    return render_template('alerts.html',
                           alertes=alertes_liste,
                           en_cours=en_cours,
                           traitees=traitees,
                           total=total)


@dashboard_bp.route('/alertes/signaler', methods=['POST'])
@login_required
def signaler():
    """Signaler un vol, une perte ou une anomalie."""
    appareil_id = request.form.get('appareil_id')
    type_alerte = request.form.get('type_alerte', '').strip()
    description = request.form.get('description', '').strip()

    if not appareil_id or not type_alerte:
        flash(_('Veuillez sélectionner un appareil et un type d\'alerte.'), 'danger')
        return redirect(url_for('dashboard.alertes'))

    appareil = db.get_or_404(Appareil, int(appareil_id))

    # Vérifier que l'utilisateur est propriétaire
    if appareil.user_id != current_user.id:
        flash(_('Cet appareil ne vous appartient pas.'), 'danger')
        return redirect(url_for('dashboard.alertes'))

    # Déterminer la priorité selon le type
    priorite = 'critique' if type_alerte == 'vol' else 'haute' if type_alerte == 'perte' else 'moyenne'

    alerte = Alerte(
        user_id=current_user.id,
        appareil_id=appareil.id,
        type_alerte=type_alerte,
        description=description or None,
        statut='en_cours',
        priorite=priorite
    )
    db.session.add(alerte)

    # En cas de vol, verrouiller automatiquement l'appareil
    if type_alerte == 'vol':
        appareil.statut = 'volé'
    elif type_alerte == 'perte':
        appareil.statut = 'verrouillé'

    db.session.commit()

    # Créer une notification
    notif = Notification(
        alerte_id=alerte.id,
        type_notification='push',
        contenu=f'ALERTE {type_alerte.upper()} — {appareil.marque} {appareil.modele}',
        destinataire=current_user.email,
        statut='envoyé'
    )
    db.session.add(notif)
    db.session.commit()

    log_activite(
        current_user.id,
        'signalement_alerte',
        f'{type_alerte.capitalize()} — {appareil.marque} {appareil.modele}'
    )
    flash(_('Alerte signalée avec succès. L\'appareil a été sécurisé.'), 'success')
    return redirect(url_for('dashboard.alertes'))


@dashboard_bp.route('/alertes/<int:id>/resoudre', methods=['POST'])
@login_required
def resoudre_alerte(id):
    """Marquer une alerte comme résolue."""
    alerte = db.get_or_404(Alerte, id)

    if alerte.user_id != current_user.id and current_user.role != 'admin':
        flash(_('Vous n\'êtes pas autorisé à effectuer cette action.'), 'danger')
        return redirect(url_for('dashboard.alertes'))

    alerte.statut = 'traité'
    alerte.date_resolution = datetime.now(timezone.utc)

    # Remettre l'appareil en mode actif
    appareil = db.session.get(Appareil, alerte.appareil_id)
    if appareil and appareil.statut in ('volé', 'verrouillé'):
        appareil.statut = 'récupéré'

    db.session.commit()

    log_activite(current_user.id, 'resolution_alerte', f'Alerte #{alerte.id} résolue')
    flash(_('Alerte marquée comme résolue.'), 'success')
    return redirect(url_for('dashboard.alertes'))


# ═══════════════════════════════════════════════
# GÉOLOCALISATION
# ═══════════════════════════════════════════════
@dashboard_bp.route('/carte')
@login_required
def carte():
    """Page de géolocalisation avec carte Leaflet."""
    if current_user.role == 'admin':
        appareils_liste = Appareil.query.all()
    else:
        appareils_liste = Appareil.query.filter_by(user_id=current_user.id).all()

    zones_risque = ZoneRisque.query.all()

    return render_template('map.html',
                           appareils=appareils_liste,
                           zones_risque=zones_risque)


# ═══════════════════════════════════════════════
# SIMULATION MOBILE (Test verrouillage)
# ═══════════════════════════════════════════════
@dashboard_bp.route('/mobile')
def mobile():
    """Page simulant l'écran du téléphone pour tester le verrouillage."""
    return render_template('mobile.html')


@dashboard_bp.route('/download')
def download():
    """Page de téléchargement de l'application mobile."""
    return render_template('download.html')


@dashboard_bp.route('/download/apk')
def download_apk():
    """Téléchargement du fichier APK."""
    import os
    from flask import send_file, abort, current_app
    apk_path = os.path.join(current_app.root_path, 'static', 'antivol.apk')
    if os.path.exists(apk_path):
        return send_file(apk_path, mimetype='application/vnd.android.package-archive', as_attachment=True, download_name='antivol.apk')
    return render_template('download.html', apk_disponible=False)


# ═══════════════════════════════════════════════
# VERROUILLAGE PAR CODE
# ═══════════════════════════════════════════════
@dashboard_bp.route('/lock-by-code', methods=['GET', 'POST'])
def lock_by_code():
    """Page de verrouillage par code — accessible sans authentification.
    Utile pour verrouiller depuis un autre téléphone/navigateur."""
    result = None
    error = None
    appareil_info = None

    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        if not code:
            error = 'Veuillez entrer un code de verrouillage.'
        else:
            appareil = Appareil.query.filter_by(code_verrouillage=code).first()
            if not appareil:
                error = 'Code invalide. Aucun appareil trouvé.'
            elif appareil.statut in ('volé', 'verrouillé'):
                error = f'Cet appareil ({appareil.marque} {appareil.modele}) est déjà verrouillé.'
            else:
                appareil.statut = 'verrouillé'

                alerte = Alerte(
                    user_id=appareil.user_id,
                    appareil_id=appareil.id,
                    type_alerte='perte',
                    description='Verrouillé à distance via la page lock-by-code',
                    priorite='haute',
                    statut='en_cours'
                )
                db.session.add(alerte)
                db.session.commit()

                # Envoyer notification push au propriétaire
                envoyer_notification_push(
                    appareil.user_id,
                    '🔒 Appareil verrouillé',
                    f'{appareil.marque} {appareil.modele} a été verrouillé à distance.',
                    {'action': 'lock', 'appareil_id': str(appareil.id)}
                )

                # Broadcast communauté : prévenir tous les autres téléphones
                tous = Appareil.query.filter(Appareil.id != appareil.id, Appareil.device_uuid != None).all()
                for autre in tous:
                    if autre.user_id:
                        envoyer_notification_push(
                            autre.user_id,
                            "VOL SIGNALE: " + appareil.marque + " " + appareil.modele,
                            "Ce telephone a ete declare vole! Restez vigilant.",
                            {"appareil_id": str(appareil.id), "type": "community_alert"}
                        )

                result = 'succes'
                appareil_info = f"{appareil.marque} {appareil.modele}"

    return render_template('lock_by_code.html', result=result, error=error, appareil_info=appareil_info)



# ═══════════════════════════════════════════════
# PROFIL UTILISATEUR
# ═══════════════════════════════════════════════
@dashboard_bp.route('/profil')
@login_required
def profil():
    """Page de profil utilisateur."""
    appareils_liste = Appareil.query.filter_by(user_id=current_user.id).all()
    total_alertes = Alerte.query.filter_by(user_id=current_user.id).count()

    return render_template('profil.html',
                           appareils=appareils_liste,
                           total_alertes=total_alertes)


@dashboard_bp.route('/profil/modifier', methods=['POST'])
@login_required
def modifier_profil():
    """Modifier les informations du profil."""
    prenom = request.form.get('prenom', '').strip()
    nom = request.form.get('nom', '').strip()
    email = request.form.get('email', '').strip()
    telephone = request.form.get('telephone', '').strip()
    new_password = request.form.get('new_password', '')

    if not prenom or not nom or not email:
        flash(_('Le prénom, le nom et l\'email sont obligatoires.'), 'danger')
        return redirect(url_for('dashboard.profil'))

    # Vérifier que l'email n'est pas déjà pris par un autre utilisateur
    existing = User.query.filter(User.email == email, User.id != current_user.id).first()
    if existing:
        flash(_('Cet email est déjà utilisé par un autre compte.'), 'danger')
        return redirect(url_for('dashboard.profil'))

    current_user.prenom = prenom
    current_user.nom = nom
    current_user.email = email
    current_user.telephone = telephone or None

    if new_password:
        if len(new_password) < 6:
            flash(_('Le mot de passe doit contenir au moins 6 caractères.'), 'danger')
            return redirect(url_for('dashboard.profil'))
        current_user.password_hash = bcrypt.generate_password_hash(new_password)

    db.session.commit()

    log_activite(current_user.id, 'modification_profil', f'Profil mis à jour par {current_user.nom_complet}')
    flash(_('Profil mis à jour avec succès !'), 'success')
    return redirect(url_for('dashboard.profil'))


# ═══════════════════════════════════════════════
# ADMINISTRATION (Admin uniquement)
# ═══════════════════════════════════════════════
@dashboard_bp.route('/admin')
@login_required
def admin():
    """Page d'administration — analytique, activités, erreurs, utilisateurs."""
    if current_user.role != 'admin':
        flash(_('Accès réservé aux administrateurs.'), 'danger')
        return redirect(url_for('dashboard.index'))

    # Statistiques globales
    utilisateurs = User.query.all()
    total_appareils = Appareil.query.count()
    total_alertes = Alerte.query.count()
    alertes_en_cours = Alerte.query.filter_by(statut='en_cours').count()

    # Utilisateurs actifs aujourd'hui (qui ont une activité aujourd'hui)
    debut_journee = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    utilisateurs_actifs = db.session.query(
        db.func.count(db.func.distinct(ActiviteUtilisateur.user_id))
    ).filter(ActiviteUtilisateur.date >= debut_journee).scalar() or 0

    # Nouveaux ce mois
    debut_mois = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nouveaux_mois = User.query.filter(User.date_creation >= debut_mois).count()

    # Activités récentes
    activites_recentes = ActiviteUtilisateur.query.order_by(
        ActiviteUtilisateur.date.desc()
    ).limit(50).all()

    # Erreurs
    erreurs_recentes = JournalErreur.query.order_by(JournalErreur.date.desc()).limit(30).all()
    erreurs_non_resolues = JournalErreur.query.filter_by(resolu=False).count()

    # Données JSON pour le modal de détails
    erreurs_data = [{
        'id': e.id,
        'type_erreur': e.type_erreur,
        'url': e.url,
        'description': e.description,
        'adresse_ip': e.adresse_ip,
        'navigateur': e.navigateur,
        'date': e.date.strftime('%d/%m/%Y %H:%M') if e.date else '—',
        'resolu': e.resolu,
        'utilisateur': {
            'prenom': e.utilisateur.prenom,
            'nom': e.utilisateur.nom
        } if e.utilisateur else None
    } for e in erreurs_recentes]

    # ─── Données analytiques ───

    # Connexions par jour (7 derniers jours)
    labels_jours = []
    connexions_par_jour = []
    for i in range(6, -1, -1):
        jour = datetime.now(timezone.utc) - timedelta(days=i)
        debut = jour.replace(hour=0, minute=0, second=0, microsecond=0)
        fin = jour.replace(hour=23, minute=59, second=59, microsecond=999999)
        count = ActiviteUtilisateur.query.filter(
            ActiviteUtilisateur.action == 'connexion',
            ActiviteUtilisateur.date >= debut,
            ActiviteUtilisateur.date <= fin
        ).count()
        labels_jours.append(jour.strftime('%d/%m'))
        connexions_par_jour.append(count)

    # Alertes par type
    stats_alertes = {
        'vol': Alerte.query.filter_by(type_alerte='vol').count(),
        'perte': Alerte.query.filter_by(type_alerte='perte').count(),
        'anomalie': Alerte.query.filter(
            Alerte.type_alerte.notin_(['vol', 'perte'])
        ).count()
    }

    # Appareils par opérateur
    operateurs_connus = ['Orange CI', 'MTN CI', 'Moov Africa']
    stats_operateurs = {}
    for op in operateurs_connus:
        stats_operateurs[op] = Appareil.query.filter_by(operateur=op).count()
    total_connus = sum(stats_operateurs.values())
    stats_operateurs['Autre'] = Appareil.query.count() - total_connus

    return render_template('admin.html',
                           utilisateurs=utilisateurs,
                           utilisateurs_actifs=utilisateurs_actifs,
                           nouveaux_mois=nouveaux_mois,
                           total_appareils=total_appareils,
                           total_alertes=total_alertes,
                           alertes_en_cours=alertes_en_cours,
                           activites_recentes=activites_recentes,
                           erreurs_recentes=erreurs_recentes,
                           erreurs_data=erreurs_data,
                           erreurs_non_resolues=erreurs_non_resolues,
                           labels_jours=labels_jours,
                           connexions_par_jour=connexions_par_jour,
                           stats_alertes=stats_alertes,
                           stats_operateurs=stats_operateurs)


@dashboard_bp.route('/admin/erreurs/<int:id>/resoudre', methods=['POST'])
@login_required
def resoudre_erreur(id):
    """Marquer une erreur comme résolue."""
    if current_user.role != 'admin':
        flash(_('Accès réservé aux administrateurs.'), 'danger')
        return redirect(url_for('dashboard.index'))

    erreur = db.get_or_404(JournalErreur, id)
    erreur.resolu = True
    db.session.commit()

    flash(_('Erreur marquée comme résolue.'), 'success')
    return redirect(url_for('dashboard.admin'))


@dashboard_bp.route('/admin/erreurs/resoudre-tout', methods=['POST'])
@login_required
def resoudre_toutes_erreurs():
    """Marquer toutes les erreurs non résolues comme résolues."""
    if current_user.role != 'admin':
        flash(_('Accès réservé aux administrateurs.'), 'danger')
        return redirect(url_for('dashboard.index'))

    count = JournalErreur.query.filter_by(resolu=False).update({'resolu': True})
    db.session.commit()

    log_activite(current_user.id, 'resolution_erreurs', f'{count} erreurs résolues automatiquement')
    flash(_(f'{count} erreur(s) résolue(s) automatiquement.'), 'success')
    return redirect(request.referrer or url_for('dashboard.admin'))


@dashboard_bp.route('/admin/utilisateurs/<int:id>/supprimer', methods=['POST'])
@login_required
def supprimer_utilisateur(id):
    """Supprimer un utilisateur et tous ses appareils."""
    if current_user.role != 'admin':
        flash(_('Accès réservé aux administrateurs.'), 'danger')
        return redirect(url_for('dashboard.index'))

    if id == current_user.id:
        flash(_('Vous ne pouvez pas supprimer votre propre compte.'), 'danger')
        return redirect(url_for('dashboard.admin'))

    user = db.get_or_404(User, id)
    nom = user.nom_complet

    from app.models import ActiviteUtilisateur, JournalErreur, FcmToken, TelephoneCollecte, HistoriqueNavigation

    ActiviteUtilisateur.query.filter_by(user_id=user.id).delete()
    JournalErreur.query.filter_by(user_id=user.id).delete()
    FcmToken.query.filter_by(user_id=user.id).delete()
    TelephoneCollecte.query.filter_by(user_id=user.id).delete()
    HistoriqueNavigation.query.filter_by(user_id=user.id).delete()

    db.session.delete(user)
    db.session.commit()

    log_activite(current_user.id, 'suppression_utilisateur', f'Utilisateur {nom} supprimé')
    flash(_('Utilisateur supprimé avec succès.'), 'success')
    return redirect(url_for('dashboard.admin'))
