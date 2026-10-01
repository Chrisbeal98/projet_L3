"""Schéma initial — première migration versionnée du projet.

Revision ID: 3b6322e5a986
Revises:
Create Date: 2026-09-30

POURQUOI CE FICHIER EST PLUS LONG QU'UN AUTOGÉNÉRATEUR
-----------------------------------------------------
Le projet est né sans Alembic : le schéma était créé par `db.create_all()`, puis
complété au démarrage par quatre `ALTER TABLE` écrits à la main dans `run.py` et
`wsgi.py` (code_verrouillage, code_ussd, device_uuid, contacts_urgents). Deux
générations sont donc déjà déployées dans la nature, et une troisième
(`device_secret`, `derniere_activite`, `partage_accepte`, `partage_precision`)
a été ajoutée par le même mécanisme, toujours dans le code de démarrage.

Une migration « create_all » standard échouerait sur ces bases existantes
(table déjà là). Cette révision sait donc traiter les deux cas :

  * base VIERGE  → création complète du schéma, contraintes CHECK comprises ;
  * base LEGACY  → réconciliation : on ajoute uniquement ce qui manque, sans
                    jamais toucher aux données déjà en place.

C'est la seule révision qui se charge de cette manière. Toutes les
suivantes sont des migrations normales, applicables et réversibles.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3b6322e5a986'
down_revision = None
branch_labels = None
depends_on = None


# ═══════════════════════════════════════════════════════════════════════════
#  OUTILS (utilisés uniquement par le chemin « base legacy »)
# ═══════════════════════════════════════════════════════════════════════════

# Colonnes ajoutées APRÈS la création initiale de la base, dans l'ordre
# chronologique où elles l'ont été. Sert à réconcilier les bases déjà en place.
_COLONNES_manQUANTES = (
    # (table, nom, type SQL)
    ('appareils', 'code_verrouillage', sa.String(length=20)),
    ('appareils', 'code_ussd', sa.String(length=20)),
    ('appareils', 'device_uuid', sa.String(length=64)),
    ('appareils', 'contacts_urgents', sa.Text()),
    ('appareils', 'device_secret', sa.String(length=64)),
    ('appareils', 'derniere_activite', sa.DateTime()),
    ('alertes', 'partage_accepte', sa.Boolean()),
    ('alertes', 'partage_precision', sa.String(length=20)),
)

# Index posés par cette révision, avec la contrainte d'unicité qu'ils portent.
# `ix_appareils_device_secret` est UNIQUE : deux appareils ne peuvent pas
# partager un secret, sans quoi un téléphone usurperait l'identité d'un autre.
_INDEX = (
    ('ix_utilisateurs_statut', 'utilisateurs', ['statut'], False),
    ('ix_zones_risque_ville', 'zones_risque', ['ville'], False),
    ('ix_activites_utilisateurs_user_date', 'activites_utilisateurs',
     ['user_id', 'date'], False),
    ('ix_activites_utilisateurs_action', 'activites_utilisateurs',
     ['action'], False),
    ('ix_appareils_user_id', 'appareils', ['user_id'], False),
    ('ix_appareils_statut', 'appareils', ['statut'], False),
    ('ix_appareils_device_secret', 'appareils', ['device_secret'], True),
    ('ix_fcm_tokens_user_id', 'fcm_tokens', ['user_id'], False),
    ('ix_historique_navigation_user_date', 'historique_navigation',
     ['user_id', 'date_visite'], False),
    ('ix_journal_erreurs_user_date', 'journal_erreurs', ['user_id', 'date'], False),
    ('ix_journal_erreurs_resolu', 'journal_erreurs', ['resolu'], False),
    ('ix_alertes_user_statut', 'alertes', ['user_id', 'statut'], False),
    ('ix_alertes_appareil_id', 'alertes', ['appareil_id'], False),
    ('ix_alertes_date_creation', 'alertes', ['date_creation'], False),
    ('ix_localisations_appareil_date', 'localisations',
     ['appareil_id', 'date_capture'], False),
    ('ix_notifications_alerte_id', 'notifications', ['alerte_id'], False),
)

# Mêmes contraintes CHECK que celles déclarées dans `app/models.py`.
_CONTRAINTES_CHECK = (
    ('ck_utilisateurs_role', 'utilisateurs',
     "role IN ('utilisateur', 'admin')"),
    ('ck_utilisateurs_statut', 'utilisateurs',
     "statut IN ('actif', 'suspendu', 'désactivé')"),
    ('ck_appareils_statut', 'appareils',
     "statut IN ('actif', 'volé', 'verrouillé', 'récupéré', 'perdu', 'désactivé')"),
    ('ck_alertes_type_alerte', 'alertes',
     "type_alerte IN ('vol', 'perte', 'anomalie', 'changement_sim')"),
    ('ck_alertes_statut', 'alertes',
     "statut IN ('en_cours', 'traité', 'annulé')"),
    ('ck_alertes_priorite', 'alertes',
     "priorite IN ('basse', 'moyenne', 'haute', 'critique')"),
    ('ck_alertes_partage_precision', 'alertes',
     "partage_precision IN ('approximatif', 'exact')"),
    ('ck_notifications_type', 'notifications',
     "type_notification IN ('sms', 'email', 'push')"),
    ('ck_notifications_statut', 'notifications',
     "statut IN ('en_attente', 'envoyé', 'reçu', 'échoué')"),
    ('ck_localisations_latitude', 'localisations',
     'latitude >= -90 AND latitude <= 90'),
    ('ck_localisations_longitude', 'localisations',
     'longitude >= -180 AND longitude <= 180'),
    ('ck_zones_risque_niveau', 'zones_risque',
     "niveau_risque IN ('faible', 'moyen', 'élevé', 'critique')"),
)


def _reconcilier_legacy(bind):
    """Aligne une base créée sans Alembic sur le schéma de cette révision.

    Principe : on n'ajoute QUE ce qui manque. Aucun `DROP`, aucune donnée
    touchée. C'est réversible (`downgrade()` de cette révision recrée la base
    depuis zéro, ce qui est le seul moyen de revenir en arrière de façon
    propre).
    """
    inspecteur = sa.inspect(bind)
    tables = set(inspecteur.get_table_names())

    for table, colonne, type_sql in _COLONNES_manQUANTES:
        if table not in tables:
            continue
        if colonne in {c['name'] for c in inspecteur.get_columns(table)}:
            continue
        op.add_column(table, sa.Column(colonne, type_sql, nullable=True))
        print(f'[migration] colonne ajoutée : {table}.{colonne}')

    for nom, table, colonnes, unique in _INDEX:
        if table not in tables:
            continue
        existants = {i['name'] for i in inspecteur.get_indexes(table)}
        existants |= {c.get('name') for c in inspecteur.get_unique_constraints(table)}
        if nom in existants:
            continue
        op.create_index(nom, table, colonnes, unique=unique)
        print(f'[migration] index créé : {nom}')

    # `op.create_check_constraint` n'est supporté nativement que par les
    # moteurs gérés (PostgreSQL en production). SQLite sait lire une
    # contrainte CHECK mais pas en ajouter une à une table existante : la
    # migration s'arrêterait sur une erreur, on le saute donc explicitement.
    # Conséquence assumée : une base SQLite antérieure à cette migration
    # conserve ses données mais ne bénéficie pas des CHECK. Pour les
    # réinstaller (données de développement uniquement) :
    #     rm antivol.db && flask db upgrade
    if bind.dialect.name == 'sqlite':
        print('[migration] base SQLite existante : contraintes CHECK non ajoutées '
              '(opération non supportée par SQLite). Schéma fonctionnel.')
        return
    for nom, table, texte in _CONTRAINTES_CHECK:
        if table not in tables:
            continue
        op.create_check_constraint(nom, table, texte)
    print('[migration] contraintes CHECK ajoutées')


def upgrade():
    bind = op.get_bind()
    if 'utilisateurs' in set(sa.inspect(bind).get_table_names()):
        # Base déjà en place (avant Alembic) : on réconcilie au lieu de recréer.
        _reconcilier_legacy(bind)
        return

    op.create_table('utilisateurs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=100), nullable=False),
    sa.Column('prenom', sa.String(length=100), nullable=False),
    sa.Column('email', sa.String(length=150), nullable=False),
    sa.Column('telephone', sa.String(length=20), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=True),
    sa.Column('statut', sa.String(length=20), nullable=True),
    sa.Column('date_creation', sa.DateTime(), nullable=True),
    sa.CheckConstraint("role IN ('utilisateur', 'admin')", name='ck_utilisateurs_role'),
    sa.CheckConstraint("statut IN ('actif', 'suspendu', 'désactivé')", name='ck_utilisateurs_statut'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    with op.batch_alter_table('utilisateurs', schema=None) as batch_op:
        batch_op.create_index('ix_utilisateurs_statut', ['statut'], unique=False)

    op.create_table('zones_risque',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=100), nullable=False),
    sa.Column('ville', sa.String(length=50), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('rayon_m', sa.Float(), nullable=True),
    sa.Column('niveau_risque', sa.String(length=20), nullable=True),
    sa.Column('nombre_incidents', sa.Integer(), nullable=True),
    sa.Column('date_mise_a_jour', sa.DateTime(), nullable=True),
    sa.CheckConstraint("niveau_risque IN ('faible', 'moyen', 'élevé', 'critique')", name='ck_zones_risque_niveau'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('zones_risque', schema=None) as batch_op:
        batch_op.create_index('ix_zones_risque_ville', ['ville'], unique=False)

    op.create_table('activites_utilisateurs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('details', sa.String(length=255), nullable=True),
    sa.Column('adresse_ip', sa.String(length=45), nullable=True),
    sa.Column('navigateur', sa.String(length=200), nullable=True),
    sa.Column('date', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('activites_utilisateurs', schema=None) as batch_op:
        batch_op.create_index('ix_activites_utilisateurs_action', ['action'], unique=False)
        batch_op.create_index('ix_activites_utilisateurs_user_date', ['user_id', 'date'], unique=False)

    op.create_table('appareils',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('imei', sa.String(length=20), nullable=False),
    sa.Column('modele', sa.String(length=100), nullable=False),
    sa.Column('marque', sa.String(length=50), nullable=True),
    sa.Column('systeme_os', sa.String(length=20), nullable=True),
    sa.Column('version_os', sa.String(length=20), nullable=True),
    sa.Column('numero_telephone', sa.String(length=20), nullable=True),
    sa.Column('operateur', sa.String(length=30), nullable=True),
    sa.Column('statut', sa.String(length=20), nullable=True),
    sa.Column('code_verrouillage', sa.String(length=20), nullable=True),
    sa.Column('code_ussd', sa.String(length=20), nullable=True),
    sa.Column('device_uuid', sa.String(length=64), nullable=True),
    sa.Column('device_secret', sa.String(length=64), nullable=True),
    sa.Column('derniere_activite', sa.DateTime(), nullable=True),
    sa.Column('contacts_urgents', sa.Text(), nullable=True),
    sa.Column('date_enregistrement', sa.DateTime(), nullable=True),
    sa.CheckConstraint("statut IN ('actif', 'volé', 'verrouillé', 'récupéré', 'perdu', 'désactivé')", name='ck_appareils_statut'),
    sa.ForeignKeyConstraint(['user_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code_ussd'),
    sa.UniqueConstraint('code_verrouillage'),
    sa.UniqueConstraint('device_uuid'),
    sa.UniqueConstraint('imei')
    )
    with op.batch_alter_table('appareils', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_appareils_device_secret'), ['device_secret'], unique=True)
        batch_op.create_index('ix_appareils_statut', ['statut'], unique=False)
        batch_op.create_index('ix_appareils_user_id', ['user_id'], unique=False)

    op.create_table('fcm_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('token', sa.String(length=500), nullable=False),
    sa.Column('date_creation', sa.DateTime(), nullable=True),
    sa.Column('date_mise_a_jour', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token')
    )
    with op.batch_alter_table('fcm_tokens', schema=None) as batch_op:
        batch_op.create_index('ix_fcm_tokens_user_id', ['user_id'], unique=False)

    op.create_table('historique_navigation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('endpoint', sa.String(length=100), nullable=False),
    sa.Column('titre', sa.String(length=100), nullable=False),
    sa.Column('icone', sa.String(length=50), nullable=True),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('date_visite', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('historique_navigation', schema=None) as batch_op:
        batch_op.create_index('ix_historique_navigation_user_date', ['user_id', 'date_visite'], unique=False)

    op.create_table('journal_erreurs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('type_erreur', sa.String(length=10), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('adresse_ip', sa.String(length=45), nullable=True),
    sa.Column('navigateur', sa.String(length=200), nullable=True),
    sa.Column('date', sa.DateTime(), nullable=True),
    sa.Column('resolu', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('journal_erreurs', schema=None) as batch_op:
        batch_op.create_index('ix_journal_erreurs_resolu', ['resolu'], unique=False)
        batch_op.create_index('ix_journal_erreurs_user_date', ['user_id', 'date'], unique=False)

    op.create_table('telephones_collectes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('session_id', sa.String(length=100), nullable=True),
    sa.Column('modele', sa.String(length=100), nullable=True),
    sa.Column('marque', sa.String(length=50), nullable=True),
    sa.Column('systeme_os', sa.String(length=50), nullable=True),
    sa.Column('version_os', sa.String(length=50), nullable=True),
    sa.Column('navigateur', sa.String(length=100), nullable=True),
    sa.Column('ecran_largeur', sa.Integer(), nullable=True),
    sa.Column('ecran_hauteur', sa.Integer(), nullable=True),
    sa.Column('langue', sa.String(length=10), nullable=True),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('consentement', sa.Boolean(), nullable=True),
    sa.Column('date_collecte', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('alertes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('appareil_id', sa.Integer(), nullable=False),
    sa.Column('type_alerte', sa.String(length=20), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('statut', sa.String(length=20), nullable=True),
    sa.Column('priorite', sa.String(length=10), nullable=True),
    sa.Column('date_creation', sa.DateTime(), nullable=True),
    sa.Column('date_resolution', sa.DateTime(), nullable=True),
    sa.Column('partage_accepte', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('partage_precision', sa.String(length=20), server_default='approximatif', nullable=False),
    sa.CheckConstraint("partage_precision IN ('approximatif', 'exact')", name='ck_alertes_partage_precision'),
    sa.CheckConstraint("priorite IN ('basse', 'moyenne', 'haute', 'critique')", name='ck_alertes_priorite'),
    sa.CheckConstraint("statut IN ('en_cours', 'traité', 'annulé')", name='ck_alertes_statut'),
    sa.CheckConstraint("type_alerte IN ('vol', 'perte', 'anomalie', 'changement_sim')", name='ck_alertes_type_alerte'),
    sa.ForeignKeyConstraint(['appareil_id'], ['appareils.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['utilisateurs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('alertes', schema=None) as batch_op:
        batch_op.create_index('ix_alertes_appareil_id', ['appareil_id'], unique=False)
        batch_op.create_index('ix_alertes_date_creation', ['date_creation'], unique=False)
        batch_op.create_index('ix_alertes_user_statut', ['user_id', 'statut'], unique=False)

    op.create_table('localisations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('appareil_id', sa.Integer(), nullable=False),
    sa.Column('latitude', sa.Float(), nullable=False),
    sa.Column('longitude', sa.Float(), nullable=False),
    sa.Column('adresse', sa.String(length=255), nullable=True),
    sa.Column('precision_m', sa.Float(), nullable=True),
    sa.Column('source', sa.String(length=20), nullable=True),
    sa.Column('date_capture', sa.DateTime(), nullable=True),
    sa.CheckConstraint('latitude >= -90 AND latitude <= 90', name='ck_localisations_latitude'),
    sa.CheckConstraint('longitude >= -180 AND longitude <= 180', name='ck_localisations_longitude'),
    sa.ForeignKeyConstraint(['appareil_id'], ['appareils.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('localisations', schema=None) as batch_op:
        batch_op.create_index('ix_localisations_appareil_date', ['appareil_id', sa.text('date_capture DESC')], unique=False)

    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('alerte_id', sa.Integer(), nullable=False),
    sa.Column('type_notification', sa.String(length=20), nullable=False),
    sa.Column('contenu', sa.Text(), nullable=False),
    sa.Column('destinataire', sa.String(length=150), nullable=True),
    sa.Column('statut', sa.String(length=20), nullable=True),
    sa.Column('date_envoi', sa.DateTime(), nullable=True),
    sa.CheckConstraint("statut IN ('en_attente', 'envoyé', 'reçu', 'échoué')", name='ck_notifications_statut'),
    sa.CheckConstraint("type_notification IN ('sms', 'email', 'push')", name='ck_notifications_type'),
    sa.ForeignKeyConstraint(['alerte_id'], ['alertes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.create_index('ix_notifications_alerte_id', ['alerte_id'], unique=False)


def downgrade():
    # Inversible : on supprime les index, puis les tables, dans l'ordre
    # inverse des dépendances. Aucune donnée n'est recréée.
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('ix_notifications_alerte_id')

    op.drop_table('notifications')
    with op.batch_alter_table('localisations', schema=None) as batch_op:
        batch_op.drop_index('ix_localisations_appareil_date')

    op.drop_table('localisations')
    with op.batch_alter_table('alertes', schema=None) as batch_op:
        batch_op.drop_index('ix_alertes_user_statut')
        batch_op.drop_index('ix_alertes_date_creation')
        batch_op.drop_index('ix_alertes_appareil_id')

    op.drop_table('alertes')
    op.drop_table('telephones_collectes')
    with op.batch_alter_table('journal_erreurs', schema=None) as batch_op:
        batch_op.drop_index('ix_journal_erreurs_user_date')
        batch_op.drop_index('ix_journal_erreurs_resolu')

    op.drop_table('journal_erreurs')
    with op.batch_alter_table('historique_navigation', schema=None) as batch_op:
        batch_op.drop_index('ix_historique_navigation_user_date')

    op.drop_table('historique_navigation')
    with op.batch_alter_table('fcm_tokens', schema=None) as batch_op:
        batch_op.drop_index('ix_fcm_tokens_user_id')

    op.drop_table('fcm_tokens')
    with op.batch_alter_table('appareils', schema=None) as batch_op:
        batch_op.drop_index('ix_appareils_user_id')
        batch_op.drop_index('ix_appareils_statut')
        batch_op.drop_index(batch_op.f('ix_appareils_device_secret'))

    op.drop_table('appareils')
    with op.batch_alter_table('activites_utilisateurs', schema=None) as batch_op:
        batch_op.drop_index('ix_activites_utilisateurs_user_date')
        batch_op.drop_index('ix_activites_utilisateurs_action')

    op.drop_table('activites_utilisateurs')
    with op.batch_alter_table('zones_risque', schema=None) as batch_op:
        batch_op.drop_index('ix_zones_risque_ville')

    op.drop_table('zones_risque')
    with op.batch_alter_table('utilisateurs', schema=None) as batch_op:
        batch_op.drop_index('ix_utilisateurs_statut')

    op.drop_table('utilisateurs')
