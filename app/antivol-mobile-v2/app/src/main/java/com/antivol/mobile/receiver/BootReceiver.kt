package com.antivol.mobile.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import com.antivol.mobile.AntiVolApp

class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (Intent.ACTION_BOOT_COMPLETED == intent.action ||
            "android.intent.action.QUICKBOOT_POWERON" == intent.action
        ) {
            Log.i(TAG, "Redémarrage détecté, relance du service")

            val app = context.applicationContext as AntiVolApp
            val userId = app.preferencesManager.getUserIdSync()
            val appareilId = app.preferencesManager.getAppareilIdSync()

            if (userId == -1 || appareilId == -1) {
                Log.w(TAG, "Utilisateur/appareil non configuré")
                return
            }

            val serviceIntent = Intent(context, com.antivol.mobile.service.MonitorService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent)
            } else {
                context.startService(serviceIntent)
            }
            Log.i(TAG, "MonitorService relancé après redémarrage")
        }
    }
}
