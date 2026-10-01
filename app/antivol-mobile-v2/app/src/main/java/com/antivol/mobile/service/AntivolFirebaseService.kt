package com.antivol.mobile.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.*
import com.antivol.mobile.AntiVolApp

class AntivolFirebaseService : FirebaseMessagingService() {

    companion object {
        private const val TAG = "FCM_AntiVol"
        private const val CHANNEL_ID = "antivol_alerts"
    }

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private lateinit var prefsManager: com.antivol.mobile.data.PreferencesManager

    override fun onCreate() {
        super.onCreate()
        prefsManager = (application as AntiVolApp).preferencesManager
        createNotificationChannel()
    }

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        // Le token n'est PAS journalisé : c'est une clé d'abonnement au canal
        // de notification. Quiconque le lirait dans logcat pourrait s'y
        // inscrire et recevoir les alertes antivol de ce téléphone — donc sa
        // position et ses ordres de verrouillage.
        //
        // Même un préfixe est retiré : un « renew » et un échec d'envoi se
        // distinguent déjà par ce que journalise `sendTokenToServer`. Il n'y
        // a rien à diagnostiquer que le token lui-même ne donne.
        Log.i(TAG, "Nouveau token FCM enregistré")
        sendTokenToServer(token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)

        val monAppareilId = prefsManager.getAppareilIdSync()
        val action = CommandeHandler.normaliser(
            message.data["action"],
            message.data["command"]
        )

        // Le contenu du message n'est pas journalisé non plus : il peut
        // contenir une position GPS ou un ordre de verrouillage.
        Log.i(TAG, "Message FCM reçu (action=$action, appareil=$monAppareilId)")

        if (action == null) {
            message.notification?.let {
                showAlertNotification(it.title ?: "AntiVol", it.body ?: "Notification")
            }
            return
        }

        // Alerte communautaire ou commande visant un autre appareil : on informe seulement.
        if (action == CommandeHandler.ACTION_ALERT || !CommandeHandler.estPourCetAppareil(
                message.data["appareil_id"], monAppareilId
            )
        ) {
            showAlertNotification(
                message.data["title"] ?: message.notification?.title ?: "AntiVol",
                message.data["body"] ?: message.notification?.body ?: "Notification"
            )
            return
        }

        val titre = message.data["title"] ?: "Appareil verrouillé"
        val corps = message.data["body"] ?: "Verrouillage à distance activé"

        when (action) {
            CommandeHandler.ACTION_LOCK -> {
                Log.i(TAG, "Commande LOCK reçue pour l'appareil $monAppareilId")
                CommandeHandler.verifierAdmin(this)
                CommandeHandler.verrouiller(this, titre, corps)
            }
            CommandeHandler.ACTION_UNLOCK -> {
                Log.i(TAG, "Commande UNLOCK reçue")
                CommandeHandler.deverrouiller(this)
            }
            CommandeHandler.ACTION_LOCATE -> {
                Log.i(TAG, "Commande LOCATE reçue pour l'appareil $monAppareilId")
                // Le service de surveillance détient le client GPS : c'est lui
                // qui prend et envoie la position. On le relance au cas où.
                CommandeHandler.localiser(this)
            }
        }
    }

    private fun showAlertNotification(title: String, body: String) {
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_ALARM)

        (getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager)
            ?.notify(System.currentTimeMillis().toInt(), builder.build())
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Alertes AntiVol",
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

    private fun sendTokenToServer(token: String) {
        scope.launch {
            try {
                val apiUrl = prefsManager.getApiUrlSync()
                // Garde-fou local : sans session, le serveur refuse l'appel.
                // Ce n'est pas une identité — le compte est déduit du cookie.
                if (prefsManager.getUserIdSync() == -1) return@launch

                val api = com.antivol.mobile.data.api.RetrofitClient.getApiService(apiUrl)
                api.registerFcmToken(com.antivol.mobile.data.model.FcmTokenRequest(token))
                Log.i(TAG, "Token FCM envoyé au serveur")
            } catch (e: Exception) {
                Log.e(TAG, "Erreur envoi token: ${e.message}")
            }
        }
    }
}
