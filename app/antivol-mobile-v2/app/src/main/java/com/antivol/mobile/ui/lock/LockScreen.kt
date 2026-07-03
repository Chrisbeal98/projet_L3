package com.antivol.mobile.ui.lock

import android.app.admin.DevicePolicyManager
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.view.WindowManager
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.antivol.mobile.AntiVolApp
import com.antivol.mobile.data.api.RetrofitClient
import com.antivol.mobile.data.model.VerifyCodeRequest
import com.antivol.mobile.receiver.AdminReceiver
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import androidx.lifecycle.lifecycleScope

class LockActivity : ComponentActivity() {

    private var isPolling = true
    private var wakeLock: PowerManager.WakeLock? = null
    private var dpm: DevicePolicyManager? = null
    private var adminComponent: ComponentName? = null
    private var failedAttempts = 0
    private lateinit var prefsManager: com.antivol.mobile.data.PreferencesManager

    private val unlockReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if ("com.antivol.mobile.ACTION_UNLOCK" == intent.action) {
                isPolling = false
                stopLockTask()
                releaseWakeLock()
                Toast.makeText(this@LockActivity, "Déverrouillé à distance", Toast.LENGTH_SHORT).show()
                finish()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefsManager = (application as AntiVolApp).preferencesManager

        window.addFlags(
            WindowManager.LayoutParams.FLAG_FULLSCREEN or
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
            WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD or
            WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
        )

        dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager
        adminComponent = ComponentName(this, AdminReceiver::class.java)

        val pm = getSystemService(Context.POWER_SERVICE) as? PowerManager
        wakeLock = pm?.newWakeLock(
            PowerManager.FULL_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP or PowerManager.ON_AFTER_RELEASE,
            "AntiVol:LockWakeLock"
        )
        wakeLock?.acquire(10 * 60 * 1000L)

        setFinishOnTouchOutside(false)
        startLockTask()

        val audio = getSystemService(Context.AUDIO_SERVICE) as? AudioManager
        audio?.let {
            it.setStreamVolume(AudioManager.STREAM_ALARM, it.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0)
            try {
                val tg = ToneGenerator(AudioManager.STREAM_ALARM, 100)
                tg.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 2000)
            } catch (_: Exception) {}
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(unlockReceiver, IntentFilter("com.antivol.mobile.ACTION_UNLOCK"), Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            registerReceiver(unlockReceiver, IntentFilter("com.antivol.mobile.ACTION_UNLOCK"))
        }

        setContent {
            LockScreenContent(
                onUnlock = { code -> verifyCode(code) },
                onBack = {
                    Toast.makeText(this, "Appareil verrouillé", Toast.LENGTH_SHORT).show()
                },
                failedAttempts = failedAttempts
            )
        }

        lifecycleScope.launch {
            while (isPolling) {
                checkServerStatus()
                delay(3000)
            }
        }
    }

    private suspend fun checkServerStatus() {
        try {
            val deviceId = prefsManager.getAppareilIdSync()
            val apiUrl = prefsManager.getApiUrlSync()
            if (deviceId == -1) return

            val api = RetrofitClient.getApiService(apiUrl)
            val response = api.getDeviceStatus(deviceId)
            if (response.isSuccessful) {
                val verrouille = response.body()?.verrouille ?: true
                if (!verrouille) {
                    isPolling = false
                    failedAttempts = 0
                    stopLockTask()
                    releaseWakeLock()
                    Toast.makeText(this@LockActivity, "Déverrouillé à distance", Toast.LENGTH_SHORT).show()
                    finish()
                }
            }
        } catch (_: Exception) {}
    }

    private fun verifyCode(code: String) {
        lifecycleScope.launch {
            try {
                val deviceId = prefsManager.getAppareilIdSync()
                val apiUrl = prefsManager.getApiUrlSync()
                if (deviceId == -1) return@launch

                val api = RetrofitClient.getApiService(apiUrl)
                val response = api.verifyCode(deviceId, VerifyCodeRequest(code))
                if (response.isSuccessful) {
                    isPolling = false
                    failedAttempts = 0
                    stopLockTask()
                    releaseWakeLock()
                    Toast.makeText(this@LockActivity, "Déverrouillé", Toast.LENGTH_SHORT).show()
                    finish()
                } else {
                    failedAttempts++
                    val remaining = 5 - failedAttempts
                    if (remaining <= 0) {
                        dpm?.lockNow()
                    }
                }
            } catch (_: Exception) {}
        }
    }

    override fun onBackPressed() {
        Toast.makeText(this, "Appareil verrouillé", Toast.LENGTH_SHORT).show()
    }

    override fun onDestroy() {
        super.onDestroy()
        isPolling = false
        try { stopLockTask() } catch (_: Exception) {}
        releaseWakeLock()
        try { unregisterReceiver(unlockReceiver) } catch (_: Exception) {}
    }

    private fun releaseWakeLock() {
        if (wakeLock?.isHeld == true) {
            try { wakeLock?.release() } catch (_: Exception) {}
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (!hasFocus && isPolling) {
            dpm?.lockNow()
            val intent = Intent(this, LockActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
            }
            startActivity(intent)
        }
    }
}

@Composable
private fun LockScreenContent(
    onUnlock: (String) -> Unit,
    onBack: () -> Unit,
    failedAttempts: Int
) {
    var code by remember { mutableStateOf("") }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(32.dp)
        ) {
            Text("🔒", fontSize = 64.sp)
            Spacer(modifier = Modifier.height(16.dp))
            Text(
                "Appareil verrouillé",
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.error
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                "Entrez le code de sécurité pour déverrouiller",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center
            )

            Spacer(modifier = Modifier.height(32.dp))

            OutlinedTextField(
                value = code,
                onValueChange = { if (it.length <= 6) code = it },
                label = { Text("Code à 4 chiffres") },
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )

            if (failedAttempts > 0) {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    "Tentatives: $failedAttempts/5",
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            Button(
                onClick = { onUnlock(code) },
                enabled = code.length >= 4,
                modifier = Modifier.fillMaxWidth().height(50.dp),
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
            ) {
                Text("Déverrouiller")
            }
        }
    }
}
