package com.antivol.mobile;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.app.admin.DevicePolicyManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.location.Location;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import androidx.core.content.ContextCompat;
import android.telephony.TelephonyManager;
import android.util.Log;

import com.google.android.gms.location.FusedLocationProviderClient;
import com.google.android.gms.location.LocationCallback;
import com.google.android.gms.location.LocationRequest;
import com.google.android.gms.location.LocationResult;
import com.google.android.gms.location.LocationServices;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;
import org.json.JSONObject;

public class MonitorService extends Service {

    private static final String TAG = "MonitorService";
    private static final int NOTIFICATION_ID = 1;
    private static final String PREFS = "antivol_protection";
    private static final String KEY_WAS_STOLEN = "was_stolen";

    private static final int GPS_NORMAL_INTERVAL = 10000;
    private static final int GPS_NORMAL_FASTEST = 5000;
    private static final int GPS_STOLEN_INTERVAL = 3000;
    private static final int GPS_STOLEN_FASTEST = 1000;

    private DevicePolicyManager dpm;
    private ComponentName adminComponent;
    private Handler handler;
    private OkHttpClient client;
    private boolean isLocked = false;
    private boolean isStolenMode = false;
    private PowerManager.WakeLock wakeLock;

    private FusedLocationProviderClient fusedLocationClient;
    private LocationCallback locationCallback;
    private boolean isGpsStarted = false;
    private int currentGpsInterval = GPS_NORMAL_INTERVAL;

