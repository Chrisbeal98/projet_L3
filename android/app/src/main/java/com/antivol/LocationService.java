package com.antivol;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Build;
import android.os.Bundle;
import android.os.IBinder;
import android.telephony.SmsManager;
import android.util.Log;

import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class LocationService extends Service implements LocationListener {
    private static final String TAG = "LocationService";
    private static final String PREF_NAME = "antivol_prefs";
    private static final String KEY_DEVICE_UUID = "device_uuid";
    private static final String KEY_DEVICE_ID = "device_id";
    private static final String CHANNEL_ID = "antivol_gps_channel";
    private static final int NOTIF_ID = 1002;
    private static final int MIN_TIME = 15000;
    private static final int MIN_DISTANCE = 30;

    private LocationManager locationManager;
    private String serverUrl;
    private boolean isTracking = false;
    private boolean reportedLocked = false;

    @Override
    public void onCreate() {
        super.onCreate();
        serverUrl = getString(R.string.server_url);
        locationManager = (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        createChannel();
        startForeground(NOTIF_ID, buildNotification("AntiVol", "Localisation en cours..."));
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startTracking();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        stopTracking();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "AntiVol - Localisation",
                NotificationManager.IMPORTANCE_LOW
            );
            ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).createNotificationChannel(channel);
        }
    }

    private Notification buildNotification(String title, String text) {
        Notification.Builder b = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? new Notification.Builder(this, CHANNEL_ID)
            : new Notification.Builder(this);
        return b.setContentTitle(title).setContentText(text)
                .setSmallIcon(android.R.drawable.ic_menu_mylocation)
                .setOngoing(true).build();
    }

    private void startTracking() {
        if (isTracking) return;
        try {
            if (checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION)
                    == android.content.pm.PackageManager.PERMISSION_GRANTED) {
                locationManager.requestLocationUpdates(
                    LocationManager.GPS_PROVIDER, MIN_TIME, MIN_DISTANCE, this);
                locationManager.requestLocationUpdates(
                    LocationManager.NETWORK_PROVIDER, MIN_TIME, MIN_DISTANCE, this);
                isTracking = true;
                Log.d(TAG, "Tracking GPS démarré");
            }
        } catch (Exception e) {
            Log.e(TAG, "Erreur démarrage GPS", e);
        }
    }

    private void stopTracking() {
        if (locationManager != null && isTracking) {
            locationManager.removeUpdates(this);
            isTracking = false;
        }
    }

    @Override
    public void onLocationChanged(Location location) {
        if (location == null) return;
        sendLocation(location);
        checkAndSendAlert(location);
    }

    private void sendLocation(Location location) {
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        int deviceId = prefs.getInt(KEY_DEVICE_ID, -1);
        if (deviceId == -1) return;

        new Thread(() -> {
            try {
                JSONObject data = new JSONObject();
                data.put("appareil_id", deviceId);
                data.put("latitude", location.getLatitude());
                data.put("longitude", location.getLongitude());
                data.put("precision_m", location.getAccuracy());
                data.put("source", location.getProvider());

                URL url = new URL(serverUrl + "/api/localisation/update");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setConnectTimeout(10000);
                conn.setDoOutput(true);

                OutputStream os = conn.getOutputStream();
                os.write(data.toString().getBytes());
                os.close();
                conn.getResponseCode();
                conn.disconnect();
            } catch (Exception e) {
                Log.e(TAG, "Erreur envoi position", e);
            }
        }).start();
    }

    private void checkAndSendAlert(Location location) {
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        boolean isLocked = prefs.getBoolean("was_locked", false);
        if (!isLocked) {
            reportedLocked = false;
            return;
        }
        if (reportedLocked) return;
        reportedLocked = true;

        String uuid = prefs.getString(KEY_DEVICE_UUID, "");

        updateNotif("VOLE", "Ce téléphone a été volé! Localisation envoyée.");
        sendSmsAlert(location, uuid);
        notifyServerStolen(location, uuid);
    }

    private void updateNotif(String title, String text) {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm != null) nm.notify(NOTIF_ID, buildNotification(title, text));
    }

    private void sendSmsAlert(Location location, String uuid) {
        try {
            SmsManager sms = SmsManager.getDefault();
            String msg = "ALERTE AntiVol: Ce telephone a ete vole! Position: "
                + location.getLatitude() + "," + location.getLongitude()
                + " http://maps.google.com/?q=" + location.getLatitude() + ","
                + location.getLongitude();
            sms.sendTextMessage("**CODE_URGENCE**", null, msg, null, null);
        } catch (Exception e) {
            Log.e(TAG, "Erreur envoi SMS", e);
        }
    }

    private void notifyServerStolen(Location location, String uuid) {
        new Thread(() -> {
            try {
                JSONObject data = new JSONObject();
                data.put("device_uuid", uuid);
                data.put("latitude", location.getLatitude());
                data.put("longitude", location.getLongitude());

                URL url = new URL(serverUrl + "/api/mobile/stolen-alert");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setConnectTimeout(10000);
                conn.setDoOutput(true);

                OutputStream os = conn.getOutputStream();
                os.write(data.toString().getBytes());
                os.close();
                conn.getResponseCode();
                conn.disconnect();
            } catch (Exception e) {
                Log.e(TAG, "Erreur alerte vol", e);
            }
        }).start();
    }

    @Override public void onStatusChanged(String provider, int status, Bundle extras) {}
    @Override public void onProviderEnabled(String provider) {}
    @Override public void onProviderDisabled(String provider) { startTracking(); }
}

