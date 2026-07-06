package com.antivol.mobile;

import android.app.admin.DevicePolicyManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;

public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "BootReceiver";
    private static final String PREFS = "antivol_protection";
    private static final String KEY_WAS_STOLEN = "was_stolen";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())
                || "android.intent.action.QUICKBOOT_POWERON".equals(intent.getAction())) {

            Log.i(TAG, "Redemarrage detecte");

            int userId = AppConfig.getUserId(context);
            int appareilId = AppConfig.getAppareilId(context);

            if (userId == -1 || appareilId == -1) {
                Log.w(TAG, "Aucun utilisateur/appareil configure.");
                return;
            }

            SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            boolean wasStolen = prefs.getBoolean(KEY_WAS_STOLEN, false);

            if (wasStolen) {
                Log.w(TAG, "Appareil etait en mode vole ! Verrouillage au demarrage...");

                DevicePolicyManager dpm = (DevicePolicyManager)
                    context.getSystemService(Context.DEVICE_POLICY_SERVICE);
                ComponentName admin = new ComponentName(context, AdminReceiver.class);
                if (dpm != null && dpm.isAdminActive(admin)) {
                    dpm.lockNow();
                }

                Intent lockIntent = new Intent(context, LockActivity.class);
                lockIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                lockIntent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);
                context.startActivity(lockIntent);

                new Thread(() -> {
                    try {
                        String apiUrl = AppConfig.getApiUrl(context);
                        org.json.JSONObject json = new org.json.JSONObject();
                        json.put("appareil_id", appareilId);
                        json.put("alerte", "ALLUMAGE_APRES_VOL");

                        okhttp3.MediaType JSON = okhttp3.MediaType.parse("application/json; charset=utf-8");
                        okhttp3.RequestBody body = okhttp3.RequestBody.create(json.toString(), JSON);
                        okhttp3.Request request = new okhttp3.Request.Builder()
                            .url(apiUrl + "/mobile/stolen-alert")
                            .post(body)
                            .build();
                        AppConfig.getHttpClient().newCall(request).execute();
                        Log.i(TAG, "Alerte allumage apres vol envoyee au serveur");
                    } catch (Exception e) {
                        Log.e(TAG, "Erreur envoi alerte allumage", e);
                    }
                }).start();
            }

            Intent serviceIntent = new Intent(context, MonitorService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent);
            } else {
                context.startService(serviceIntent);
            }

            Log.i(TAG, "MonitorService relance apres redemarrage");
        }
    }
}