    private BroadcastReceiver unlockReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if ("com.antivol.mobile.ACTION_UNLOCK".equals(intent.getAction())) {
                Log.i(TAG, "Deverrouillage recu");
                isLocked = false;
                getSharedPreferences(PREFS, MODE_PRIVATE)
                    .edit().putBoolean(KEY_WAS_STOLEN, false).apply();
            }
        }
    };

    private BroadcastReceiver shutdownReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if (Intent.ACTION_SHUTDOWN.equals(intent.getAction())) {
                Log.w(TAG, "Extinction detection ! Sauvegarde statut vole");
                SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
                prefs.edit().putBoolean(KEY_WAS_STOLEN, isLocked).apply();

                Thread lastGps = new Thread(() -> {
                    try {
                        int appareilId = AppConfig.getAppareilId(context);
                        if (appareilId == -1) return;
                        String apiUrl = AppConfig.getApiUrl(context);
                        JSONObject json = new JSONObject();
                        json.put("appareil_id", appareilId);
                        json.put("alerte", "EXTINCTION_VOLEUR");
                        RequestBody body = RequestBody.create(json.toString(),
                            MediaType.parse("application/json; charset=utf-8"));
                        Request request = new Request.Builder()
                            .url(apiUrl + "/mobile/stolen-alert")
                            .post(body)
                            .build();
                        client.newCall(request).execute();
                    } catch (Exception ignored) {}
                });
                lastGps.start();
                try { lastGps.join(2000); } catch (InterruptedException ignored) {}
            }
        }
    };

        private Runnable checkRunnable = new Runnable() {
        @Override
        public void run() {
            checkStatus();
            reacquireWakeLock();
            handler.postDelayed(this, 5000);
        }
    };

    private void reacquireWakeLock() {
        if (wakeLock != null && !wakeLock.isHeld()) {
            try {
                PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
                if (pm != null) {
                    wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AntiVol:ProtectionWakeLock");
                    wakeLock.acquire(10 * 60 * 1000L);
                }
            } catch (Exception ignored) {}
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        dpm = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        adminComponent = new ComponentName(this, AdminReceiver.class);
        handler = new Handler(Looper.getMainLooper());
        client = AppConfig.getHttpClient();
        createNotificationChannel();
        acquireWakeLock();

        IntentFilter unlockFilter = new IntentFilter("com.antivol.mobile.ACTION_UNLOCK");
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            registerReceiver(unlockReceiver, unlockFilter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(unlockReceiver, unlockFilter);
        }

        IntentFilter shutdownFilter = new IntentFilter(Intent.ACTION_SHUTDOWN);
        registerReceiver(shutdownReceiver, shutdownFilter);

        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        boolean wasStolen = prefs.getBoolean(KEY_WAS_STOLEN, false);
        if (wasStolen) {
            Log.w(TAG, "Appareil etait en mode vole avant extinction ! Re-verrouillage.");
            isLocked = true;
            lockDevice();
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTIFICATION_ID, buildNotification());
        handler.post(checkRunnable);
        startLocationUpdates();
        return START_STICKY;
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        Log.w(TAG, "App tuee ! Redemarrage force...");
        Intent restartIntent = new Intent(this, MonitorService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(restartIntent);
        } else {
            startService(restartIntent);
        }
        super.onTaskRemoved(rootIntent);
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacks(checkRunnable);
        stopLocationUpdates();
        releaseWakeLock();
        try {
            unregisterReceiver(unlockReceiver);
            unregisterReceiver(shutdownReceiver);
        } catch (Exception ignored) {}
        super.onDestroy();

        Log.w(TAG, "Service detruit ! Relance...");
        Intent restartIntent = new Intent(this, MonitorService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(restartIntent);
        } else {
            startService(restartIntent);
        }
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void acquireWakeLock() {
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        if (pm != null) {
            wakeLock = pm.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "AntiVol:ProtectionWakeLock"
            );
            wakeLock.acquire(10 * 60 * 1000L);
        }
    }

    private void releaseWakeLock() {
        if (wakeLock != null && wakeLock.isHeld()) {
            try { wakeLock.release(); } catch (Exception ignored) {}
        }
    }

    private void checkStatus() {
        new Thread(() -> {
            try {
                Context context = getApplicationContext();
                int appareilId = AppConfig.getAppareilId(context);
                if (appareilId == -1) return;

                String apiUrl = AppConfig.getApiUrl(context);
                Request request = new Request.Builder()
                        .url(apiUrl + "/appareils/" + appareilId + "/statut")
                        .get()
                        .build();

                try (Response response = client.newCall(request).execute()) {
                    if (!response.isSuccessful()) {
                        Log.e(TAG, "HTTP " + response.code());
                        return;
                    }
                    ResponseBody body = response.body();
                    if (body != null) {
                        String json = body.string();
                        JSONObject obj = new JSONObject(json);
                        boolean verrouille = obj.getBoolean("verrouille");
                        String statut = obj.optString("statut", "");

                        if (verrouille && !isLocked) {
                            isLocked = true;
                            getSharedPreferences(PREFS, MODE_PRIVATE)
                                .edit().putBoolean(KEY_WAS_STOLEN, true).apply();
                            lockDevice();
                        } else if (!verrouille) {
                            isLocked = false;
                            getSharedPreferences(PREFS, MODE_PRIVATE)
                                .edit().putBoolean(KEY_WAS_STOLEN, false).apply();
                        }

                        boolean shouldBeStolen = "vole".equals(statut) || "verrouille".equals(statut);
                        if (shouldBeStolen != isStolenMode) {
                            isStolenMode = shouldBeStolen;
                            if (isGpsStarted) {
                                handler.post(() -> restartLocationUpdates());
                            }
                        }
                    }
                }
            } catch (Exception e) {
                Log.e(TAG, "Erreur checkStatus: " + e.getMessage());
            }
        }).start();
    }

    private void lockDevice() {
        if (dpm != null && dpm.isAdminActive(adminComponent)) {
            dpm.lockNow();
        }

        Intent lockIntent = new Intent(this, LockActivity.class);
        lockIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        lockIntent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);
        lockIntent.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(lockIntent);
    }

    private int getTargetGpsInterval() {
        return isStolenMode ? GPS_STOLEN_INTERVAL : GPS_NORMAL_INTERVAL;
    }

    private int getTargetGpsFastest() {
        return isStolenMode ? GPS_STOLEN_FASTEST : GPS_NORMAL_FASTEST;
    }

    private void restartLocationUpdates() {
        stopLocationUpdates();
        startLocationUpdates();
    }

    private void startLocationUpdates() {
        if (isGpsStarted) return;

        if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION)
                != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            Log.w(TAG, "Permission ACCESS_FINE_LOCATION non accordee. GPS desactive.");
            return;
        }

        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this);
        LocationRequest locationRequest = LocationRequest.create();
        locationRequest.setInterval(getTargetGpsInterval());
        locationRequest.setFastestInterval(getTargetGpsFastest());
        locationRequest.setPriority(LocationRequest.PRIORITY_HIGH_ACCURACY);

        locationCallback = new LocationCallback() {
            @Override
            public void onLocationResult(LocationResult locationResult) {
                if (locationResult == null) return;
                for (Location location : locationResult.getLocations()) {
                    sendLocationToServer(location);
                }
            }
        };

        try {
            fusedLocationClient.requestLocationUpdates(locationRequest, locationCallback, Looper.getMainLooper());
            isGpsStarted = true;
            currentGpsInterval = getTargetGpsInterval();
            String mode = isStolenMode ? "INTENSIF (3s)" : "NORMAL (10s)";
            Log.i(TAG, "GPS demarre - Mode " + mode);
        } catch (SecurityException e) {
            Log.e(TAG, "SecurityException GPS: " + e.getMessage());
        }
    }

    private void stopLocationUpdates() {
        if (fusedLocationClient != null && locationCallback != null) {
            fusedLocationClient.removeLocationUpdates(locationCallback);
            isGpsStarted = false;
            Log.i(TAG, "GPS arrete");
        }
    }

    private void sendLocationToServer(Location location) {
        new Thread(() -> {
            try {
                Context context = getApplicationContext();
                int appareilId = AppConfig.getAppareilId(context);
                String apiUrl = AppConfig.getApiUrl(context);

                MediaType JSON = MediaType.parse("application/json; charset=utf-8");
                JSONObject json = new JSONObject();
                json.put("appareil_id", appareilId);
                json.put("latitude", location.getLatitude());
                json.put("longitude", location.getLongitude());
                json.put("precision_m", location.getAccuracy());
                json.put("source", location.getProvider() != null ? location.getProvider() : "gps");

                RequestBody body = RequestBody.create(json.toString(), JSON);
                Request request = new Request.Builder()
                        .url(apiUrl + "/localisation/update")
                        .post(body)
                        .build();

                try (Response response = client.newCall(request).execute()) {
                    if (response.isSuccessful()) {
                        Log.i(TAG, "GPS envoye: " + location.getLatitude() + ", " + location.getLongitude());
                    }
                }
            } catch (Exception e) {
                Log.e(TAG, "Erreur envoi GPS: " + e.getMessage());
            }
        }).start();
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    "antivol_channel",
                    "AntiVol Monitor",
                    NotificationManager.IMPORTANCE_LOW
            );
            NotificationManager manager = getSystemService(NotificationManager.class);
            if (manager != null) {
                manager.createNotificationChannel(channel);
            }
        }
    }

    private Notification buildNotification() {
        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, "antivol_channel");
        } else {
            builder = new Notification.Builder(this);
        }

        return builder
                .setContentTitle("Antivol Intelligent")
                .setContentText("Protection active - Surveillance en cours")
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setOngoing(true)
                .build();
    }
}
