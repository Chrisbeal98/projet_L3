"""
Modèles de la base de données.
Architecture 3-tiers — Couche Données.

Classes :
    - User (Utilisateur)
    - Appareil (Smartphone enregistré)
    - Alerte (Signalement vol/perte)
    - Notification (SMS, Email, Push)
    - Localisation (Position GPS)
    - ZoneRisque (Zone à risque de vol)
"""

from datetime import datetime, timezone

from app import db, login_manager
from flask_login import UserMixin


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ─────────────────────────────────────────────
# UTILISATEUR
# ─────────────────────────────────────────────
class User(db.Model, UserMixin):
    """Modèle Utilisateur — propriétaire de smartphones."""
    __tablename__ = 'utilisateurs'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    prenom = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    telephone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='utilisateur')  # utilisateur | admin
    statut = db.Column(db.String(20), default='actif')  # actif | suspendu | désactivé
    date_creation = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relations
    appareils = db.relationship('Appareil', backref='proprietaire', lazy=True, cascade='all, delete-orphan')
    alertes = db.relationship('Alerte', backref='utilisateur', lazy=True, cascade='all, delete-orphan')

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"

    def __repr__(self):
        return f'<User {self.email}>'


# ─────────────────────────────────────────────
# APPAREIL (Smartphone)
# ─────────────────────────────────────────────
class Appareil(db.Model):
    """Modèle Appareil — smartphone enregistré dans le système."""
    __tablename__ = 'appareils'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id'), nullable=False)
    imei = db.Column(db.String(20), unique=True, nullable=False)
    modele = db.Column(db.String(100), nullable=False)
    marque = db.Column(db.String(50))
    systeme_os = db.Column(db.String(20))  # Android | iOS
    version_os = db.Column(db.String(20))
    numero_telephone = db.Column(db.String(20))
    operateur = db.Column(db.String(30))  # Orange CI | MTN CI | Moov Africa
    statut = db.Column(db.String(20), default='actif')
    # Statuts : actif | volé | verrouillé | récupéré | désactivé
    code_verrouillage = db.Column(db.String(20), unique=True, nullable=True)
    code_ussd = db.Column(db.String(20), unique=True, nullable=True)  # stocke un code PIN 4 chiffres
    date_enregistrement = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relations
    alertes = db.relationship('Alerte', backref='appareil', lazy=True, cascade='all, delete-orphan')
    localisations = db.relationship('Localisation', backref='appareil', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Appareil {self.marque} {self.modele} - IMEI:{self.imei}>'


# ─────────────────────────────────────────────
# ALERTE
# ─────────────────────────────────────────────
class Alerte(db.Model):
    """Modèle Alerte — signalement de vol, perte ou anomalie."""
    __tablename__ = 'alertes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id'), nullable=False)
    appareil_id = db.Column(db.Integer, db.ForeignKey('appareils.id'), nullable=False)
    type_alerte = db.Column(db.String(20), nullable=False)
    # Types : vol | perte | anomalie | changement_sim
    description = db.Column(db.Text)
    statut = db.Column(db.String(20), default='en_cours')
    # Statuts : en_cours | traité | annulé
    priorite = db.Column(db.String(10), default='haute')  # basse | moyenne | haute | critique
    date_creation = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    date_resolution = db.Column(db.DateTime, nullable=True)

    # Relations
    notifications = db.relationship('Notification', backref='alerte', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Alerte {self.type_alerte} - {self.statut}>'


# ─────────────────────────────────────────────
# NOTIFICATION
# ─────────────────────────────────────────────
class Notification(db.Model):
    """Modèle Notification — SMS, Email ou Push envoyé."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    alerte_id = db.Column(db.Integer, db.ForeignKey('alertes.id'), nullable=False)
    type_notification = db.Column(db.String(20), nullable=False)
    # Types : sms | email | push
    contenu = db.Column(db.Text, nullable=False)
    destinataire = db.Column(db.String(150))
    statut = db.Column(db.String(20), default='envoyé')
    # Statuts : en_attente | envoyé | reçu | échoué
    date_envoi = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Notification {self.type_notification} - {self.statut}>'


# ─────────────────────────────────────────────
# LOCALISATION
# ─────────────────────────────────────────────
class Localisation(db.Model):
    """Modèle Localisation — position GPS d'un appareil."""
    __tablename__ = 'localisations'

    id = db.Column(db.Integer, primary_key=True)
    appareil_id = db.Column(db.Integer, db.ForeignKey('appareils.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    adresse = db.Column(db.String(255))
    precision_m = db.Column(db.Float)  # Précision en mètres
    source = db.Column(db.String(20), default='gps')  # gps | réseau | wifi
    date_capture = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    __table_args__ = (
        db.Index('ix_localisations_appareil_date', 'appareil_id', date_capture.desc()),
    )

    def __repr__(self):
        return f'<Localisation ({self.latitude}, {self.longitude})>'


# ─────────────────────────────────────────────
# ZONE À RISQUE
# ─────────────────────────────────────────────
class ZoneRisque(db.Model):
    """Modèle Zone à Risque — zone géographique avec incidents fréquents."""
    __tablename__ = 'zones_risque'

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    ville = db.Column(db.String(50), default='Abidjan')
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    rayon_m = db.Column(db.Float, default=500)  # Rayon en mètres
    niveau_risque = db.Column(db.String(20), default='moyen')
    # Niveaux : faible | moyen | élevé | critique
    nombre_incidents = db.Column(db.Integer, default=0)
    date_mise_a_jour = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def __repr__(self):
        return f'<ZoneRisque {self.nom} - {self.niveau_risque}>'


# ─────────────────────────────────────────────
# ACTIVITÉ UTILISATEUR (Journal analytique)
# ─────────────────────────────────────────────
class ActiviteUtilisateur(db.Model):
    """Modèle Activité — trace les actions des utilisateurs."""
    __tablename__ = 'activites_utilisateurs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    # Actions : connexion | deconnexion | inscription | ajout_appareil |
    #           signalement_alerte | modification_profil | suppression_appareil
    details = db.Column(db.String(255))
    adresse_ip = db.Column(db.String(45))
    navigateur = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    # Relation
    utilisateur = db.relationship('User', backref=db.backref('activites', lazy=True))

    def __repr__(self):
        return f'<Activite {self.action} par User#{self.user_id}>'


# ─────────────────────────────────────────────
# JOURNAL D'ERREURS
# ─────────────────────────────────────────────
class JournalErreur(db.Model):
    """Modèle Erreur — log des erreurs pour l'admin."""
    __tablename__ = 'journal_erreurs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id'), nullable=True)
    type_erreur = db.Column(db.String(10), nullable=False)  # 400, 403, 404, 500
    url = db.Column(db.String(500))
    description = db.Column(db.String(255))
    adresse_ip = db.Column(db.String(45))
    navigateur = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    resolu = db.Column(db.Boolean, default=False)

    # Relation
    utilisateur = db.relationship('User', backref=db.backref('erreurs', lazy=True))

    def __repr__(self):
        return f'<Erreur {self.type_erreur} - {self.url}>'


# ─────────────────────────────────────────────
# TOKEN FCM (Firebase Cloud Messaging)
# ─────────────────────────────────────────────
class FcmToken(db.Model):
    """Modèle Token FCM — stocke les tokens de notification push."""
    __tablename__ = 'fcm_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id'), nullable=False)
    token = db.Column(db.String(500), nullable=False, unique=True)
    date_creation = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    date_mise_a_jour = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    utilisateur = db.relationship('User', backref=db.backref('fcm_tokens', lazy=True))

    def __repr__(self):
        return f'<FcmToken User#{self.user_id}>'


