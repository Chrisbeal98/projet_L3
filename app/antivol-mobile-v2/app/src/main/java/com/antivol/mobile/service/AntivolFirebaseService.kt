package com.antivol.mobile.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.antivol.mobile.receiver.AdminReceiver
import com.antivol.mobile.ui.lock.LockActivity
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
        Log.i(TAG, "Nouveau token FCM: $token")
        sendTokenToServer(token)
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        Log.i(TAG, "Message FCM: ${message.data}")

        val action = message.data["action"]
        when (action) {
            "lock" -> lockDevice()
            "unlock" -> unlockDevice()
            "alert" -> {
                val title = message.data["title"] ?: "AntiVol Alerte"
                val body = message.data["body"] ?: "Action requise"
                showAlertNotification(title, body)
            }
        }

        message.notification?.let {
            showAlertNotification(it.title ?: "AntiVol", it.body ?: "Notification")
        }
    }

    private fun lockDevice() {
        val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager
        val admin = ComponentName(this, AdminReceiver::class.java)
        if (dpm != null && dpm.isAdminActive(admin)) {
            dpm.lockNow()
        }
        val intent = Intent(this, LockActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        }
        startActivity(intent)
    }

    private fun unlockDevice() {
        sendBroadcast(Intent("com.antivol.mobile.ACTION_UNLOCK"))
        startService(Intent(this, MonitorService::class.java))
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
                val userId = prefsManager.getUserIdSync()
                if (userId == -1) return@launch

                val api = com.antivol.mobile.data.api.RetrofitClient.getApiService(apiUrl)
                api.registerFcmToken(com.antivol.mobile.data.model.FcmTokenRequest(userId, token))
                Log.i(TAG, "Token FCM envoyé au serveur")
            } catch (e: Exception) {
                Log.e(TAG, "Erreur envoi token: ${e.message}")
            }
        }
    }
}
