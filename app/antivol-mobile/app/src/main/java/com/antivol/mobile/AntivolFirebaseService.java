package com.antivol.mobile;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

public class AntivolFirebaseService extends FirebaseMessagingService {

    private static final String TAG = "FCM_AntiVol";
    private static final String CHANNEL_ID = "antivol_alerts";

    @Override
    public void onCreate() {
        super.onCreate();
        createNotificationChannel();
    }

    @Override
    public void onNewToken(@NonNull String token) {
        super.onNewToken(token);
        Log.i(TAG, "Nouveau token FCM: " + token);
        // Envoyer le token au serveur Flask pour les notifications push
        sendTokenToServer(token);
    }

    @Override
    public void onMessageReceived(@NonNull RemoteMessage message) {
        super.onMessageReceived(message);
        Log.i(TAG, "Message FCM reçu: " + message.getData());

        String action = message.getData().get("action");
        if ("lock".equals(action)) {
            // Verrouiller l'appareil immédiatement
            lockDevice();
        } else if ("unlock".equals(action)) {
            Log.i(TAG, "Ordre de déverrouillage reçu - déverrouillage en cours");
            unlockDevice();
        } else if ("alert".equals(action)) {
            // Afficher une notification d'alerte
            String title = message.getData().get("title");
            String body = message.getData().get("body");
            showAlertNotification(title != null ? title : "AntiVol Alerte",
                    body != null ? body : "Action requise");
        }

        // Notification standard
        if (message.getNotification() != null) {
            showAlertNotification(
                message.getNotification().getTitle(),
                message.getNotification().getBody()
            );
        }
    }

    private void lockDevice() {
        DevicePolicyManager dpm = (DevicePolicyManager)
                getSystemService(Context.DEVICE_POLICY_SERVICE);
        ComponentName admin = new ComponentName(this, AdminReceiver.class);

        if (dpm != null && dpm.isAdminActive(admin)) {
            dpm.lockNow();
            Log.i(TAG, "Appareil verrouillé via FCM");
        }

        // Afficher l'écran de verrouillage
        Intent lockIntent = new Intent(this, LockActivity.class);
        lockIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                | Intent.FLAG_ACTIVITY_CLEAR_TOP
                | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(lockIntent);
    }

    private void unlockDevice() {
        Intent unlockIntent = new Intent("com.antivol.mobile.ACTION_UNLOCK");
        sendBroadcast(unlockIntent);
        Log.i(TAG, "Broadcast ACTION_UNLOCK envoyé");

        Intent serviceIntent = new Intent(this, MonitorService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }
    }

    private void showAlertNotification(String title, String body) {
        Intent intent = new Intent(this, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setContentTitle(title)
                .setContentText(body)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setCategory(NotificationCompat.CATEGORY_ALARM);

        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager != null) {
            manager.notify((int) System.currentTimeMillis(), builder.build());
        }
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID,
                "Alertes AntiVol",
                NotificationManager.IMPORTANCE_HIGH
            );
            channel.setDescription("Notifications d'alerte de vol et verrouillage");
            channel.enableVibration(true);
            channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);

            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private void sendTokenToServer(String token) {
        new Thread(() -> {
            try {
                String apiUrl = AppConfig.getApiUrl(getApplicationContext());
                int userId = AppConfig.getUserId(getApplicationContext());
                if (userId == -1 || apiUrl.isEmpty()) return;

                okhttp3.MediaType JSON = okhttp3.MediaType.parse("application/json; charset=utf-8");
                okhttp3.OkHttpClient client = AppConfig.getHttpClient();

                org.json.JSONObject json = new org.json.JSONObject();
                json.put("user_id", userId);
                json.put("fcm_token", token);

                okhttp3.RequestBody body = okhttp3.RequestBody.create(json.toString(), JSON);
                okhttp3.Request request = new okhttp3.Request.Builder()
                        .url(apiUrl + "/fcm/register-token")
                        .post(body)
                        .build();

                try (okhttp3.Response response = client.newCall(request).execute()) {
                    if (response.isSuccessful()) {
                        Log.i(TAG, "Token FCM envoyé au serveur");
                    }
                }
            } catch (Exception e) {
                Log.e(TAG, "Erreur envoi token FCM: " + e.getMessage());
            }
        }).start();
    }
}