# ─────────────────────────────────────────────
# INFORMATIONS TÉLÉPHONE COLLECTÉES (Web)
# ─────────────────────────────────────────────
class TelephoneCollecte(db.Model):
    """Modèle pour le stockage automatique des infos téléphone depuis le navigateur."""
    __tablename__ = 'telephones_collectes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id'), nullable=True)
    session_id = db.Column(db.String(100))
    modele = db.Column(db.String(100))
    marque = db.Column(db.String(50))
    systeme_os = db.Column(db.String(50))
    version_os = db.Column(db.String(50))
    navigateur = db.Column(db.String(100))
    ecran_largeur = db.Column(db.Integer)
    ecran_hauteur = db.Column(db.Integer)
    langue = db.Column(db.String(10))
    ip = db.Column(db.String(45))
    consentement = db.Column(db.Boolean, default=False)
    date_collecte = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    utilisateur = db.relationship('User', backref=db.backref('infos_telephone', lazy=True))

    def __repr__(self):
        return f'<TelephoneCollecte {self.marque} {self.modele} - {self.systeme_os}>'


# ─────────────────────────────────────────────
# HISTORIQUE DE NAVIGATION
# ─────────────────────────────────────────────
class HistoriqueNavigation(db.Model):
    """Modèle Historique — pages visitées par l'utilisateur."""
    __tablename__ = 'historique_navigation'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('utilisateurs.id'), nullable=False)
    endpoint = db.Column(db.String(100), nullable=False)
    titre = db.Column(db.String(100), nullable=False)
    icone = db.Column(db.String(50), default='file-text')
    url = db.Column(db.String(500), nullable=False)
    date_visite = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    utilisateur = db.relationship('User', backref=db.backref('historique_navigation', lazy=True))

    def __repr__(self):
        return f'<Historique {self.titre} pour User#{self.user_id}>'
