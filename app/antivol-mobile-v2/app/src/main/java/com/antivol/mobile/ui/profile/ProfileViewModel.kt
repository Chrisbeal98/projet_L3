package com.antivol.mobile.ui.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.antivol.mobile.data.PreferencesManager
import com.antivol.mobile.data.api.RetrofitClient
import com.antivol.mobile.data.model.UserData
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Profil de l'utilisateur connecté.
 *
 * ─── Pourquoi cet écran a sa propre couche ───
 *
 * Il lisait directement les préférences et se construisait son propre client
 * HTTP « à la main ». Deux conséquences, toutes deux silencieuses :
 *
 *  1. Il lisait le fichier de préférences `"antivol_prefs"`, qui n'est PAS
 *     celui où `PreferencesManager` écrit (le miroir `SharedPreferences`
 *     s'appelle `antivol_prefs_sync`). `user_id` valait donc toujours -1 et
 *     l'écran abandonnait avant même d'appeler le serveur : profil vide.
 *
 *  2. Il construisait un `OkHttpClient()` neuf, sans le `SessionCookieJar` ni
 *     l'intercepteur `X-Device-Token`. Le serveur répondait 401 « Non
 *     authentifié » — et, là encore, sans le moindre message.
 *
 * Passer par `RetrofitClient.getApiService()` et `PreferencesManager` règle les
 * deux d'un coup : il n'y a plus qu'un seul client HTTP dans l'application, et
 * il porte par construction la session et le secret d'appareil.
 *
 * Aucun `user_id` n'est transmis : le serveur déduit l'utilisateur du cookie
 * de session.
 */
data class ProfileState(
    val isLoading: Boolean = false,
    val user: UserData? = null,
    /** Message d'erreur affichable, ou null. */
    val error: String? = null
)

class ProfileViewModel(
    private val preferencesManager: PreferencesManager
) : ViewModel() {

    private val _state = MutableStateFlow(ProfileState())
    val state: StateFlow<ProfileState> = _state.asStateFlow()

    init {
        charger()
    }

    fun charger() {
        _state.update { it.copy(isLoading = true, error = null) }
        viewModelScope.launch {
            try {
                // Garde-fou local : évite un aller-retour inutile, et évite
                // d'afficher une erreur réseau alors que l'utilisateur n'est
                // simplement pas connecté.
                if (preferencesManager.getUserIdSync() == -1) {
                    _state.update {
                        it.copy(isLoading = false, error = "Aucune session ouverte")
                    }
                    return@launch
                }

                val apiUrl = preferencesManager.apiUrl.first()
                val api = RetrofitClient.getApiService(apiUrl)
                val reponse = api.getProfile()

                if (reponse.isSuccessful) {
                    val utilisateur = reponse.body()?.user
                    if (utilisateur == null) {
                        _state.update {
                            it.copy(isLoading = false, error = "Profil vide renvoyé par le serveur")
                        }
                    } else {
                        _state.update {
                            it.copy(isLoading = false, user = utilisateur, error = null)
                        }
                    }
                } else {
                    _state.update {
                        it.copy(isLoading = false, error = messageErreur(reponse.code(), reponse.errorBody()?.string()))
                    }
                }
            } catch (e: Exception) {
                // Silencieux jusqu'ici : l'utilisateur voyait un profil vide
                // sans comprendre pourquoi. Un réseau coupé et un serveur en
                // panne sont deux situations différentes, et l'utilisateur doit
                // pouvoir les distinguer.
                _state.update {
                    it.copy(
                        isLoading = false,
                        error = "Impossible de joindre le serveur. Vérifiez la connexion et l'URL dans les paramètres."
                    )
                }
            }
        }
    }

    /** Traduit un code HTTP et un corps d'erreur en message lisible. */
    private fun messageErreur(code: Int, corps: String?): String {
        val detail = try {
            corps?.takeIf { it.isNotBlank() }
                ?.let { JSONObject(it).optString("error") }
                ?.takeIf { it.isNotBlank() }
        } catch (_: Exception) {
            null
        }
        return when {
            detail != null -> detail
            code == 401 -> "Session expirée, reconnectez-vous"
            code == 403 -> "Accès refusé"
            else -> "Erreur du serveur (HTTP $code)"
        }
    }
}
