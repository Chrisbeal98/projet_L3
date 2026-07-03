package com.antivol.mobile.ui.auth

import android.content.Context
import android.net.Uri
import android.widget.Toast
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.antivol.mobile.data.PreferencesManager
import com.antivol.mobile.data.api.RetrofitClient
import com.antivol.mobile.data.model.LoginRequest
import com.antivol.mobile.data.model.RegisterRequest
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import org.json.JSONObject

data class AuthState(
    val isLoading: Boolean = false,
    val isSuccess: Boolean = false,
    val error: String? = null
)

class AuthViewModel(
    private val preferencesManager: PreferencesManager
) : ViewModel() {

    private val _state = MutableStateFlow(AuthState())
    val state: StateFlow<AuthState> = _state.asStateFlow()

    val apiUrl = preferencesManager.apiUrl

    fun login(email: String, password: String, context: Context) {
        if (email.isBlank() || password.isBlank()) {
            _state.update { it.copy(error = "Veuillez remplir tous les champs") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            try {
                val apiUrl = preferencesManager.apiUrl.first()
                val api = RetrofitClient.getApiService(apiUrl)
                val response = api.login(LoginRequest(email.trim(), password))
                if (response.isSuccessful) {
                    val user = response.body()?.user
                    if (user != null) {
                        preferencesManager.saveUserSession(user.id, user.email)
                        _state.update { it.copy(isLoading = false, isSuccess = true) }
                    }
                } else {
                    try {
                        val errorBody = response.errorBody()?.string()
                        val msg = if (errorBody != null) {
                            JSONObject(errorBody).optString("error", "Email ou mot de passe incorrect")
                        } else "Email ou mot de passe incorrect"
                        _state.update { it.copy(isLoading = false, error = msg) }
                    } catch (_: Exception) {
                        _state.update { it.copy(isLoading = false, error = "Email ou mot de passe incorrect") }
                    }
                }
            } catch (e: Exception) {
                _state.update { it.copy(isLoading = false, error = "Erreur serveur: ${e.message}") }
            }
        }
    }

    fun register(
        nom: String, prenom: String, email: String,
        telephone: String, password: String, confirm: String,
        context: Context
    ) {
        if (nom.isBlank() || prenom.isBlank() || email.isBlank() || password.isBlank()) {
            _state.update { it.copy(error = "Veuillez remplir tous les champs obligatoires") }
            return
        }
        if (password != confirm) {
            _state.update { it.copy(error = "Les mots de passe ne correspondent pas") }
            return
        }
        if (password.length < 6) {
            _state.update { it.copy(error = "Le mot de passe doit contenir au moins 6 caractères") }
            return
        }
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            try {
                val apiUrl = preferencesManager.apiUrl.first()
                val api = RetrofitClient.getApiService(apiUrl)
                val response = api.register(
                    RegisterRequest(nom.trim(), prenom.trim(), email.trim(), telephone.trim(), password)
                )
                if (response.isSuccessful) {
                    val user = response.body()?.user
                    if (user != null) {
                        preferencesManager.saveUserSession(user.id, user.email)
                        _state.update { it.copy(isLoading = false, isSuccess = true) }
                    }
                } else {
                    try {
                        val errorBody = response.errorBody()?.string()
                        val msg = if (errorBody != null) {
                            JSONObject(errorBody).optString("error", "Erreur d'inscription")
                        } else "Erreur d'inscription"
                        _state.update { it.copy(isLoading = false, error = msg) }
                    } catch (_: Exception) {
                        _state.update { it.copy(isLoading = false, error = "Erreur d'inscription") }
                    }
                }
            } catch (e: Exception) {
                _state.update { it.copy(isLoading = false, error = "Erreur serveur: ${e.message}") }
            }
        }
    }

    fun openForgotPassword(context: Context) {
        viewModelScope.launch {
            val baseUrl = preferencesManager.apiUrl.first().replace("/api", "")
            val intent = android.content.Intent(android.content.Intent.ACTION_VIEW, Uri.parse("$baseUrl/reset-password"))
            context.startActivity(intent)
        }
    }

    fun clearError() {
        _state.update { it.copy(error = null) }
    }

    fun resetSuccess() {
        _state.update { it.copy(isSuccess = false) }
    }
}
