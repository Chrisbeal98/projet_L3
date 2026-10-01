package com.antivol.mobile.ui.splash

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.antivol.mobile.data.EnrollementAppareil
import com.antivol.mobile.data.PreferencesManager
import com.antivol.mobile.service.MonitorService
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class SplashState(
    val isLoading: Boolean = true,
    val isLoggedIn: Boolean = false,
    /** Le téléphone a-t-il pu s'enrôler auprès du serveur ? */
    val appareilEnrole: Boolean = false
)

/**
 * Écran de démarrage.
 *
 * Deux responsabilités :
 *
 * 1. Aiguiller vers l'authentification ou l'accueil.
 *
 * 2. Rejouer l'enrôlement de l'appareil. Ce n'est pas redondant avec la
 *    connexion : l'enrôlement a pu échouer la première fois (coupure réseau),
 *    ou les données locales ont pu être effacées par l'utilisateur ou par le
 *    système. `enrollerSiBesoin` est idempotent — il ne refait rien si le
 *    téléphone est déjà enrôlé — donc le rappeler à chaque démarrage ne coûte
 *    qu'une lecture de préférences quand tout va bien.
 *
 * Un échec n'est pas bloquant pour l'utilisateur : il reste connecté et
 * l'enrôlement sera rejoué à la prochaine ouverture. En revanche le tableau de
 * bord le signale, parce que sans enrôlement le téléphone n'envoie aucune
 * position et ne reçoit aucune commande — autant le dire.
 */
class SplashViewModel(
    private val preferencesManager: PreferencesManager
) : ViewModel() {

    private val _state = MutableStateFlow(SplashState())
    val state: StateFlow<SplashState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            preferencesManager.isLoggedIn.collect { loggedIn ->
                if (!loggedIn) {
                    _state.update { it.copy(isLoading = false, isLoggedIn = false) }
                    return@collect
                }

                val enrole = EnrollementAppareil.enrollerSiBesoin(
                    preferencesManager.appContext,
                    preferencesManager
                )

                // Le service de surveillance n'a de sens qu'avec un appareil
                // identifié : il s'arrête dans la seconde s'il ne trouve pas
                // d'identifiant. Le démarrer quand même consommerait de la
                // batterie pour rien.
                if (enrole) {
                    MonitorService.demarrer(preferencesManager.appContext)
                }

                _state.update {
                    it.copy(
                        isLoading = false,
                        isLoggedIn = true,
                        appareilEnrole = enrole
                    )
                }
            }
        }
    }
}
