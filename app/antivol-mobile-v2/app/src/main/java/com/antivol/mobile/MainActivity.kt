package com.antivol.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.antivol.mobile.ui.alerts.AlertesScreen
import com.antivol.mobile.ui.auth.AuthViewModel
import com.antivol.mobile.ui.auth.LoginScreen
import com.antivol.mobile.ui.auth.RegisterScreen
import com.antivol.mobile.ui.dashboard.DashboardScreen
import com.antivol.mobile.ui.navigation.Screen
import com.antivol.mobile.ui.profile.ProfileScreen
import com.antivol.mobile.ui.settings.SettingsScreen
import com.antivol.mobile.ui.splash.SplashScreen
import com.antivol.mobile.ui.splash.SplashViewModel
import com.antivol.mobile.ui.theme.AntiVolTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val app = application as AntiVolApp
        val preferencesManager = app.preferencesManager

        enableEdgeToEdge()

        setContent {
            AntiVolTheme {
                val navController = rememberNavController()

                val splashViewModel = remember { SplashViewModel(preferencesManager) }
                val splashState by splashViewModel.state.collectAsStateWithLifecycle()

                val authViewModel: AuthViewModel = remember {
                    AuthViewModel(preferencesManager)
                }

                NavHost(
                    navController = navController,
                    startDestination = Screen.Splash.route,
                    modifier = Modifier.fillMaxSize()
                ) {
                    composable(Screen.Splash.route) {
                        SplashScreen()
                        LaunchedEffect(splashState) {
                            if (!splashState.isLoading) {
                                val destination = if (splashState.isLoggedIn)
                                    Screen.Dashboard.route else Screen.Login.route
                                navController.navigate(destination) {
                                    popUpTo(Screen.Splash.route) { inclusive = true }
                                }
                            }
                        }
                    }

                    composable(Screen.Login.route) {
                        LoginScreen(
                            onNavigateToRegister = { navController.navigate(Screen.Register.route) },
                            onLoginSuccess = {
                                navController.navigate(Screen.Dashboard.route) {
                                    popUpTo(0) { inclusive = true }
                                }
                            },
                            onNavigateToSettings = { navController.navigate(Screen.Settings.route) },
                            viewModel = authViewModel
                        )
                    }

                    composable(Screen.Register.route) {
                        RegisterScreen(
                            onNavigateToLogin = { navController.popBackStack() },
                            onRegisterSuccess = {
                                navController.navigate(Screen.Dashboard.route) {
                                    popUpTo(0) { inclusive = true }
                                }
                            },
                            viewModel = authViewModel
                        )
                    }

                    composable(Screen.Dashboard.route) {
                        DashboardScreen(
                            onNavigateToSettings = { navController.navigate(Screen.Settings.route) },
                            onNavigateToAlertes = { navController.navigate(Screen.Alertes.route) },
                            onNavigateToProfile = { navController.navigate(Screen.Profile.route) }
                        )
                    }

                    composable(Screen.Settings.route) {
                        SettingsScreen(
                            onNavigateBack = { navController.popBackStack() },
                            onLogout = {
                                navController.navigate(Screen.Login.route) {
                                    popUpTo(0) { inclusive = true }
                                }
                            }
                        )
                    }

                    composable(Screen.Alertes.route) {
                        AlertesScreen(
                            onNavigateBack = { navController.popBackStack() }
                        )
                    }

                    composable(Screen.Profile.route) {
                        ProfileScreen(
                            onNavigateBack = { navController.popBackStack() }
                        )
                    }
                }
            }
        }
    }
}
