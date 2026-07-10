package com.antivol.mobile;

import android.app.Activity;
import android.app.KeyguardManager;
import android.app.admin.DevicePolicyManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.media.AudioManager;
import android.media.ToneGenerator;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import java.io.IOException;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;

import org.json.JSONObject;

public class LockActivity extends Activity {

    private EditText etCode;
    private TextView tvError;
    private Handler handler;
    private OkHttpClient client;
    private boolean isPolling = true;
    private int failedAttempts = 0;
    private DevicePolicyManager dpm;
    private ComponentName adminComponent;
    private PowerManager.WakeLock wakeLock;

    private BroadcastReceiver unlockReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if ("com.antivol.mobile.ACTION_UNLOCK".equals(intent.getAction())) {
                runOnUiThread(() -> {
                    isPolling = false;
                    Toast.makeText(LockActivity.this,
                            "Appareil déverrouillé à distance", Toast.LENGTH_SHORT).show();
                    stopLockTask();
                    releaseWakeLock();
                    finish();
                });
            }
        }
    };

    private Runnable checkStatusRunnable = new Runnable() {
        @Override
        public void run() {
            if (isPolling) {
                checkServerStatus();
                handler.postDelayed(this, 3000);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Verrouillage total : plein écran, pas de barre de notification
        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setFlags(
            WindowManager.LayoutParams.FLAG_FULLSCREEN,
            WindowManager.LayoutParams.FLAG_FULLSCREEN
        );

        setContentView(R.layout.activity_lock);

        dpm = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        adminComponent = new ComponentName(this, AdminReceiver.class);

        // Acquire wake lock to keep screen on
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (pm != null) {
            wakeLock = pm.newWakeLock(
                PowerManager.FULL_WAKE_LOCK |
                PowerManager.ACQUIRE_CAUSES_WAKEUP |
                PowerManager.ON_AFTER_RELEASE,
                "AntiVol:LockWakeLock"
            );
            wakeLock.acquire(10 * 60 * 1000L);
        }

        // Make sure screen is on and device is unlocked for this activity
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true);
            setTurnScreenOn(true);
            KeyguardManager km = (KeyguardManager) getSystemService(Context.KEYGUARD_SERVICE);
            if (km != null) {
                km.requestDismissKeyguard(this, null);
            }
        } else {
            getWindow().addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED |
                WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD |
                WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON |
                WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
            );
        }

        // Prevent back and recent apps
        setFinishOnTouchOutside(false);
        // Mode kiosque : bloque Home et Récents
        try { startLockTask(); } catch (Exception ignored) {}

        // Force max volume alarm sound
        AudioManager audio = (AudioManager) getSystemService(Context.AUDIO_SERVICE);
        if (audio != null) {
            int maxVolume = audio.getStreamMaxVolume(AudioManager.STREAM_ALARM);
            audio.setStreamVolume(AudioManager.STREAM_ALARM, maxVolume, 0);
            try {
                ToneGenerator tg = new ToneGenerator(AudioManager.STREAM_ALARM, 100);
                tg.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 2000);
                handler.postDelayed(tg::release, 2500);
            } catch (Exception ignored) {}
        }

        etCode = findViewById(R.id.etCode);
        tvError = findViewById(R.id.tvError);
        handler = new Handler(Looper.getMainLooper());
        client = AppConfig.getHttpClient();

        Button btnUnlock = findViewById(R.id.btnUnlock);
        btnUnlock.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String code = etCode.getText().toString().trim();
                if (code.length() >= 4) {
                    verifyCodeWithServer(code);
                } else {
                    tvError.setText("Entrez le code à 4 chiffres");
                    etCode.setText("");
                }
            }
        });

        // Start polling
        handler.postDelayed(checkStatusRunnable, 3000);

        // Écouter le broadcast de déverrouillage distant
        IntentFilter filter = new IntentFilter("com.antivol.mobile.ACTION_UNLOCK");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            registerReceiver(unlockReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(unlockReceiver, filter);
        }
    }

    private void checkServerStatus() {
        new Thread(() -> {
            try {
                Context context = getApplicationContext();
                int appareilId = AppConfig.getAppareilId(context);
                String apiUrl = AppConfig.getApiUrl(context);

                Request request = new Request.Builder()
                        .url(apiUrl + "/appareils/" + appareilId + "/statut")
                        .get()
                        .build();
                try (Response response = client.newCall(request).execute()) {
                    if (!response.isSuccessful()) return;
                    ResponseBody body = response.body();
                    if (body != null) {
                        String json = body.string();
                        JSONObject obj = new JSONObject(json);
                        boolean verrouille = obj.getBoolean("verrouille");
                        if (!verrouille) {
                            runOnUiThread(() -> {
                                isPolling = false;
                                Toast.makeText(LockActivity.this,
                                        "Appareil déverrouillé", Toast.LENGTH_SHORT).show();
                                stopLockTask();
                                releaseWakeLock();
                                finish();
                            });
                        }
                    }
                }
            } catch (Exception ignored) {}
        }).start();
    }

    private void verifyCodeWithServer(String code) {
        new Thread(() -> {
            try {
                Context context = getApplicationContext();
                int appareilId = AppConfig.getAppareilId(context);
                String apiUrl = AppConfig.getApiUrl(context);

                MediaType JSON = MediaType.parse("application/json; charset=utf-8");
                JSONObject json = new JSONObject();
                json.put("code", code);

                RequestBody body = RequestBody.create(json.toString(), JSON);
                Request request = new Request.Builder()
                        .url(apiUrl + "/appareils/" + appareilId + "/verifier-code")
                        .post(body)
                        .build();

                try (Response response = client.newCall(request).execute()) {
                    if (response.isSuccessful()) {
                        runOnUiThread(() -> {
                            isPolling = false;
                            failedAttempts = 0;
                            stopLockTask();
                            releaseWakeLock();
                            finish();
                            Toast.makeText(LockActivity.this,
                                    "Déverrouillé", Toast.LENGTH_SHORT).show();
                        });
                    } else {
                        failedAttempts++;
                        runOnUiThread(() -> {
                            int remaining = 5 - failedAttempts;
                            if (remaining > 0) {
                                tvError.setText("Code incorrect. " + remaining + " tentative(s) restante(s).");
                            } else {
                                tvError.setText("Trop de tentatives.");
                                if (dpm != null && dpm.isAdminActive(adminComponent)) {
                                    dpm.lockNow();
                                }
                            }
                            etCode.setText("");
                        });
                    }
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    tvError.setText("Erreur réseau. Réessayez.");
                });
            }
        }).start();
    }

    @Override
    public void onBackPressed() {
        // Bloque le retour - l'utilisateur ne peut pas quitter l'écran de verrouillage
        Toast.makeText(this, "Appareil verrouillé. Entrez le code.", Toast.LENGTH_SHORT).show();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        isPolling = false;
        try { stopLockTask(); } catch (Exception ignored) {}
        releaseWakeLock();
        try {
            unregisterReceiver(unlockReceiver);
        } catch (Exception ignored) {}
    }

    private void releaseWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) {
            try {
                wakeLock.release();
            } catch (Exception ignored) {}
        }
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (!hasFocus && isPolling) {
            // Re-lock device if user tries to switch apps
            if (dpm != null && dpm.isAdminActive(adminComponent)) {
                dpm.lockNow();
            }
            // Refocus this activity
            final Intent intent = new Intent(this, LockActivity.class);
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK |
                Intent.FLAG_ACTIVITY_CLEAR_TOP |
                Intent.FLAG_ACTIVITY_SINGLE_TOP);
            startActivity(intent);
        }
    }
}
