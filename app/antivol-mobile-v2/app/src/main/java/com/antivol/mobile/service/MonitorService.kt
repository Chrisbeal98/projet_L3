package com.antivol.mobile.service

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
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.antivol.mobile.AntiVolApp
import com.antivol.mobile.data.api.RetrofitClient
import com.antivol.mobile.data.model.LocationUpdateRequest
import com.antivol.mobile.receiver.AdminReceiver
import com.antivol.mobile.ui.lock.LockActivity
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.util.concurrent.TimeUnit

class MonitorService : Service() {

    companion object {
        private const val TAG = "MonitorService"
        private const val NOTIFICATION_ID = 1
        private const val ALERT_NOTIFICATION_CHANNEL = "antivol_alerts"
        private const val NTFY_BASE_URL = "https://ntfy.sh"
    }

    private var dpm: DevicePolicyManager? = null
    private var adminComponent: ComponentName? = null
    private var isLocked = false
    private var fusedLocationClient: FusedLocationProviderClient? = null
    private var locationCallback: LocationCallback? = null
    private var isGpsStarted = false
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var pollingJob: Job? = null
    private var ntfyJob: Job? = null
    private var lastNtfyTimestamp: Long = System.currentTimeMillis() / 1000

    private lateinit var prefsManager: com.antivol.mobile.data.PreferencesManager

    private val unlockReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if ("com.antivol.mobile.ACTION_UNLOCK" == intent.action) {
                Log.i(TAG, "Déverrouillage via FCM")
                isLocked = false
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        prefsManager = (application as AntiVolApp).preferencesManager
        dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager
        adminComponent = ComponentName(this, AdminReceiver::class.java)
        createNotificationChannel()
        createAlertNotificationChannel()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(unlockReceiver, IntentFilter("com.antivol.mobile.ACTION_UNLOCK"), Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(unlockReceiver, IntentFilter("com.antivol.mobile.ACTION_UNLOCK"))
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIFICATION_ID, buildNotification())
        startPolling()
        startNtfySubscription()
        startLocationUpdates()
        return START_STICKY
    }

    override fun onDestroy() {
        pollingJob?.cancel()
        ntfyJob?.cancel()
        stopLocationUpdates()
        try { unregisterReceiver(unlockReceiver) } catch (_: Exception) {}
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startPolling() {
        pollingJob?.cancel()
        pollingJob = scope.launch {
            while (isActive) {
                checkStatus()
                delay(5000)
            }
        }
    }

    private fun startNtfySubscription() {
        ntfyJob?.cancel()
        ntfyJob = scope.launch {
            val userId = prefsManager.getUserIdSync()
            val topics = mutableListOf("antivol-community")
            if (userId != -1) {
                topics.add(0, "antivol-u$userId")
            }
            while (isActive) {
                for (topic in topics) {
                    try {
                        pollNtfyTopic(topic)
                    } catch (e: Exception) {
                        Log.e(TAG, "Erreur ntfy ($topic): ${e.message}")
                    }
                }
                delay(5000)
            }
        }
    }

    private fun pollNtfyTopic(topic: String) {
        val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .build()

        val url = "$NTFY_BASE_URL/$topic/json?poll=1&since=$lastNtfyTimestamp"
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
                    val dataAction = data?.optString("action") ?: ""
                    val dataAppareilId = data?.optString("appareil_id") ?: ""
                    val dataType = data?.optString("type") ?: ""

                    val msgTimestamp = json.optLong("time", 0)
                    if (msgTimestamp > lastNtfyTimestamp) {
                        lastNtfyTimestamp = msgTimestamp
                    }

                    Log.i(TAG, "Ntfy reçu ($topic): $title - $message")

                    if (dataAction == "lock" && !isLocked) {
                        isLocked = true
                        lockDevice()
                    } else if (dataAction == "unlock") {
                        isLocked = false
                        sendBroadcast(Intent("com.antivol.mobile.ACTION_UNLOCK"))
                    }

                    showAlertNotification(title, message)

                } catch (_: Exception) {}
            }
        } catch (e: Exception) {
            Log.e(TAG, "Erreur HTTP ntfy: ${e.message}")
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
                    isLocked = true
                    lockDevice()
                } else if (!verrouille) {
                    isLocked = false
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Erreur checkStatus: ${e.message}")
        }
    }

    private fun lockDevice() {
        try {
            val intent = Intent(this, LockActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            }
            startActivity(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Erreur lockDevice: ${e.message}")
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

            val request = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                LocationRequest.Builder(30000).apply {
                    setPriority(LocationRequest.PRIORITY_HIGH_ACCURACY)
                    setMinUpdateIntervalMillis(15000)
                }.build()
            } else {
                @Suppress("DEPRECATION")
                LocationRequest().apply {
                    interval = 30000
                    fastestInterval = 15000
                    priority = LocationRequest.PRIORITY_HIGH_ACCURACY
                }
            }

            if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION) == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                @Suppress("DEPRECATION")
                fusedLocationClient?.requestLocationUpdates(request, locationCallback!!, Looper.myLooper() ?: Looper.getMainLooper())
                isGpsStarted = true
            }
        } catch (e: Exception) {
            Log.e(TAG, "Erreur startLocationUpdates: ${e.message}")
        }
    }

    private fun stopLocationUpdates() {
        fusedLocationClient?.removeLocationUpdates(locationCallback ?: return)
        isGpsStarted = false
    }

    private fun sendLocation(location: Location) {
        scope.launch {
            try {
                val deviceId = prefsManager.getAppareilIdSync()
                val apiUrl = prefsManager.getApiUrlSync()
                if (deviceId == -1) return@launch

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
            }
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                "antivol_channel", "AntiVol Monitor",
                NotificationManager.IMPORTANCE_LOW
            )
            (getSystemService(Context.NOTIFICATION_SERVICE) as? NotificationManager)?.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, "antivol_channel")
        } else {
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("Antivol Intelligent")
            .setContentText("Protection active - Surveillance en cours")
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setOngoing(true)
            .build()
    }
}
