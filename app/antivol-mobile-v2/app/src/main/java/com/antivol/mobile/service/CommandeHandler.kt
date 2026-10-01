package com.antivol.mobile.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.antivol.mobile.receiver.AdminReceiver
import com.antivol.mobile.ui.lock.LockActivity

/**
 * Point d'entrée unique des commandes poussées par le serveur (ntfy + FCM).
 *
 * Le backend envoie la commande dans deux cles : "action" (canonique, minuscule)
 * et "command" (historique, en majuscules). Les deux sont acceptées ici.
 */
object CommandeHandler {

    private const val TAG = "CommandeHandler"
    private const val CHANNEL_ID = "antivol_alerts"
    private const val NOTIFICATION_ID_LOCK = 9001

    const val ACTION_LOCK = "lock"
    const val ACTION_UNLOCK = "unlock"
    const val ACTION_ALERT = "alert"
    const val ACTION_LOCATE = "locate"

    /**
     * Diffusion interne qui demande une position immédiate.
     *
     * Le service de surveillance est le seul à détenir le client GPS : c'est
     * donc lui qui traite la demande. Le broadcast est émis en interne
     * (`setPackage`) et non exporté, pour qu'une autre application ne puisse
     * pas déclencher une prise de position à l'insu de l'utilisateur.
     */
    const val ACTION_LOCATE_IMMEDIAT = "com.antivol.mobile.ACTION_LOCATE_IMMEDIAT"

    private val COMMANDES = mapOf(
        "LOCK" to ACTION_LOCK,
        "VERROUILLER" to ACTION_LOCK,
        "VOL" to ACTION_LOCK,
        "PERTE" to ACTION_LOCK,
        "UNLOCK" to ACTION_UNLOCK,
        "DEVERROUILLER" to ACTION_UNLOCK,
        "ALERTE" to ACTION_ALERT,
        "ALERT" to ACTION_ALERT,
        "COMMUNITY_ALERT" to ACTION_ALERT,
        "LOCATE" to ACTION_LOCATE,
        "LOCALISER" to ACTION_LOCATE
    )

    /**
     * Traduit la commande reçue en action normalisée, ou null si inconnue.
     */
    fun normaliser(action: String?, commande: String?): String? {
        val candidat = action?.takeIf { it.isNotBlank() } ?: commande?.takeIf { it.isNotBlank() }
            ?: return null
        return COMMANDES[candidat.trim().uppercase()]
    }

    /**
     * La commande ne concerne cet appareil que si l'id envoyé correspond à celui
     * enregistré localement. Sans ce filtre, une alerte communautaire concernant
     * un autre téléphone verrouillerait le mauvais appareil.
     */
    fun estPourCetAppareil(appareilIdEnvoye: String?, monAppareilId: Int): Boolean {
        if (appareilIdEnvoye.isNullOrBlank()) return true
        val cible = appareilIdEnvoye.trim()
        return cible.isEmpty() || cible == "0" ||
            (monAppareilId != -1 && cible == monAppareilId.toString())
    }

    fun verifierAdmin(context: Context): Boolean {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager
        val admin = ComponentName(context, AdminReceiver::class.java)
        val actif = dpm != null && dpm.isAdminActive(admin)
        if (!actif) {
            Log.w(TAG, "Device Admin inactif : lockNow() ignoré, l'écran de verrouillage ne s'affichera pas.")
        }
        return actif
    }

    /**
     * Verrouille l'appareil : coupure de l'écran via Device Admin, notification
     * plein écran (seule méthode fiable quand Android bloque le démarrage
     * d'activité en arrière-plan depuis Android 10), puis écran LockActivity.
     */
    fun verrouiller(context: Context, titre: String, corps: String) {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager
        val admin = ComponentName(context, AdminReceiver::class.java)
        if (dpm != null && dpm.isAdminActive(admin)) {
            try {
                dpm.lockNow()
            } catch (e: Exception) {
                Log.e(TAG, "lockNow() a échoué: ${e.message}")
            }
        } else {
            Log.w(TAG, "Device Admin inactif : verrouillage système indisponible.")
        }

        notifierPleinEcran(context, titre, corps)

        try {
            val intent = Intent(context, LockActivity::class.java).apply {
                addFlags(
                    Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_CLEAR_TOP or
                        Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS
                )
            }
            context.startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Démarrage de LockActivity impossible: ${e.message}")
        }
    }

    fun deverrouiller(context: Context) {
        try {
            context.sendBroadcast(
                Intent("com.antivol.mobile.ACTION_UNLOCK").apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    setPackage(context.packageName)
                }
            )
        } catch (e: Exception) {
            Log.e(TAG, "Broadcast de déverrouillage impossible: ${e.message}")
        }
        try {
            context.startService(Intent(context, MonitorService::class.java))
        } catch (e: Exception) {
            Log.e(TAG, "MonitorService non relancé: ${e.message}")
        }
    }

    /**
     * Demande une position immédiate (FR-CMD-05).
     *
     * Le service de surveillance tourne déjà en premier plan et envoie une
     * position toutes les 30 s. Il est relancé ici s'il ne tourne plus, puis
     * prévenu par diffusion interne : il demandera un point GPS unique et
     * l'enverra aussitôt, sans attendre le cycle suivant.
     */
    fun localiser(context: Context) {
        try {
            context.startService(Intent(context, MonitorService::class.java))
        } catch (e: Exception) {
            Log.e(TAG, "Relance du MonitorService impossible: ${e.message}")
        }
        try {
            context.sendBroadcast(
                Intent(ACTION_LOCATE_IMMEDIAT).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    setPackage(context.packageName)
                }
            )
        } catch (e: Exception) {
            Log.e(TAG, "Demande de localisation impossible: ${e.message}")
        }
    }

    fun afficherNotification(context: Context, titre: String, corps: String) {
        creerCanal(context)
        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle(titre)
            .setContentText(corps)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_ALARM)

        (context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager)
            ?.notify((System.currentTimeMillis() and 0xFFFF).toInt(), builder.build())
    }

    private fun notifierPleinEcran(context: Context, titre: String, corps: String) {
        creerCanal(context)
        val intent = Intent(context, LockActivity::class.java).apply {
            addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or
                    Intent.FLAG_ACTIVITY_CLEAR_TOP or
                    Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS
            )
        }
        val pending = PendingIntent.getActivity(
            context,
            NOTIFICATION_ID_LOCK,
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle(titre)
            .setContentText(corps)
            .setPriority(NotificationCompat.PRIORITY_MAX)
            .setCategory(NotificationCompat.CATEGORY_ALARM)
            .setOngoing(true)
            .setAutoCancel(false)
            .setFullScreenIntent(pending, true)
            .setContentIntent(pending)

        (context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager)
            ?.notify(NOTIFICATION_ID_LOCK, builder.build())
    }

    private fun creerCanal(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val canal = NotificationChannel(
                CHANNEL_ID, "Alertes AntiVol", NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notifications d'alerte de vol et verrouillage"
                enableVibration(true)
                lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
            }
            (context.getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager)
                ?.createNotificationChannel(canal)
        }
    }
}
