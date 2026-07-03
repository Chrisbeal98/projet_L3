package com.antivol.mobile.receiver

import android.app.admin.DeviceAdminReceiver
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.Toast

class AdminReceiver : DeviceAdminReceiver() {

    override fun onEnabled(context: Context, intent: Intent) {
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager
        val admin = ComponentName(context, AdminReceiver::class.java)
        dpm?.setLockTaskPackages(admin, arrayOf(context.packageName))
        Toast.makeText(context, "Protection AntiVol activée", Toast.LENGTH_LONG).show()
    }

    override fun onDisabled(context: Context, intent: Intent) {
        Toast.makeText(context, "⚠️ Protection AntiVol désactivée !", Toast.LENGTH_LONG).show()
        val dpm = context.getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager
        val admin = ComponentName(context, AdminReceiver::class.java)
        if (dpm != null && !dpm.isAdminActive(admin)) {
            Intent(context, com.antivol.mobile.MainActivity::class.java).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                context.startActivity(this)
            }
        }
    }

    override fun onDisableRequested(context: Context, intent: Intent): CharSequence {
        return "La protection Admin est nécessaire pour le verrouillage à distance. " +
               "Si vous désactivez cette protection, l'AntiVol ne pourra plus verrouiller " +
               "votre appareil en cas de vol. Êtes-vous sûr ?"
    }
}
