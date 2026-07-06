package com.antivol.mobile;

import android.app.admin.DevicePolicyManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.telephony.TelephonyManager;
import android.util.Log;

public class SimChangeReceiver extends BroadcastReceiver {

    private static final String TAG = "SimChange";
    private static final String PREFS = "antivol_sim";
    private static final String KEY_SIM_SERIAL = "sim_serial";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (TelephonyManager.ACTION_SIM_STATE_CHANGED.equals(action)) {
            String state = intent.getStringExtra(TelephonyManager.EXTRA_SIM_STATE);
            if ("ABSENT".equals(state)) {
                Log.w(TAG, "SIM retiree !");
                lockAndAlert(context, "SIM RETIREE");
            } else if ("LOADED".equals(state)) {
                checkSimChange(context);
            }
        }
    }

    private void checkSimChange(Context context) {
        try {
            TelephonyManager tm = (TelephonyManager) context.getSystemService(Context.TELEPHONY_SERVICE);
            String newSimSerial = tm.getSimSerialNumber();

            SharedPreferences prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            String savedSimSerial = prefs.getString(KEY_SIM_SERIAL, null);

            if (savedSimSerial == null) {
                prefs.edit().putString(KEY_SIM_SERIAL, newSimSerial != null ? newSimSerial : "").apply();
                return;
            }

            if (newSimSerial != null && !newSimSerial.equals(savedSimSerial)) {
                Log.w(TAG, "SIM changee ! Ancienne: " + savedSimSerial + " Nouvelle: " + newSimSerial);
                lockAndAlert(context, "SIM CHANGEE");
            }
        } catch (SecurityException e) {
            Log.e(TAG, "Permission READ_PHONE_STATE requise", e);
        }
    }

    private void lockAndAlert(Context context, String reason) {
        new Thread(() -> {
            try {
                int appareilId = AppConfig.getAppareilId(context);
                if (appareilId == -1) return;

                String apiUrl = AppConfig.getApiUrl(context);
                org.json.JSONObject json = new org.json.JSONObject();
                json.put("appareil_id", appareilId);
                json.put("alerte", reason);

                okhttp3.MediaType JSON = okhttp3.MediaType.parse("application/json; charset=utf-8");
                okhttp3.RequestBody body = okhttp3.RequestBody.create(json.toString(), JSON);
                okhttp3.Request request = new okhttp3.Request.Builder()
                        .url(apiUrl + "/alertes/signaler")
                        .post(body)
                        .build();

                AppConfig.getHttpClient().newCall(request).execute();
            } catch (Exception ignored) {}
        }).start();

        DevicePolicyManager dpm = (DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);
        ComponentName admin = new ComponentName(context, AdminReceiver.class);
        if (dpm != null && dpm.isAdminActive(admin)) {
            dpm.lockNow();
        }

        Intent lockIntent = new Intent(context, LockActivity.class);
        lockIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(lockIntent);
    }
}
