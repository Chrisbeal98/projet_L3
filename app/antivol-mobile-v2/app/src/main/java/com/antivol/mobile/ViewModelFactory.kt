package com.antivol.mobile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import com.antivol.mobile.data.PreferencesManager
import com.antivol.mobile.ui.auth.AuthViewModel
import com.antivol.mobile.ui.dashboard.DashboardViewModel
import com.antivol.mobile.ui.alerts.AlertsViewModel

class ViewModelFactory(private val preferencesManager: PreferencesManager) : ViewModelProvider.Factory {
    @Suppress("UNCHECKED_CAST")
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        return when {
            modelClass.isAssignableFrom(AuthViewModel::class.java) ->
                AuthViewModel(preferencesManager) as T
            modelClass.isAssignableFrom(DashboardViewModel::class.java) ->
                DashboardViewModel(preferencesManager) as T
            modelClass.isAssignableFrom(AlertsViewModel::class.java) ->
                AlertsViewModel(preferencesManager) as T
            else -> throw IllegalArgumentException("Unknown ViewModel class: ${modelClass.name}")
        }
    }
}
