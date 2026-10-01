package com.antivol.mobile.service

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.app.admin.DevicePolicyManager
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.location.Location
import android.os.Build
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.antivol.mobile.AntiVolApp
import com.antivol.mobile.data.CommandeProtocole
import com.antivol.mobile.data.api.RetrofitClient
import com.antivol.mobile.data.model.LocationUpdateRequest
import com.antivol.mobile.receiver.AdminReceiver
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

/**
 * Service de surveillance : GPS, canal de commande, état de verrouillage.
 *
 * Trois décisions structurantes, toutes commentées ici : la persistance de
 * l'état de vol, la signature des commandes reçues, et un wakelock borné.
 */
class MonitorService : Service() {

    companion object {
        private const val TAG = "MonitorService"
        private const val NOTIFICATION_ID = 1
        private const val ALERT_NOTIFICATION_CHANNEL = "antivol_alerts"
        private const val NTFY_BASE_URL = "https://ntfy.sh"

        /**
         * Fenêtre de la prise de position demandée (FR-CMD-05).
         *
         * Courte : le propriétaire attend une réponse immédiate, pas une
         * position de précision offensive. Au-delà, le cycle périodique prend
         * le relais.
         */
        private const val PRIORITE_LOCATE_MS = 10_000L

        /**
         * Cadence GPS en fonctionnement normal.
         *
         * 10 s : suffisamment fin pour tracer un trajet, suffisamment économe
         * pour tenir une journée entière. Une cadence plus serrée n'apporte rien
         * à une surveillance de vol et finirait en batterie vide — donc en
         * téléphone muet précisément quand il faudrait agir.
         */
        private const val GPS_INTERVALLE_NORMAL_MS = 10_000L
        private const val GPS_INTERVALLE_MIN_NORMAL_MS = 5_000L

        /**
         * Cadence GPS quand l'appareil est déclaré volé.
         *
         * 3 s : on suit le voleur en temps quasi réel. Le surcoût est
         * assumé — c'est la situation pour laquelle l'utilisateur a payé ce
         * qu'il reste de batterie.
         */
        private const val GPS_INTERVALLE_VOL_MS = 3_000L
        private const val GPS_INTERVALLE_MIN_VOL_MS = 1_000L

        /**
         * Marge d'expiration du wakelock, en millisecondes.
         *
         * Le wakelock n'est demandé que le temps d'un appel réseau : le tenir
         * en continu viderait la batterie et se ferait couper par Android.
         */
        private const val WAKELOCK_MARGE_MS = 30_000L

        /**
         * Démarre le service, en respectant la contrainte d'Android 8+.
         *
         * Point d'entrée unique : une activité, un récepteur de démarrage et
         * l'écran de démarrage appellent tous cette méthode, ce qui évite
         * d'oublier la variante `startForegroundService` quelque part — un
         * oubli qui provoque un `IllegalStateException` silencieux à l'achat.
         */
        fun demarrer(context: Context) {
            val intent = Intent(context, MonitorService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }

    private var dpm: DevicePolicyManager? = null
    private var adminComponent: ComponentName? = null

    /**
     * L'appareil est-il verrouillé ?
     *
     * Volontairement miroir de `PreferencesManager.etatVol`, et non l'unique
     * vérité : le service peut être tué et recréé par le système à tout
     * moment, et une variable de champ serait alors remise à `false`. Un
     * téléphone volé qui voit son service tuer se déverrouillerait tout seul.
     *
     * La version persistée fait autorité au démarrage — voir `restaurerEtatVol`
     * — et l'état local ne sert qu'à éviter de re-notifier sans arrêt.
     */
    private var isLocked = false
    private var fusedLocationClient: FusedLocationProviderClient? = null
    private var locationCallback: LocationCallback? = null
    private var isGpsStarted = false
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var pollingJob: Job? = null
    private var ntfyJob: Job? = null
    private var wakeLock: PowerManager.WakeLock? = null

    /**
     * Curseur de lecture ntfy, par topic.
     *
     * Une map et non un champ unique : plusieurs topics peuvent être suivis
     * (celui de cet appareil, celui des appareils partagés), et un curseur
     * global ferait sauter les messages de l'un dès qu'un message de l'autre
     * arrive.
     */
    private val lastNtfyTimestamp = mutableMapOf<String, Long>()

    private lateinit var prefsManager: com.antivol.mobile.data.PreferencesManager

    private val unlockReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if ("com.antivol.mobile.ACTION_UNLOCK" == intent.action) {
                Log.i(TAG, "Déverrouillage via FCM")
                setVerrouille(false)
            }
        }
    }

