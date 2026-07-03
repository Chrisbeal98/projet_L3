# Antivol Intelligent --- Application Android

Application Android native qui verrouille physiquement le telephone a distance.

## Comment ca marche

1. L'app interroge l'API du serveur Flask toutes les 3 secondes
2. Quand le statut de l'appareil passe a `vole` ou `verrouille`, l'app:
   - **Verrouille l'ecran immediatement** via `DevicePolicyManager.lockNow()`
   - **Affiche un ecran de verrouillage** par-dessus tout (meme sur l'ecran d'accueil)
   - L'utilisateur doit entrer le code de deverrouillage via l'API

## Comment compiler

### Prerequis
- Android Studio Hedgehog (2023.1.1) ou plus recent
- JDK 17
- Projet Firebase (optionnel, pour les notifications push)

### Configuration Firebase (optionnelle mais recommandee)
Les notifications push FCM permettent un verrouillage/deverrouillage quasi-instantane
(sans attendre le polling de 3-5 secondes).

1. Va sur https://console.firebase.google.com
2. Cree un projet Firebase
3. Ajoute une application Android avec le package `com.antivol.mobile`
4. Telecharge `google-services.json` et remplace le fichier `app/google-services.json`
5. Copie la `clef serveur FCM` depuis Firebase > Cloud Messaging > Parametres
6. Configure la variable d'environnement sur le serveur Flask:
   ```
   FCM_SERVER_KEY=ta_clef_serveur_fcm
   ```

**Actions FCM supportees par l'application :**
| Action | Effet |
|---|---|
| `lock` | Verrouillage immediat + ecran de verrouillage |
| `unlock` | Deverrouillage immediat (broadcast + polling) |
| `alert` | Notification d'alerte haute priorite |

### Methode 1: Android Studio
1. Ouvre Android Studio
2. `File > Open` -> Selectionne le dossier `antivol-mobile/`
3. Attends la synchronisation Gradle
4. `Build > Build Bundle(s) / APK(s) > Build APK(s)`
5. L'APK est genere dans `app/build/outputs/apk/debug/app-debug.apk`

### Methode 2: Ligne de commande
```
cd app/antivol-mobile
./gradlew assembleDebug
```

## Comment installer

1. Transfere l'APK sur ton telephone
2. Active `Sources inconnues` dans les parametres
3. Installe l'APK
4. Ouvre l'app et connecte-toi avec ton compte AntiVol
5. Active la protection Admin
6. Enregistre l'appareil (clique sur le bouton)
7. Clique sur `Lancer la surveillance`

## Configuration reseau

L'application configure l'URL du serveur dans les parametres de l'app.
Par defaut, l'URL est `http://192.168.45.36:8000/api`.

Pour changer :
1. Ouvre l'app
2. Clique sur `Parametres`
3. Modifie l'URL du serveur
4. Sauvegarde

## Permissions requises

- **INTERNET**: Interroger l'API du serveur
- **Device Admin**: Verrouiller l'ecran physiquement
- **SYSTEM_ALERT_WINDOW**: Afficher l'ecran de verrouillage par-dessus tout
- **FOREGROUND_SERVICE**: Surveiller en arriere-plan
- **ACCESS_FINE_LOCATION**: Envoyer la position GPS au serveur
- **RECEIVE_BOOT_COMPLETED**: Demarrage automatique apres redemarrage
- **REQUEST_IGNORE_BATTERY_OPTIMIZATIONS**: Desactiver l'optimisation batterie pour une surveillance fiable

## Architecture

```
com.antivol.mobile/
├── LoginActivity.java        # Connexion
├── RegisterActivity.java     # Inscription
├── MainActivity.java         # Tableau de bord + surveillance
├── LockActivity.java         # Ecran de verrouillage
├── SettingsActivity.java     # Parametres
├── MonitorService.java       # Service fond (polling + GPS)
├── AdminReceiver.java        # Device Admin
├── BootReceiver.java         # Demarrage automatique au boot
├── AntivolFirebaseService.java # Notifications push FCM
└── AppConfig.java            # Configuration partagee
```

## Optimisation batterie

Pour garantir le fonctionnement en arriere-plan, l'application demande a desactiver
l'optimisation batterie lors du lancement de la surveillance. Cela permet d'eviter
que le systeme ne mette en veille le service de polling et de GPS.

L'utilisateur doit accepter la permission `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`.

## Securite

- Verrouillage physique via DevicePolicyManager
- WakeLock pour maintien de l'ecran allume
- Blocage du retour arriere sur l'ecran de verrouillage
- Re-verrouillage si tentative de changement d'app
- Alarme sonore au verrouillage
- Anti-desactivation de l'admin (message d'avertissement)
- Tentatives limitees de code de deverrouillage
- Enforcement du PIN/pattern ecran

## Test

1. Installe l'app sur ton telephone
2. Connecte-toi avec ton compte
3. Active la protection Admin
4. Enregistre l'appareil
5. Lance la surveillance
6. Sur ton PC, va dans `http://localhost:8000/appareils`
7. Clique sur **Verrouiller** pour l'appareil
8. Le telephone se verrouille automatiquement en ~3 secondes
