package com.antivol.mobile.ui.splash

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.antivol.mobile.data.PreferencesManager
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

data class SplashState(
    val isLoading: Boolean = true,
    val isLoggedIn: Boolean = false
)

class SplashViewModel(
    private val preferencesManager: PreferencesManager
) : ViewModel() {

    private val _state = MutableStateFlow(SplashState())
    val state: StateFlow<SplashState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            preferencesManager.isLoggedIn.collect { loggedIn ->
                _state.update { it.copy(isLoading = false, isLoggedIn = loggedIn) }
            }
        }
    }
}
