package com.antivol;

import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

import androidx.annotation.NonNull;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Map;

public class AntivolFirebaseService extends FirebaseMessagingService {
    private static final String TAG = "FCMService";
    private static final String PREF_NAME = "antivol_prefs";

    @Override
    public void onNewToken(@NonNull String token) {
        super.onNewToken(token);
        Log.d(TAG, "Nouveau token FCM: " + token);
        sendTokenToServer(token);
    }

    @Override
    public void onMessageReceived(@NonNull RemoteMessage message) {
        super.onMessageReceived(message);
        Log.d(TAG, "Message FCM reçu");

        Map<String, String> data = message.getData();
        String command = data.get("command");
        String title = message.getNotification() != null ? message.getNotification().getTitle() : "";
        String body = message.getNotification() != null ? message.getNotification().getBody() : "";

        if (command == null && title != null) {
            String upper = title.toUpperCase();
            if (upper.contains("VOL") || upper.contains("STOLEN")) command = "VOL";
            else if (upper.contains("PERTE") || upper.contains("LOST")) command = "PERTE";
            else if (upper.contains("LOCK") || upper.contains("VERROUILL")) command = "LOCK";
            else if (upper.contains("UNLOCK") || upper.contains("DEVERROUILL")) command = "UNLOCK";
        }

        if (command != null) {
            handleCommand(command, title, body);
        }
    }

    private void handleCommand(String command, String title, String body) {
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        String myUuid = prefs.getString("device_uuid", "");
        if (body != null && body.contains(myUuid)) return;

        String cmd = command.toUpperCase().trim();

        if ("LOCK".equals(cmd) || "VOL".equals(cmd) || "PERTE".equals(cmd)) {
            Log.d(TAG, "FCM: commande LOCK reçue → verrouillage instantané");
            SharedPreferences.Editor ed = prefs.edit();
            ed.putBoolean("was_locked", true);
            if ("VOL".equals(cmd)) ed.putBoolean("was_stolen", true);
            ed.apply();

            Intent lockIntent = new Intent(this, LockActivity.class);
            lockIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_NO_ANIMATION
                | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
            startActivity(lockIntent);

        } else if ("UNLOCK".equals(cmd)) {
            Log.d(TAG, "FCM: commande UNLOCK reçue");
            prefs.edit().putBoolean("was_locked", false).apply();
        }
    }

    private void sendTokenToServer(String token) {
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        String uuid = prefs.getString("device_uuid", null);
        if (uuid == null) return;

        new Thread(() -> {
            try {
                String serverUrl = getString(R.string.server_url);
                JSONObject data = new JSONObject();
                data.put("device_uuid", uuid);
                data.put("fcm_token", token);

                URL url = new URL(serverUrl + "/api/fcm/register-token");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setConnectTimeout(15000);
                conn.setDoOutput(true);

                OutputStream os = conn.getOutputStream();
                os.write(data.toString().getBytes());
                os.close();
                conn.getResponseCode();
                conn.disconnect();
                Log.d(TAG, "Token FCM envoyé au serveur");
            } catch (Exception e) {
                Log.e(TAG, "Erreur envoi token FCM", e);
            }
        }).start();
    }
}
