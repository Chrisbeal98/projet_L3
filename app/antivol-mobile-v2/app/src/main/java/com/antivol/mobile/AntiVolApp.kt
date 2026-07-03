package com.antivol.mobile

import android.app.Application
import com.antivol.mobile.data.PreferencesManager

class AntiVolApp : Application() {
    lateinit var preferencesManager: PreferencesManager
        private set

    override fun onCreate() {
        super.onCreate()
        preferencesManager = PreferencesManager(this)
    }
}
