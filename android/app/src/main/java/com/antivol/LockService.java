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

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.HashSet;
import java.util.Set;

public class LockService extends Service {
    private static final String TAG = "LockService";
    private static final int POLL_INTERVAL = 10000;
    private static final int COMMUNITY_POLL_INTERVAL = 30000;
    private static final int NTFY_POLL_INTERVAL = 30000;
    private static final String PREF_NAME = "antivol_prefs";
    private static final String KEY_DEVICE_UUID = "device_uuid";
    private static final String PREF_SEEN_STOLEN = "seen_stolen_ids";
    private static final String PREF_SEEN_NTFY = "seen_ntfy_ids";
    private static final String CHANNEL_ID = "antivol_lock_channel";
    private static final String COMMUNITY_CHANNEL_ID = "antivol_community_channel";
    private static final int NOTIF_ID = 1001;
    private static final int COMMUNITY_NOTIF_BASE = 2001;

    private Thread pollThread;
    private Thread communityPollThread;
    private Thread ntfyThread;
    private Thread personalNtfyThread;
    private volatile boolean running = false;
    private String serverUrl;
    private boolean lastVerrouilleState = false;

    @Override
    public void onCreate() {
        super.onCreate();
        serverUrl = getString(R.string.server_url);
        createNotificationChannel();
        createCommunityChannel();
        startForeground(NOTIF_ID, buildNotification(false, ""));
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        running = true;
        pollThread = new Thread(this::pollLoop);
        pollThread.start();
        communityPollThread = new Thread(this::communityPollLoop);
        communityPollThread.start();
        ntfyThread = new Thread(this::ntfyPollLoop);
        ntfyThread.start();
        personalNtfyThread = new Thread(this::personalNtfyPollLoop);
        personalNtfyThread.start();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running = false;
        if (pollThread != null) pollThread.interrupt();
        if (communityPollThread != null) communityPollThread.interrupt();
        if (ntfyThread != null) ntfyThread.interrupt();
        if (personalNtfyThread != null) personalNtfyThread.interrupt();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "AntiVol - Protection",
                NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription("Service de protection AntiVol");
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(channel);
        }
    }

    private void createCommunityChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                COMMUNITY_CHANNEL_ID, "AntiVol - Alerte Communaute",
                NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Alertes de vol de la communaute");
            channel.enableVibration(true);
            channel.setVibrationPattern(new long[]{0, 500, 200, 500});
            channel.enableLights(true);
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) manager.createNotificationChannel(channel);
        }
    }

    private Notification buildNotification(boolean verrouille, String code) {
        String title = verrouille ? "APPAREIL VERROUILLE" : "AntiVol actif";
        String text = verrouille
            ? ("Code deverrouillage: " + code)
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

    private void communityPollLoop() {
        while (running) {
            try {
                checkCommunityAlerts();
                Thread.sleep(COMMUNITY_POLL_INTERVAL);
            } catch (InterruptedException e) {
                break;
            } catch (Exception e) {
                Log.e(TAG, "Erreur polling communaute", e);
                try { Thread.sleep(COMMUNITY_POLL_INTERVAL); } catch (InterruptedException ex) { break; }
            }
        }
    }

    private void ntfyPollLoop() {
        while (running) {
            try {
                checkNtfyAlerts();
                Thread.sleep(NTFY_POLL_INTERVAL);
            } catch (InterruptedException e) {
                break;
            } catch (Exception e) {
                Log.e(TAG, "Erreur polling ntfy", e);
                try { Thread.sleep(NTFY_POLL_INTERVAL); } catch (InterruptedException ex) { break; }
            }
        }
    }

    private void personalNtfyPollLoop() {
        while (running) {
            try {
                checkPersonalNtfyAlerts();
                Thread.sleep(NTFY_POLL_INTERVAL);
            } catch (InterruptedException e) {
                break;
            } catch (Exception e) {
                Log.e(TAG, "Erreur polling ntfy personnel", e);
                try { Thread.sleep(NTFY_POLL_INTERVAL); } catch (InterruptedException ex) { break; }
            }
        }
    }

    private void checkPersonalNtfyAlerts() {
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        int userId = prefs.getInt("user_id", -1);
        if (userId <= 0) return;

        String myUuid = prefs.getString(KEY_DEVICE_UUID, "");
        String topic = "antivol-u" + userId;

        try {
            URL url = new URL("https://ntfy.sh/" + topic + "/json?poll=1&since=1m");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(35000);

            int code = conn.getResponseCode();
            if (code == 200) {
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    response.append(line);
                }
                reader.close();

                String seenStr = prefs.getString("seen_personal_ntfy", "");
                Set<String> seenIds = new HashSet<>();
                if (!seenStr.isEmpty()) {
                    for (String id : seenStr.split(",")) {
                        String trimmed = id.trim();
                        if (!trimmed.isEmpty()) seenIds.add(trimmed);
                    }
                }

                boolean changed = false;
                String[] lines = response.toString().split("\n");

                for (String jsonLine : lines) {
                    jsonLine = jsonLine.trim();
                    if (jsonLine.isEmpty()) continue;
                    try {
                        JSONObject msg = new JSONObject(jsonLine);
                        String eventId = msg.optString("id", "");
                        if (eventId.isEmpty() || seenIds.contains(eventId)) continue;

                        String msgTopic = msg.optString("topic", "");
                        String title = msg.optString("title", "");
                        String message = msg.optString("message", "");

                        if (topic.equals(msgTopic) && !title.isEmpty()) {
                            seenIds.add(eventId);
                            changed = true;

                            if (message.contains(myUuid)) continue;

                            showPersonalNotification(title, message);
                        }
                    } catch (Exception ignored) {}
                }

                if (changed) {
                    String joined = String.join(",", seenIds);
                    prefs.edit().putString("seen_personal_ntfy", joined).apply();
                }
            }
            conn.disconnect();
        } catch (Exception e) {
            Log.e(TAG, "Erreur requete ntfy personnel", e);
        }
    }

    private void showPersonalNotification(String title, String text) {
        try {
            Notification.Builder builder;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                builder = new Notification.Builder(this, COMMUNITY_CHANNEL_ID);
            } else {
                builder = new Notification.Builder(this);
            }

            Notification notif = builder
                .setContentTitle(title)
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setAutoCancel(true)
                .setDefaults(Notification.DEFAULT_ALL)
                .build();

            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.notify(COMMUNITY_NOTIF_BASE + Math.abs(title.hashCode()), notif);
            }
        } catch (Exception e) {
            Log.e(TAG, "Erreur notification personnelle", e);
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
                    SharedPreferences.Editor ed = prefs.edit();
                    ed.putBoolean("was_locked", verrouille);
                    if (verrouille && "vole".equals(statut)) {
                        ed.putBoolean("was_stolen", true);
                    }
                    ed.apply();

                    if (verrouille) {
                        Intent lockIntent = new Intent(this, LockActivity.class);
                        lockIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                            | Intent.FLAG_ACTIVITY_NO_ANIMATION
                            | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                        startActivity(lockIntent);
                    }
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

    private void checkCommunityAlerts() {
        try {
            URL url = new URL(serverUrl + "/api/mobile/community-alerts");
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
                JSONArray alertes = json.getJSONArray("alertes");

                SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
                String seenStr = prefs.getString(PREF_SEEN_STOLEN, "");
                String[] parts = seenStr.isEmpty() ? new String[0] : seenStr.split(",");
                Set<String> seenIds = new HashSet<>();
                for (String id : parts) {
                    String trimmed = id.trim();
                    if (!trimmed.isEmpty()) seenIds.add(trimmed);
                }

                String myUuid = prefs.getString(KEY_DEVICE_UUID, "");
                boolean changed = false;

                for (int i = 0; i < alertes.length(); i++) {
                    JSONObject alert = alertes.getJSONObject(i);
                    String deviceUuid = alert.optString("device_uuid", "");
                    if (deviceUuid.isEmpty() || deviceUuid.equals(myUuid)) continue;

                    int appId = alert.getInt("id");
                    String idStr = String.valueOf(appId);

                    if (!seenIds.contains(idStr)) {
                        seenIds.add(idStr);
                        changed = true;
                        showCommunityNotification(alert);
                    }
                }

                if (changed) {
                    String joined = String.join(",", seenIds);
                    prefs.edit().putString(PREF_SEEN_STOLEN, joined).apply();
                }
            }
            conn.disconnect();
        } catch (Exception e) {
            Log.e(TAG, "Erreur requete communaute", e);
        }
    }

    private void showCommunityNotification(JSONObject alert) {
        try {
            String marque = alert.optString("marque", "Inconnu");
            String modele = alert.optString("modele", "Inconnu");
            String statut = alert.optString("statut", "vole");
            double lat = alert.optDouble("latitude", 0);
            double lng = alert.optDouble("longitude", 0);

            String title = "VOL SIGNALE: " + marque + " " + modele;
            String text = "Ce telephone a ete declare " + statut + "!";
            if (lat != 0 && lng != 0) {
                text += " Position: http://maps.google.com/?q=" + lat + "," + lng;
            }

            Notification.Builder builder;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                builder = new Notification.Builder(this, COMMUNITY_CHANNEL_ID);
            } else {
                builder = new Notification.Builder(this);
            }

            Notification notif = builder
                .setContentTitle(title)
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setAutoCancel(true)
                .setDefaults(Notification.DEFAULT_ALL)
                .build();

            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.notify(COMMUNITY_NOTIF_BASE + alert.getInt("id"), notif);
            }
        } catch (Exception e) {
            Log.e(TAG, "Erreur notification communaute", e);
        }
    }

    private void checkNtfyAlerts() {
        try {
            URL url = new URL("https://ntfy.sh/antivol-community/json?poll=1&since=1m");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(35000);

            int code = conn.getResponseCode();
            if (code == 200) {
                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    response.append(line);
                }
                reader.close();

                SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
                String seenStr = prefs.getString(PREF_SEEN_NTFY, "");
                Set<String> seenIds = new HashSet<>();
                if (!seenStr.isEmpty()) {
                    for (String id : seenStr.split(",")) {
                        String trimmed = id.trim();
                        if (!trimmed.isEmpty()) seenIds.add(trimmed);
                    }
                }

                String myUuid = prefs.getString(KEY_DEVICE_UUID, "");
                boolean changed = false;
                String[] lines = response.toString().split("\n");

                for (String jsonLine : lines) {
                    jsonLine = jsonLine.trim();
                    if (jsonLine.isEmpty()) continue;
                    try {
                        JSONObject msg = new JSONObject(jsonLine);
                        String eventId = msg.optString("id", "");
                        if (eventId.isEmpty() || seenIds.contains(eventId)) continue;

                        String topic = msg.optString("topic", "");
                        String title = msg.optString("title", "");
                        String message = msg.optString("message", "");

                        if ("antivol-community".equals(topic) && !title.isEmpty()) {
                            seenIds.add(eventId);
                            changed = true;

                            String notifTitle = title;
                            String notifText = message;
                            if (message.contains(myUuid)) continue;

                            Notification.Builder builder;
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                                builder = new Notification.Builder(this, COMMUNITY_CHANNEL_ID);
                            } else {
                                builder = new Notification.Builder(this);
                            }

                            Notification notif = builder
                                .setContentTitle(notifTitle)
                                .setContentText(notifText)
                                .setSmallIcon(android.R.drawable.ic_lock_lock)
                                .setAutoCancel(true)
                                .setDefaults(Notification.DEFAULT_ALL)
                                .build();

                            NotificationManager nm = getSystemService(NotificationManager.class);
                            if (nm != null) {
                                nm.notify(COMMUNITY_NOTIF_BASE + Math.abs(eventId.hashCode()), notif);
                            }
                        }
                    } catch (Exception ignored) {}
                }

                if (changed) {
                    String joined = String.join(",", seenIds);
                    prefs.edit().putString(PREF_SEEN_NTFY, joined).apply();
                }
            }
            conn.disconnect();
        } catch (Exception e) {
            Log.e(TAG, "Erreur requete ntfy", e);
        }
    }
}
