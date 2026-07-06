package com.antivol.mobile;

import android.app.Activity;
import android.app.KeyguardManager;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.Manifest;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.annotation.NonNull;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;

import org.json.JSONObject;
import org.json.JSONArray;

import java.util.UUID;

public class MainActivity extends AppCompatActivity {

    private TextView tvStatus, tvImei, tvLocked, tvLog, tvDeviceId, tvUserEmail;
    private TextView tvStatsDevices, tvStatsAlertes, tvStatsVol, tvStatsLocked;
    private Button btnActivate, btnStart, btnStop, btnRegister, btnSettings, btnLogout;
    private LinearLayout navAlertes, navProfile, navDevices, navLocation, navZones;
    private Handler handler;
    private OkHttpClient client;
    private boolean isMonitoring = false;

    private Runnable checkStatusRunnable = new Runnable() {
        @Override
        public void run() {
            if (isMonitoring) {
                checkDeviceStatus();
                handler.postDelayed(this, 3000);
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (AppConfig.getUserId(this) == -1) {
            startActivity(new Intent(this, LoginActivity.class));
            finish();
            return;
        }

        setContentView(R.layout.activity_main);
        client = AppConfig.getHttpClient();

        tvStatus = findViewById(R.id.tvStatus);
        tvImei = findViewById(R.id.tvImei);
        tvLocked = findViewById(R.id.tvLocked);
        tvLog = findViewById(R.id.tvLog);
        tvDeviceId = findViewById(R.id.tvDeviceId);
        tvUserEmail = findViewById(R.id.tvUserEmail);
        tvStatsDevices = findViewById(R.id.tvStatsDevices);
        tvStatsAlertes = findViewById(R.id.tvStatsAlertes);
        tvStatsVol = findViewById(R.id.tvStatsVol);
        tvStatsLocked = findViewById(R.id.tvStatsLocked);
        btnActivate = findViewById(R.id.btnActivate);
        btnStart = findViewById(R.id.btnStart);
        btnStop = findViewById(R.id.btnStop);
        btnRegister = findViewById(R.id.btnRegister);
        btnSettings = findViewById(R.id.btnSettings);
        btnLogout = findViewById(R.id.btnLogout);
        navAlertes = findViewById(R.id.navAlerts);
        navProfile = findViewById(R.id.navProfile);
        navDevices = findViewById(R.id.navDevices);
        navLocation = findViewById(R.id.navLocation);
        navZones = findViewById(R.id.navZones);

        handler = new Handler(Looper.getMainLooper());
        tvUserEmail.setText(AppConfig.getUserEmail(this));
        addLog("Utilisateur: " + AppConfig.getUserEmail(this));

        int currentId = AppConfig.getAppareilId(this);
        if (currentId != -1) {
            tvDeviceId.setText("ID: " + currentId);
            String savedImei = AppConfig.getAppareilImei(this);
            if (!savedImei.isEmpty()) {
                tvImei.setText(savedImei);
            }
            btnRegister.setVisibility(View.GONE);
            btnStart.setVisibility(View.VISIBLE);
        }

        navAlertes.setOnClickListener(v -> openAlertes());
        navProfile.setOnClickListener(v -> openProfile());
        navDevices.setOnClickListener(v -> openSettings(v));
        navLocation.setOnClickListener(v -> openLocation());
        navZones.setOnClickListener(v -> openZones());

        checkLocationPermission();
        enforceDeviceSecurity();
        updateAdminButton();
        loadDashboardStats();
        addLog("Application AntiVol lancée");
    }

    private void loadDashboardStats() {
        new Thread(() -> {
            try {
                String apiUrl = AppConfig.getApiUrl(getApplicationContext());
                int userId = AppConfig.getUserId(getApplicationContext());
                if (userId == -1) return;

                MediaType JSON = MediaType.parse("application/json; charset=utf-8");
                JSONObject json = new JSONObject();
                json.put("user_id", userId);

                RequestBody body = RequestBody.create(json.toString(), JSON);
                Request request = new Request.Builder()
                        .url(apiUrl + "/dashboard/stats")
                        .post(body)
                        .build();

                try (Response response = client.newCall(request).execute()) {
                    if (response.isSuccessful()) {
                        ResponseBody rb = response.body();
                        if (rb != null) {
                            JSONObject data = new JSONObject(rb.string());
                            runOnUiThread(() -> {
                                tvStatsDevices.setText(String.valueOf(data.optInt("total_appareils", 0)));
                                tvStatsAlertes.setText(String.valueOf(data.optInt("total_alertes", 0)));
                                tvStatsVol.setText(String.valueOf(data.optInt("total_voles", 0)));
                                tvStatsLocked.setText(String.valueOf(data.optInt("total_verrouilles", 0)));
                            });
                        }
                    }
                }
            } catch (Exception ignored) {}
        }).start();
    }

    private void openAlertes() {
        startActivity(new Intent(this, AlertesActivity.class));
    }

    private void openProfile() {
        startActivity(new Intent(this, ProfilActivity.class));
    }

    private void openLocation() {
        int appareilId = AppConfig.getAppareilId(this);
        if (appareilId == -1) {
            Toast.makeText(this, "Enregistrez d'abord un appareil", Toast.LENGTH_SHORT).show();
            return;
        }
        String apiUrl = AppConfig.getApiUrl(this);
        String url = apiUrl.replace("/api", "") + "/dashboard/carte?appareil_id=" + appareilId;
        Intent browserIntent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
        startActivity(browserIntent);
    }

    private void openZones() {
        startActivity(new Intent(this, ZonesActivity.class));
    }

    @Override
    protected void onResume() {
        super.onResume();
        loadDashboardStats();
        int currentId = AppConfig.getAppareilId(this);
        if (currentId != -1) {
            tvDeviceId.setText("ID: " + currentId);
            String savedImei = AppConfig.getAppareilImei(this);
            if (!savedImei.isEmpty()) {
                tvImei.setText(savedImei);
            }
            btnRegister.setVisibility(View.GONE);
        }
        checkDeviceStatus();
    }

    public void activateAdmin(View view) {
        Toast.makeText(this, "Protection Admin disponible dans une version ultérieure", Toast.LENGTH_LONG).show();
    }

    public void registerDevice(View view) {
        registerDeviceOnServer();
    }

    private void registerDeviceOnServer() {
        new Thread(() -> {
            try {
                String apiUrl = AppConfig.getApiUrl(getApplicationContext());
                String imei = UUID.randomUUID().toString();
                String modele = android.os.Build.MODEL;
                String marque = android.os.Build.BRAND;
                int userId = AppConfig.getUserId(getApplicationContext());

                MediaType JSON = MediaType.parse("application/json; charset=utf-8");
                JSONObject json = new JSONObject();
                json.put("imei", imei.substring(0, Math.min(imei.length(), 20)));
                json.put("modele", modele);
                json.put("marque", marque);
                json.put("user_id", userId);

                RequestBody body = RequestBody.create(json.toString(), JSON);
                Request request = new Request.Builder()
                        .url(apiUrl + "/appareils/register")
                        .post(body)
                        .build();

                Response response = client.newCall(request).execute();
                String responseBody = response.body() != null ? response.body().string() : "";

                if (!response.isSuccessful()) {
                    runOnUiThread(() -> {
                        addLog("Erreur enregistrement: HTTP " + response.code());
                        Toast.makeText(MainActivity.this, "Erreur serveur", Toast.LENGTH_LONG).show();
                    });
                    return;
                }

                JSONObject jsonResponse = new JSONObject(responseBody);
                final int deviceId = jsonResponse.getInt("id");
                final String serverImei = jsonResponse.optString("imei", "");
                runOnUiThread(() -> {
                    AppConfig.setAppareilId(getApplicationContext(), deviceId);
                    if (!serverImei.isEmpty()) {
                        AppConfig.setAppareilImei(getApplicationContext(), serverImei);
                    }
                    tvDeviceId.setText("ID: " + deviceId);
                    tvImei.setText(serverImei.isEmpty() ? "Enregistré" : serverImei);
                    btnRegister.setVisibility(View.GONE);
                    btnStart.setVisibility(View.VISIBLE);
                    addLog("Appareil enregistré ! ID: " + deviceId);
                    Toast.makeText(MainActivity.this, "Enregistrement réussi !", Toast.LENGTH_LONG).show();
                    loadDashboardStats();
                });
            } catch (Exception e) {
                runOnUiThread(() -> addLog("Erreur enregistrement: " + e.getMessage()));
            }
        }).start();
    }

    public void startMonitoring(View view) {
        int appareilId = AppConfig.getAppareilId(this);
        if (appareilId == -1) {
            Toast.makeText(this, "Configurez d'abord l'ID appareil", Toast.LENGTH_LONG).show();
            return;
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this,
                    new String[]{Manifest.permission.ACCESS_FINE_LOCATION}, 100);
            addLog("Demande de permission GPS...");
            return;
        }

        startMonitoringAfterPermission(appareilId);
    }

    private void startMonitoringAfterPermission(int appareilId) {
        isMonitoring = true;
        btnStart.setVisibility(View.GONE);
        btnStop.setVisibility(View.VISIBLE);
        addLog("Surveillance activée - ID: " + appareilId);

        startService(new Intent(this, MonitorService.class));

        checkDeviceStatus();
        handler.post(checkStatusRunnable);

        requestBatteryOptimizationWhitelist();
    }

    private void requestBatteryOptimizationWhitelist() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                addLog("Demande d'optimisation batterie...");
                try {
                    Intent intent = new Intent(
                        Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:" + getPackageName())
                    );
                    startActivity(intent);
                } catch (Exception e) {
                    addLog("Impossible d'ouvrir les paramètres batterie");
                }
            } else {
                addLog("Optimisation batterie désactivée ✓");
            }
        }
    }

    public void stopMonitoring(View view) {
        isMonitoring = false;
        handler.removeCallbacks(checkStatusRunnable);
        stopService(new Intent(this, MonitorService.class));
        btnStart.setVisibility(View.VISIBLE);
        btnStop.setVisibility(View.GONE);
        addLog("Surveillance arrêtée");
    }

    public void openSettings(View view) {
        startActivity(new Intent(this, SettingsActivity.class));
    }

    public void logout(View view) {
        AppConfig.logout(this);
        stopService(new Intent(this, MonitorService.class));
        startActivity(new Intent(this, LoginActivity.class));
        finishAffinity();
    }

    private void checkDeviceStatus() {
        new Thread(() -> {
            try {
                int appareilId = AppConfig.getAppareilId(getApplicationContext());
                if (appareilId == -1) return;

                String apiUrl = AppConfig.getApiUrl(getApplicationContext());
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
                        String statut = obj.getString("statut");
                        boolean verrouille = obj.getBoolean("verrouille");

                        runOnUiThread(() -> {
                            tvStatus.setText(statut.toUpperCase());
                            tvLocked.setText(verrouille ? "OUI" : "NON");
                            if (verrouille) {
                                tvStatus.setTextColor(getResources().getColor(android.R.color.holo_red_dark));
                                tvLocked.setTextColor(getResources().getColor(android.R.color.holo_red_dark));
                            } else {
                                tvStatus.setTextColor(getResources().getColor(android.R.color.holo_green_dark));
                                tvLocked.setTextColor(getResources().getColor(android.R.color.holo_green_dark));
                            }
                        });
                    }
                }
            } catch (Exception e) {
                runOnUiThread(() -> addLog("Erreur: " + e.getMessage()));
            }
        }).start();
    }

    private void updateAdminButton() {
        btnActivate.setVisibility(View.GONE);
        int appareilId = AppConfig.getAppareilId(this);
        if (appareilId != -1) {
            btnStart.setVisibility(View.VISIBLE);
        } else {
            btnRegister.setVisibility(View.VISIBLE);
        }
    }

    private void addLog(String message) {
        String time = java.text.SimpleDateFormat.getTimeInstance().format(new java.util.Date());
        final String entry = "[" + time + "] " + message;

        runOnUiThread(() -> {
            tvLog.append(entry + "\n");
            ScrollView scrollView = findViewById(R.id.scrollView);
            scrollView.fullScroll(View.FOCUS_DOWN);
        });
    }

    private void enforceDeviceSecurity() {
        KeyguardManager km = (KeyguardManager) getSystemService(Context.KEYGUARD_SERVICE);
        if (km != null && !km.isKeyguardSecure()) {
            addLog("INFO: Aucun verrouillage d'écran - Protection Admin non activée");
        }
    }

    private void checkLocationPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this,
                    new String[]{Manifest.permission.ACCESS_FINE_LOCATION}, 100);
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == 100) {
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                addLog("Permission GPS accordée");
                int appareilId = AppConfig.getAppareilId(this);
                if (appareilId != -1) {
                    startMonitoringAfterPermission(appareilId);
                }
            } else {
                addLog("Permission GPS refusée - GPS désactivé");
                Toast.makeText(this, "La localisation est nécessaire pour la surveillance", Toast.LENGTH_LONG).show();
            }
        }
    }
}
