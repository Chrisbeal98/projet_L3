package com.antivol;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.IBinder;
import android.util.Log;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class LockService extends Service {
    private static final String TAG = "LockService";
    private static final int POLL_INTERVAL = 10000;
    private static final String PREF_NAME = "antivol_prefs";
    private static final String KEY_DEVICE_UUID = "device_uuid";
    private static final String CHANNEL_ID = "antivol_lock_channel";
    private static final int NOTIF_ID = 1001;

    private Thread pollThread;
    private volatile boolean running = false;
    private String serverUrl;
    private boolean lastVerrouilleState = false;

    @Override
    public void onCreate() {
        super.onCreate();
        serverUrl = getString(R.string.server_url);
        createNotificationChannel();
        startForeground(NOTIF_ID, buildNotification(false, ""));
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

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "AntiVol - Protection",
                NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Service de protection AntiVol");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification(boolean verrouille, String code) {
        String title = verrouille ? "APPAREIL VERROUILLÉ" : "AntiVol actif";
        String text = verrouille
            ? ("Code déverrouillage: " + code)
            : "Protection en cours...";

        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }
        return builder
            .setContentTitle(title)
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setOngoing(true)
            .build();
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
                try { Thread.sleep(POLL_INTERVAL); } catch (InterruptedException ex) { break; }
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
                String lockCode = json.optString("code_verrouillage", "");
                String statut = json.optString("statut", "");

                if (verrouille != lastVerrouilleState) {
                    lastVerrouilleState = verrouille;
                    Intent intent = new Intent(verrouille ? "com.antivol.LOCK_DEVICE" : "com.antivol.UNLOCK_DEVICE");
                    intent.putExtra("code_verrouillage", lockCode);
                    sendBroadcast(intent);

                    SharedPreferences.Editor ed = prefs.edit();
                    ed.putBoolean("was_locked", verrouille);
                    if (verrouille && "vole".equals(statut)) {
                        ed.putBoolean("was_stolen", true);
                    }
                    ed.apply();
                }

                Notification notif = buildNotification(verrouille, lockCode);
                NotificationManager nm = getSystemService(NotificationManager.class);
                if (nm != null) nm.notify(NOTIF_ID, notif);
            }
            conn.disconnect();
        } catch (Exception e) {
            Log.e(TAG, "Erreur requete status", e);
        }
    }
}