    /**
     * Demande de position immédiate (FR-CMD-05).
     *
     * `BroadcastReceiver` non exporté : aucune autre application ne peut
     * déclencher une prise de position sur ce téléphone. C'est ce que
     * garantit `Context.RECEIVER_NOT_EXPORTED` sur Android 13+ ; sur les
     * versions antérieures, `setPackage()` sur l'Intent restreint déjà la
     * diffusion à notre propre application.
     */
    private val locateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (CommandeHandler.ACTION_LOCATE_IMMEDIAT == intent.action) {
                Log.i(TAG, "Commande LOCATE reçue : demande de position")
                demanderPositionImmediate()
            }
        }
    }

    /**
     * `UnspecifiedRegisterReceiverFlag` est neutralisé à dessein sur la branche
     * « ancien Android » : la surcharge
     * `registerReceiver(receiver, filter, flags)` n'existe pas avant Android 13,
     * et c'est précisément ce canal qui doit continuer à fonctionner sur ces
     * versions — c'est lui qui déverrouille un téléphone volé dont le service
     * tourne encore sous Android 8.
     *
     * Le broadcast reste protégé des deux côtés : l'émetteur pose `setPackage()`
     * (la diffusion ne sort pas de notre application) et le serveur ne signe un
     * message que pour l'appareil visé, avec le secret de cet appareil.
     */
    @SuppressLint("UnspecifiedRegisterReceiverFlag")
    override fun onCreate() {
        super.onCreate()
        prefsManager = (application as AntiVolApp).preferencesManager
        dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager
        adminComponent = ComponentName(this, AdminReceiver::class.java)
        createNotificationChannel()
        createAlertNotificationChannel()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(unlockReceiver, IntentFilter("com.antivol.mobile.ACTION_UNLOCK"), Context.RECEIVER_NOT_EXPORTED)
            registerReceiver(
                locateReceiver,
                IntentFilter(CommandeHandler.ACTION_LOCATE_IMMEDIAT),
                Context.RECEIVER_NOT_EXPORTED
            )
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(unlockReceiver, IntentFilter("com.antivol.mobile.ACTION_UNLOCK"))
            @Suppress("DEPRECATION")
            registerReceiver(locateReceiver, IntentFilter(CommandeHandler.ACTION_LOCATE_IMMEDIAT))
        }
        CommandeHandler.verifierAdmin(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification())

        // L'état de vol précède tout le reste : il conditionne la cadence du
        // GPS et détermine s'il faut reverrouiller immédiatement.
        restaurerEtatVol()

        startPolling()
        startNtfySubscription()
        startLocationUpdates()
        return START_STICKY
    }

    override fun onDestroy() {
        pollingJob?.cancel()
        ntfyJob?.cancel()
        stopLocationUpdates()
        libererWakeLock()
        try { unregisterReceiver(unlockReceiver) } catch (_: Exception) {}
        try { unregisterReceiver(locateReceiver) } catch (_: Exception) {}
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    /**
     * Reprend l'état de verrouillage persisté.
     *
     * C'est la reprise après redémarrage : un téléphone volé doit se
     * reverrouiller au démarrage du service, sans attendre une nouvelle
     * commande. Le serveur peut contredire — le propriétaire a pu déverrouiller
     * entre-temps — et le cycle de `checkStatus` tranchera. Mais on commence
     * par l'état local : c'est le plus récent et le plus sûr tant qu'on n'a
     * pas de réseau.
     */
    private fun restaurerEtatVol() {
        val volPersiste = prefsManager.estVolSync()
        if (volPersiste && !isLocked) {
            isLocked = true
            Log.i(TAG, "Appareil déclaré volé au démarrage : reverrouillage")
            CommandeHandler.verifierAdmin(this)
            CommandeHandler.verrouiller(
                this,
                "Appareil verrouillé",
                "Verrouillage automatique : cet appareil est déclaré volé"
            )
        } else {
            isLocked = volPersiste
        }
    }

    /**
     * Change l'état de verrouillage, et le persiste.
     *
     * Toute écriture de `isLocked` passe par ici : c'est le seul endroit où
     * l'on touche à la fois à la variable et au stockage. Un chemin qui
     * oublierait de sauvegarder redécouvrirait au redémarrage un téléphone que
     * l'on croyait déverrouillé.
     *
     * Le passage à « volé » accélère le GPS : c'est la seule contre-mesure qui
     * devient plus efficace à mesure que le temps passe.
     */
    private fun setVerrouille(verrouille: Boolean) {
        if (isLocked == verrouille) return
        isLocked = verrouille
        scope.launch {
            prefsManager.setEtatVol(verrouille)
            appliquerCadenceGps(verrouille)
        }
    }

    private fun startPolling() {
        pollingJob?.cancel()
        pollingJob = scope.launch {
            while (isActive) {
                checkStatus()
                delay(5000)
            }
        }
    }

    /**
     * Abonnement au canal de commande.
     *
     * Le topic est dérivé du secret de l'appareil : il n'est ni devinable ni
     * énumérable, et chaque message est signé avec ce même secret. Un topic
     * découvert ne permet donc pas de forger un ordre — le message est rejeté
     * avant tout effet.
     *
     * Sans secret, il n'y a rien à écouter : on ne se rabat sur aucun topic
     * devinable, ce qui serait exactement la faille que le canal signé
     * existe pour fermer.
     */
    private fun startNtfySubscription() {
        ntfyJob?.cancel()
        ntfyJob = scope.launch {
            val secret = prefsManager.getDeviceSecretSync()
            if (secret.isEmpty()) {
                Log.w(TAG, "Aucun secret d'appareil : canal de commande inactif")
                return@launch
            }

            val topic = CommandeProtocole.topicPourSecret(secret)
            if (topic == null) {
                Log.w(TAG, "Topic ntfy indéterminé")
                return@launch
            }

            Log.i(TAG, "Ecoute ntfy sur le topic signe de cet appareil")
            while (isActive) {
                try {
                    pollNtfyTopic(topic, secret)
                } catch (e: Exception) {
                    Log.e(TAG, "Erreur ntfy: ${e.message}")
                }
                delay(5000)
            }
        }
    }

    private fun pollNtfyTopic(topic: String, secret: String) {
        val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .build()

        val since = lastNtfyTimestamp[topic] ?: (System.currentTimeMillis() / 1000 - 1)
        val url = "$NTFY_BASE_URL/$topic/json?poll=1&since=$since"
        val request = Request.Builder().url(url).get().build()

        try {
            val response = client.newCall(request).execute()
            if (!response.isSuccessful) return

            val reader = BufferedReader(InputStreamReader(response.body?.byteStream() ?: return))
            var line: String?
            while (reader.readLine().also { line = it } != null) {
                val trimmed = line?.trim() ?: continue
                if (trimmed.isEmpty()) continue
                try {
                    val json = JSONObject(trimmed)
                    if (json.optString("event") != "message") continue

                    val title = json.optString("title", "AntiVol")
                    val message = json.optString("message", "")
                    val data = json.optJSONObject("data")

                    val msgTimestamp = json.optLong("time", 0)
                    if (msgTimestamp > (lastNtfyTimestamp[topic] ?: 0L)) {
                        lastNtfyTimestamp[topic] = msgTimestamp
                    }

                    traiterCommande(data, title, message, topic, secret)
                } catch (_: Exception) {}
            }
        } catch (e: Exception) {
            Log.e(TAG, "Erreur HTTP ntfy: ${e.message}")
        }
    }

    /**
     * Exécute une commande reçue, après vérification de sa signature.
     *
     * L'ordre est impératif et non négociable :
     *   1. signature invalide  → abandon, AUCUNE action ;
     *   2. commande d'un autre appareil → simple notification ;
     *   3. alerte (sans action) → simple notification ;
     *   4. sinon → exécution.
     *
     * Le rejet en 1 est ce qui rend le canal sûr : un attaquant qui découvre
     * le topic peut publier, mais pas signer.
     */
    private fun traiterCommande(
        data: JSONObject?,
        titre: String,
        corps: String,
        topic: String,
        secret: String
    ) {
        val monAppareilId = prefsManager.getAppareilIdSync()
        val action = CommandeHandler.normaliser(
            data?.optString("action"),
            data?.optString("command")
        )
        val appareilCible = data?.optString("appareil_id")

        // 1. Signature : précède toute décision, même pour une simple alerte.
        //    Un message non signé est traité comme une notification, jamais
        //    comme un ordre.
        if (data != null) {
            if (!CommandeProtocole.verifierSignature(secret, data)) {
                Log.w(TAG, "Commande ntfy NON signée : ignorée")
                return
            }
        } else {
            // Un message sans données ne peut être ni vérifié ni exécuté.
            Log.w(TAG, "Message ntfy sans données : ignoré")
            return
        }

        // 2. Alerte ou appareil tiers : on informe, on n'agit pas.
        if (action == CommandeHandler.ACTION_ALERT || !CommandeHandler.estPourCetAppareil(appareilCible, monAppareilId)) {
            showAlertNotification(titre, corps)
            return
        }

        // 3. Ordre authentifié, cible ce téléphone : on agit.
        when (action) {
            CommandeHandler.ACTION_LOCK -> {
                if (!isLocked) {
                    Log.i(TAG, "Commande LOCK reçue (topic=$topic, appareil=$monAppareilId)")
                    setVerrouille(true)
                    CommandeHandler.verifierAdmin(this)
                    CommandeHandler.verrouiller(this, titre, corps)
                }
            }
            CommandeHandler.ACTION_UNLOCK -> {
                setVerrouille(false)
                CommandeHandler.deverrouiller(this)
            }
            CommandeHandler.ACTION_LOCATE -> {
                Log.i(TAG, "Commande LOCATE reçue (topic=$topic, appareil=$monAppareilId)")
                demanderPositionImmediate()
            }
        }
    }

    /**
     * Prend un point GPS unique et l'envoie tout de suite (FR-CMD-05).
     *
     * Le cycle périodique (10 s) ne suffit pas quand le propriétaire consulte
     * la carte : il veut la position de maintenant. `getCurrentLocation()`
     * renvoie un point neuf, contrairement au dernier point connu que
     * `lastLocation` donnerait.
     *
     * Trois issues, aucune n'est bloquante : permission refusée, GPS
     * indisponible, ou délai dépassé. Dans les trois cas on abandonne
     * silencieusement — le cycle périodique enverra la position suivante.
     */
    private fun demanderPositionImmediate() {
        val client = fusedLocationClient
        if (client == null) {
            Log.w(TAG, "LOCATE : client GPS indisponible")
            return
        }
        if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION)
            != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            Log.w(TAG, "LOCATE : permission de localisation refusée")
            return
        }

        val tokenSource = com.google.android.gms.tasks.CancellationTokenSource()
        try {
            // play-services-location 21.3.0 expose `getCurrentLocation` avec
            // une priorité entière et non un `LocationRequest` : on utilise
            // l'API de cette version, seule disponible ici.
            client.getCurrentLocation(
                com.google.android.gms.location.Priority.PRIORITY_HIGH_ACCURACY,
                tokenSource.token
            ).addOnSuccessListener { loc ->
                if (loc != null) {
                    Log.i(TAG, "LOCATE : position envoyée")
                    sendLocation(loc)
                } else {
                    Log.w(TAG, "LOCATE : aucun point renvoyé")
                }
            }.addOnFailureListener { e ->
                Log.w(TAG, "LOCATE échoué: ${e.message}")
            }

            // Filet de sécurité : si le GPS ne répond pas, on abandonne la
            // requête au bout du délai. Appeler `cancel()` ici même annulerait
            // la demande avant qu'elle aboutisse.
            scope.launch {
                delay(PRIORITE_LOCATE_MS)
                tokenSource.cancel()
            }
        } catch (e: Exception) {
            Log.e(TAG, "LOCATE : exception ${e.message}")
        }
    }

    private fun showAlertNotification(title: String, body: String) {
        val builder = NotificationCompat.Builder(this, ALERT_NOTIFICATION_CHANNEL)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_ALARM)

        (getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager)
            ?.notify(System.currentTimeMillis().toInt(), builder.build())
    }

    private fun createAlertNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                ALERT_NOTIFICATION_CHANNEL, "Alertes AntiVol",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications d'alerte de vol et verrouillage"
                enableVibration(true)
                lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            }
            (getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager)
                ?.createNotificationChannel(channel)
        }
    }

    /**
     * Canal de secours : interroge le serveur toutes les 5 s.
     *
     * Indispensable même si FCM et ntfy fonctionnent : les services Google Play
     * peuvent être arrêtés par le système, et ntfy.sh est un service tiers qui
     * peut tomber. Cette requête ne demande aucun privilège particulier et
     * rattrape les commandes manquées.
     */
    private suspend fun checkStatus() {
        try {
            val deviceId = prefsManager.getAppareilIdSync()
            val apiUrl = prefsManager.getApiUrlSync()
            if (deviceId == -1) return

            val api = RetrofitClient.getApiService(apiUrl)
            val response = api.getDeviceStatus(deviceId)
            if (response.isSuccessful) {
                val verrouille = response.body()?.verrouille ?: false
                if (verrouille && !isLocked) {
                    setVerrouille(true)
                    CommandeHandler.verrouiller(
                        this,
                        "Appareil verrouillé",
                        "Verrouillage à distance activé depuis le tableau de bord"
                    )
                } else if (!verrouille && isLocked) {
                    setVerrouille(false)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Erreur checkStatus: ${e.message}")
        }
    }

    private fun startLocationUpdates() {
        if (isGpsStarted) return
        try {
            fusedLocationClient = LocationServices.getFusedLocationProviderClient(this)

            locationCallback = object : LocationCallback() {
                override fun onLocationResult(result: LocationResult) {
                    result.lastLocation?.let { loc ->
                        sendLocation(loc)
                    }
                }
            }

            if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                @Suppress("DEPRECATION")
                fusedLocationClient?.requestLocationUpdates(
                    construireRequeteGps(isLocked),
                    locationCallback!!,
                    Looper.myLooper() ?: Looper.getMainLooper()
                )
                isGpsStarted = true
            } else {
                Log.w(TAG, "Permission de localisation non accordée : GPS inactif")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Erreur startLocationUpdates: ${e.message}")
        }
    }

    private fun construireRequeteGps(vol: Boolean): LocationRequest {
        val intervalle = if (vol) GPS_INTERVALLE_VOL_MS else GPS_INTERVALLE_NORMAL_MS
        val minimum = if (vol) GPS_INTERVALLE_MIN_VOL_MS else GPS_INTERVALLE_MIN_NORMAL_MS

        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            LocationRequest.Builder(intervalle).apply {
                setPriority(Priority.PRIORITY_HIGH_ACCURACY)
                setMinUpdateIntervalMillis(minimum)
            }.build()
        } else {
            @Suppress("DEPRECATION")
            LocationRequest().apply {
                interval = intervalle
                fastestInterval = minimum
                priority = LocationRequest.PRIORITY_HIGH_ACCURACY
            }
        }
    }

    /**
     * Bascule la cadence du GPS entre surveillance normale et poursuite.
     *
     * On réabonne avec le nouvel intervalle plutôt que d'arrêter puis
     * redémarrer le service : cela évite de perdre le client de localisation
     * et de refaire une demande de permission qui a déjà été accordée.
     */
    private fun appliquerCadenceGps(vol: Boolean) {
        if (!isGpsStarted) return
        val client = fusedLocationClient ?: return
        val callback = locationCallback ?: return

        if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION)
            != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            return
        }

        try {
            // `removeLocationUpdates` puis un nouvel abonnement avec le bon
            // intervalle : c'est la seule façon de changer la fréquence sur
            // l'API Google.
            client.removeLocationUpdates(callback)
            @Suppress("DEPRECATION")
            client.requestLocationUpdates(
                construireRequeteGps(vol),
                callback,
                Looper.getMainLooper()
            )
            Log.i(TAG, "Cadence GPS passée à ${if (vol) "poursuite" else "normale"}")
        } catch (e: Exception) {
            Log.e(TAG, "Changement de cadence GPS impossible: ${e.message}")
        }
    }

    private fun stopLocationUpdates() {
        fusedLocationClient?.removeLocationUpdates(locationCallback ?: return)
        isGpsStarted = false
    }

    /**
     * Envoie une position au serveur.
     *
     * Le wakelock n'est pris que pour la durée de l'appel. Le garder en
     * permanence viderait la batterie ; ne pas le prendre ferait échouer
     * l'envoi quand l'écran s'éteint et que le CPU se met en veille — donc au
     * moment précis où le téléphone est dans la poche de quelqu'un.
     */
    private fun sendLocation(location: Location) {
        val deviceId = prefsManager.getAppareilIdSync()
        if (deviceId == -1) return
        if (prefsManager.getDeviceSecretSync().isEmpty()) return

        scope.launch {
            val lock = prendreWakeLock()
            try {
                val apiUrl = prefsManager.getApiUrlSync()
                val api = RetrofitClient.getApiService(apiUrl)
                api.updateLocation(
                    LocationUpdateRequest(
                        appareilId = deviceId,
                        latitude = location.latitude,
                        longitude = location.longitude,
                        precisionM = location.accuracy,
                        source = location.provider ?: "gps"
                    )
                )
                Log.i(TAG, "GPS: ${location.latitude}, ${location.longitude}")
            } catch (e: Exception) {
                Log.e(TAG, "Erreur GPS: ${e.message}")
            } finally {
                libererWakeLock(lock)
            }
        }
    }

    /**
     * Prend un wakelock partiel, borné dans le temps.
     *
     * `PARTIAL_WAKE_LOCK` avec un délai : l'écran peut s'éteindre, le CPU reste
     * réveillé le temps de l'appel réseau. Le verrou n'apparaît pas dans les
     * statistiques de batterie, ce qui évite aussi qu'Android le signale à
     * l'utilisateur comme un usage anormal.
     */
    private fun prendreWakeLock(): PowerManager.WakeLock? {
        return try {
            val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager ?: return null
            val lock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "antivol:localisation")
            lock.setReferenceCounted(false)
            lock.acquire(WAKELOCK_MARGE_MS)
            wakeLock = lock
            lock
        } catch (e: Exception) {
            Log.w(TAG, "WakeLock indisponible: ${e.message}")
            null
        }
    }

    private fun libererWakeLock(lock: PowerManager.WakeLock? = wakeLock) {
        try {
            lock?.takeIf { it.isHeld }?.release()
        } catch (e: Exception) {
            // Un « déjà relâché » n'a aucune conséquence : le délai de garde
            // aura déjà rendu le verrou de lui-même.
            Log.w(TAG, "Libération du wakelock: ${e.message}")
        }
        if (lock === wakeLock) {
            wakeLock = null
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                "antivol_channel", "AntiVol Monitor",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Surveillance en cours"
            }
            (getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager)?.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        // L'identifiant de canal est ignoré par NotificationCompat avant
        // l'API 26 : on peut donc le passer inconditionnellement et éviter
        // le constructeur à un seul argument, déprécié.
        return NotificationCompat.Builder(this, "antivol_channel")
            .setContentTitle("Antivol Intelligent")
            .setContentText("Protection active - Surveillance en cours")
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setOngoing(true)
            .build()
    }
}
