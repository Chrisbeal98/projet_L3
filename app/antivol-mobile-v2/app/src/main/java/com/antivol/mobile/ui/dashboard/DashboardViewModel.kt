package com.antivol.mobile.ui.dashboard

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.Manifest
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.antivol.mobile.data.EnrollementAppareil
import com.antivol.mobile.data.PreferencesManager
import com.antivol.mobile.data.api.RetrofitClient
import com.antivol.mobile.data.model.StatsResponse
import com.antivol.mobile.data.model.DeviceStatusResponse
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class DashboardState(
    val isLoading: Boolean = false,
    val userEmail: String = "",
    val stats: StatsResponse = StatsResponse(),
    val deviceId: Int = -1,
    val deviceImei: String = "",
    val codeVerrouillage: String = "",
    val codeUssd: String = "",
    val isMonitoring: Boolean = false,
    val deviceStatus: DeviceStatusResponse? = null,
    val logs: List<String> = emptyList(),
    val error: String? = null
)

class DashboardViewModel(
    private val preferencesManager: PreferencesManager
) : ViewModel() {

    private val _state = MutableStateFlow(DashboardState())
    val state: StateFlow<DashboardState> = _state.asStateFlow()

    private var pollingJob: kotlinx.coroutines.Job? = null

    init {
        viewModelScope.launch {
            preferencesManager.userEmail.collect { email ->
                _state.update { it.copy(userEmail = email) }
            }
        }
        viewModelScope.launch {
            preferencesManager.appareilId.collect { id ->
                _state.update { it.copy(deviceId = id) }
            }
        }
        viewModelScope.launch {
            preferencesManager.appareilImei.collect { imei ->
                _state.update { it.copy(deviceImei = imei) }
            }
        }
        viewModelScope.launch {
            preferencesManager.codeVerrouillage.collect { code ->
                _state.update { it.copy(codeVerrouillage = code) }
            }
        }
        viewModelScope.launch {
            preferencesManager.codeUssd.collect { code ->
                _state.update { it.copy(codeUssd = code) }
            }
        }
        loadStats()
    }

    fun loadStats() {
        viewModelScope.launch {
            try {
                val apiUrl = preferencesManager.apiUrl.first()
                if (preferencesManager.getUserIdSync() == -1) return@launch

                val api = RetrofitClient.getApiService(apiUrl)
                val response = api.getDashboardStats()
                if (response.isSuccessful) {
                    _state.update { it.copy(stats = response.body() ?: StatsResponse()) }
                }
            } catch (_: Exception) {}
        }
    }

    /**
     * Enrôle le téléphone auprès du serveur.
     *
     * Délégué à `EnrollementAppareil` : cette méthode NE FABRIQUE PAS
     * d'identifiant. Elle utilisait auparavant `UUID.randomUUID()`, ce qui
     * créait un nouvel enregistrement à chaque appui sur le bouton — le
     * propriétaire finissait avec dix « appareils » pour un seul téléphone, et
     * le secret d'appareil était purement et simplement jeté.
     *
     * L'opération est idempotente : si le téléphone est déjà enrôlé, elle ne
     * refait rien. Le bouton sert donc surtout à réparer un enrôlement échoué,
     * pas à « enregistrer » à chaque fois.
     */
    fun registerDevice(context: Context) {
        viewModelScope.launch {
            try {
                _state.update { it.copy(isLoading = true) }

                if (EnrollementAppareil.enrollerSiBesoin(context.applicationContext, preferencesManager)) {
                    addLog("Appareil enregistré et protégé")
                } else {
                    addLog("Enrôlement impossible : vérifiez la connexion et l'URL du serveur")
                }
            } catch (e: Exception) {
                addLog("Erreur: ${e.message}")
            } finally {
                _state.update { it.copy(isLoading = false) }
            }
            loadStats()
        }
    }

    fun setMonitoring(active: Boolean, context: Context) {
        _state.update { it.copy(isMonitoring = active) }
        if (active) {
            val intent = Intent(context, com.antivol.mobile.service.MonitorService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
            addLog("Surveillance activée - ID: ${_state.value.deviceId}")
            startPolling()
            requestBatteryOptimization(context)
        } else {
            val intent = Intent(context, com.antivol.mobile.service.MonitorService::class.java)
            context.stopService(intent)
            addLog("Surveillance arrêtée")
            stopPolling()
        }
    }

    private fun requestBatteryOptimization(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
            if (pm != null && !pm.isIgnoringBatteryOptimizations(context.packageName)) {
                try {
                    val intent = Intent(
                        Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:${context.packageName}")
                    )
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    context.startActivity(intent)
                } catch (_: Exception) {}
            }
        }
    }

    fun checkPermission(context: Context): Boolean {
        return ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED
    }

    private fun startPolling() {
        pollingJob?.cancel()
        pollingJob = viewModelScope.launch {
            while (true) {
                checkDeviceStatus()
                delay(3000)
            }
        }
    }

    private fun stopPolling() {
        pollingJob?.cancel()
        pollingJob = null
    }

    private suspend fun checkDeviceStatus() {
        try {
            val pref = preferencesManager
            val deviceId = pref.appareilId.first()
            if (deviceId == -1) return

            val apiUrl = pref.apiUrl.first()
            val api = RetrofitClient.getApiService(apiUrl)
            val response = api.getDeviceStatus(deviceId)
            if (response.isSuccessful) {
                _state.update { it.copy(deviceStatus = response.body()) }
            }
        } catch (_: Exception) {}
    }

    fun openLocation(context: Context) {
        val deviceId = _state.value.deviceId
        if (deviceId == -1) return
        viewModelScope.launch {
            val baseUrl = preferencesManager.apiUrl.first().replace("/api", "")
            val url = "$baseUrl/dashboard/carte?appareil_id=$deviceId"
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(intent)
        }
    }

    /**
     * Déconnexion.
     *
     * `clearSession` et non `clearAll` : on efface le compte et l'enrôlement,
     * mais on garde l'URL du serveur. La ressaisir à chaque déconnexion
     * n'ajouterait que de la pénibilité — et ce n'est pas un secret.
     */
    fun logout(context: Context) {
        stopPolling()
        RetrofitClient.clearCookies()
        viewModelScope.launch {
            preferencesManager.clearSession()
            val intent = Intent(context, com.antivol.mobile.MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            }
            context.startActivity(intent)
        }
    }

    private fun addLog(message: String) {
        val time = java.text.SimpleDateFormat.getTimeInstance().format(java.util.Date())
        _state.update { it.copy(logs = it.logs + "[$time] $message") }
    }
}
