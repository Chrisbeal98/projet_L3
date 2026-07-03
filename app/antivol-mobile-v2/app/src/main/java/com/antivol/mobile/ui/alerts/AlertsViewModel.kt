package com.antivol.mobile.ui.alerts

import android.app.AlertDialog
import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.antivol.mobile.data.PreferencesManager
import com.antivol.mobile.data.api.RetrofitClient
import com.antivol.mobile.data.model.AlerteItem
import com.antivol.mobile.data.model.SignalerAlerteRequest
import com.antivol.mobile.data.model.ResolveAlerteRequest
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class AlertsState(
    val isLoading: Boolean = false,
    val alertes: List<AlerteItem> = emptyList(),
    val enCours: Int = 0,
    val resolues: Int = 0
)

class AlertsViewModel(
    private val preferencesManager: PreferencesManager
) : ViewModel() {

    private val _state = MutableStateFlow(AlertsState())
    val state: StateFlow<AlertsState> = _state.asStateFlow()

    fun loadAlertes() {
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true) }
            try {
                val apiUrl = preferencesManager.apiUrl.first()
                val userId = preferencesManager.userId.first()
                if (userId == -1) return@launch

                val api = RetrofitClient.getApiService(apiUrl)
                val response = api.getAlertes(mapOf("user_id" to userId))
                if (response.isSuccessful) {
                    val items = response.body() ?: emptyList()
                    val enCours = items.count { it.statut == "en_cours" }
                    val resolues = items.count { it.statut != "en_cours" }
                    _state.update { it.copy(alertes = items, enCours = enCours, resolues = resolues) }
                }
            } catch (_: Exception) {}
            _state.update { it.copy(isLoading = false) }
        }
    }

    fun resoudreAlerte(alerteId: Int) {
        viewModelScope.launch {
            try {
                val apiUrl = preferencesManager.apiUrl.first()
                val userId = preferencesManager.userId.first()
                val api = RetrofitClient.getApiService(apiUrl)
                val response = api.resoudreAlerte(alerteId, ResolveAlerteRequest(userId))
                if (response.isSuccessful) loadAlertes()
            } catch (_: Exception) {}
        }
    }

    fun signalerAlerte(context: Context, type: String) {
        viewModelScope.launch {
            try {
                val apiUrl = preferencesManager.apiUrl.first()
                val userId = preferencesManager.userId.first()
                val appareilId = preferencesManager.appareilId.first()
                if (appareilId == -1) return@launch

                val api = RetrofitClient.getApiService(apiUrl)
                api.signalerAlerte(SignalerAlerteRequest(userId, appareilId, type))
                loadAlertes()
            } catch (_: Exception) {}
        }
    }

    fun showReportDialog(context: Context) {
        AlertDialog.Builder(context).apply {
            setTitle("Signaler un vol / perte")
            setSingleChoiceItems(arrayOf("Vol", "Perte", "Anomalie"), 0) { _, _ -> }
            setPositiveButton("Signaler") { d, _ ->
                val selected = (d as AlertDialog).listView.checkedItemPosition
                val types = arrayOf("vol", "perte", "anomalie")
                signalerAlerte(context, types[selected])
            }
            setNegativeButton("Annuler", null)
        }.show()
    }
}
