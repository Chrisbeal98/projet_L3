package com.antivol.mobile;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "BootReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())
                || "android.intent.action.QUICKBOOT_POWERON".equals(intent.getAction())) {

            Log.i(TAG, "Redémarrage détecté, relance du service de surveillance");

            int userId = AppConfig.getUserId(context);
            int appareilId = AppConfig.getAppareilId(context);

            if (userId == -1 || appareilId == -1) {
                Log.w(TAG, "Aucun utilisateur/appareil configuré. Surveillance non démarrée.");
                return;
            }

            Intent serviceIntent = new Intent(context, MonitorService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent);
            } else {
                context.startService(serviceIntent);
            }

            Log.i(TAG, "Service MonitorService relancé après redémarrage");
        }
    }
}
