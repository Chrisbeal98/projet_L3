package com.antivol;

import android.app.Service;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.IBinder;
import android.util.Log;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class LockService extends Service {
    private static final String TAG = "LockService";
    private static final int POLL_INTERVAL = 15000;
    private static final String PREF_NAME = "antivol_prefs";
    private static final String KEY_DEVICE_UUID = "device_uuid";

    private Thread pollThread;
    private volatile boolean running = false;
    private String serverUrl;

    @Override
    public void onCreate() {
        super.onCreate();
        serverUrl = getString(R.string.server_url);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        running = true;
        pollThread = new Thread(this::pollLoop);
        pollThread.start();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        if (pollThread != null) {
            pollThread.interrupt();
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void pollLoop() {
        while (running) {
            try {
                checkStatus();
                Thread.sleep(POLL_INTERVAL);
            } catch (InterruptedException e) {
                break;
            } catch (Exception e) {
                Log.e(TAG, "Erreur polling", e);
                try {
                    Thread.sleep(POLL_INTERVAL);
                } catch (InterruptedException ex) {
                    break;
                }
            }
        }
    }

    private void checkStatus() {
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        String uuid = prefs.getString(KEY_DEVICE_UUID, null);
        if (uuid == null) return;

        try {
            URL url = new URL(serverUrl + "/api/mobile/status/" + uuid);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(10000);

            int code = conn.getResponseCode();
            if (code == 200) {
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) response.append(line);
                reader.close();

                JSONObject json = new JSONObject(response.toString());
                boolean verrouille = json.getBoolean("verrouille");

                if (verrouille) {
                    String lockCode = json.optString("code_verrouillage", "");
                    Intent intent = new Intent("com.antivol.LOCK_DEVICE");
                    intent.putExtra("code_verrouillage", lockCode);
                    sendBroadcast(intent);
                } else {
                    Intent intent = new Intent("com.antivol.UNLOCK_DEVICE");
                    sendBroadcast(intent);
                }
            }
            conn.disconnect();
        } catch (Exception e) {
            Log.e(TAG, "Erreur requete status", e);
        }
    }
}
