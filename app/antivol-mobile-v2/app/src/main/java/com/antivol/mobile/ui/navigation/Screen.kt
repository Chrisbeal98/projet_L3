package com.antivol.mobile.ui.navigation

sealed class Screen(val route: String) {
    data object Splash : Screen("splash")
    data object Login : Screen("login")
    data object Register : Screen("register")
    data object Dashboard : Screen("dashboard")
    data object Settings : Screen("settings")
    data object Alertes : Screen("alertes")
    data object Profile : Screen("profile")
}
