package com.antivol.mobile

import android.app.Application
import com.antivol.mobile.data.PreferencesManager
import com.antivol.mobile.data.api.RetrofitClient

class AntiVolApp : Application() {
    lateinit var preferencesManager: PreferencesManager
        private set

    override fun onCreate() {
        super.onCreate()

        preferencesManager = PreferencesManager(this)

        // Le client HTTP joint le secret d'appareil à chaque requête : il a
        // donc besoin de connaître les préférences. On l'initialise avant
        // toute activité, service ou receiver, y compris ceux lancés au
        // démarrage du système.
        RetrofitClient.init(preferencesManager)
    }
}
