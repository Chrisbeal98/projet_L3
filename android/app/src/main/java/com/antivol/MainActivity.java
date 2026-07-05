package com.antivol;

import android.annotation.SuppressLint;
import android.app.admin.DevicePolicyManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.UUID;

public class MainActivity extends AppCompatActivity {

    private static final int LOCATION_PERMISSION_CODE = 100;
    private static final int NOTIFICATION_PERMISSION_CODE = 101;
    private static final int DEVICE_ADMIN_CODE = 102;
    private static final String PREF_NAME = "antivol_prefs";
    private static final String KEY_DEVICE_UUID = "device_uuid";
    private static final String KEY_DEVICE_ID = "device_id";
    private static final String KEY_LOCK_CODE = "lock_code";

    private WebView webView;
    private ProgressBar progressBar;
    private SwipeRefreshLayout swipeRefresh;
    private View errorView;
    private TextView errorText;
    private Button retryButton;
    private View lockOverlay;
    private EditText unlockCodeInput;
    private Button unlockButton;
    private TextView unlockError;

    private DevicePolicyManager devicePolicyManager;
    private ComponentName deviceAdminComponent;
    private String serverUrl;
    private String deviceUuid;
    private String currentLockCode = "";
    private boolean isLocked = false;

    private final BroadcastReceiver lockReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if ("com.antivol.LOCK_DEVICE".equals(action)) {
                String code = intent.getStringExtra("code_verrouillage");
                showLockScreen(code);
            } else if ("com.antivol.UNLOCK_DEVICE".equals(action)) {
                hideLockScreen();
            }
        }
    };

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        serverUrl = getString(R.string.server_url);
        devicePolicyManager = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        deviceAdminComponent = new ComponentName(this, AntiVolDeviceAdmin.class);

        webView = findViewById(R.id.webView);
        progressBar = findViewById(R.id.progressBar);
        swipeRefresh = findViewById(R.id.swipeRefresh);
        errorView = findViewById(R.id.errorView);
        errorText = findViewById(R.id.errorText);
        retryButton = findViewById(R.id.retryButton);
        lockOverlay = findViewById(R.id.lockOverlay);
        unlockCodeInput = findViewById(R.id.unlockCodeInput);
        unlockButton = findViewById(R.id.unlockButton);
        unlockError = findViewById(R.id.unlockError);

        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setLoadWithOverviewMode(true);
        webView.getSettings().setUseWideViewPort(true);
        webView.getSettings().setCacheMode(android.webkit.WebSettings.LOAD_DEFAULT);
        webView.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        webView.setWebViewClient(new AntiVolWebClient());
        webView.setWebChromeClient(new AntiVolChromeClient());

        swipeRefresh.setOnRefreshListener(this::reloadPage);
        retryButton.setOnClickListener(v -> reloadPage());
        unlockButton.setOnClickListener(v -> attemptUnlock());

        registerReceiver(lockReceiver, new IntentFilter("com.antivol.LOCK_DEVICE"));
        registerReceiver(lockReceiver, new IntentFilter("com.antivol.UNLOCK_DEVICE"));

        requestPermissions();
        initDevice();
        loadUrl();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        try {
            unregisterReceiver(lockReceiver);
        } catch (Exception ignored) {}
    }

    private void initDevice() {
        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        deviceUuid = prefs.getString(KEY_DEVICE_UUID, null);

        if (deviceUuid == null) {
            deviceUuid = UUID.randomUUID().toString();
            prefs.edit().putString(KEY_DEVICE_UUID, deviceUuid).apply();
            registerDevice(deviceUuid);
        } else {
            restoreLockState(prefs);
        }

        startService(new Intent(this, LockService.class));
    }

    private void restoreLockState(SharedPreferences prefs) {
        boolean wasLocked = prefs.getBoolean("was_locked", false);
        if (wasLocked) {
            String savedCode = prefs.getString(KEY_LOCK_CODE, "");
            showLockScreen(savedCode);
        }
    }

    private void registerDevice(String uuid) {
        new Thread(() -> {
            try {
                JSONObject data = new JSONObject();
                data.put("device_uuid", uuid);
                data.put("modele", Build.MODEL);
                data.put("marque", Build.MANUFACTURER);
                data.put("version_os", Build.VERSION.RELEASE);

                URL url = new URL(serverUrl + "/api/mobile/register");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(15000);
                conn.setDoOutput(true);

                OutputStream os = conn.getOutputStream();
                os.write(data.toString().getBytes());
                os.close();

                int code = conn.getResponseCode();
                if (code == 200 || code == 201) {
                    BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                    StringBuilder response = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) response.append(line);
                    reader.close();

                    JSONObject json = new JSONObject(response.toString());
                    int deviceId = json.getInt("id");
                    String lockCode = json.optString("code_verrouillage", "");

                    SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
                    prefs.edit()
                            .putInt(KEY_DEVICE_ID, deviceId)
                            .putString("registered", "true")
                            .apply();

                    if (!lockCode.isEmpty()) {
                        runOnUiThread(() -> Toast.makeText(this,
                                "Code verrouillage: " + lockCode, Toast.LENGTH_LONG).show());
                    }
                }
                conn.disconnect();
            } catch (Exception e) {
                e.printStackTrace();
            }
        }).start();
    }

    private void showLockScreen(String code) {
        currentLockCode = code != null ? code : "";
        isLocked = true;

        getSharedPreferences(PREF_NAME, MODE_PRIVATE)
                .edit()
                .putBoolean("was_locked", true)
                .putString(KEY_LOCK_CODE, currentLockCode)
                .apply();

        runOnUiThread(() -> {
            lockOverlay.setVisibility(View.VISIBLE);
            webView.setVisibility(View.GONE);
            unlockCodeInput.setText("");
            unlockError.setVisibility(View.GONE);
        });
    }

    private void hideLockScreen() {
        isLocked = false;
        getSharedPreferences(PREF_NAME, MODE_PRIVATE)
                .edit()
                .putBoolean("was_locked", false)
                .remove(KEY_LOCK_CODE)
                .apply();

        runOnUiThread(() -> {
            lockOverlay.setVisibility(View.GONE);
            webView.setVisibility(View.VISIBLE);
        });
    }

    private void attemptUnlock() {
        String enteredCode = unlockCodeInput.getText().toString().trim();
        if (enteredCode.isEmpty()) {
            unlockError.setText("Entrez le code");
            unlockError.setVisibility(View.VISIBLE);
            return;
        }

        unlockButton.setEnabled(false);

        new Thread(() -> {
            try {
                JSONObject data = new JSONObject();
                data.put("device_uuid", deviceUuid);
                data.put("code", enteredCode);

                URL url = new URL(serverUrl + "/api/mobile/unlock");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setConnectTimeout(15000);
                conn.setReadTimeout(15000);
                conn.setDoOutput(true);

                OutputStream os = conn.getOutputStream();
                os.write(data.toString().getBytes());
                os.close();

                int code = conn.getResponseCode();
                conn.disconnect();

                if (code == 200) {
                    runOnUiThread(() -> {
                        hideLockScreen();
                        Toast.makeText(this, "Appareil déverrouillé", Toast.LENGTH_SHORT).show();
                    });
                } else {
                    runOnUiThread(() -> {
                        unlockError.setText("Code incorrect");
                        unlockError.setVisibility(View.VISIBLE);
                        unlockCodeInput.setText("");
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> {
                    unlockError.setText("Erreur réseau");
                    unlockError.setVisibility(View.VISIBLE);
                });
            } finally {
                runOnUiThread(() -> unlockButton.setEnabled(true));
            }
        }).start();
    }

    private void requestPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this,
                        new String[]{android.Manifest.permission.POST_NOTIFICATIONS},
                        NOTIFICATION_PERMISSION_CODE);
            }
        }
        if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this,
                    new String[]{android.Manifest.permission.ACCESS_FINE_LOCATION},
                    LOCATION_PERMISSION_CODE);
        }
    }

    private void loadUrl() {
        errorView.setVisibility(View.GONE);
        if (!isLocked) {
            webView.setVisibility(View.VISIBLE);
            webView.loadUrl(serverUrl);
        }
    }

    private void reloadPage() {
        swipeRefresh.setRefreshing(true);
        loadUrl();
    }

    @Override
    public void onBackPressed() {
        if (isLocked) return;
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    private class AntiVolWebClient extends WebViewClient {
        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            super.onPageStarted(view, url, favicon);
            progressBar.setVisibility(View.VISIBLE);
            errorView.setVisibility(View.GONE);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            super.onPageFinished(view, url);
            progressBar.setVisibility(View.GONE);
            swipeRefresh.setRefreshing(false);
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            super.onReceivedError(view, request, error);
            if (request.isForMainFrame()) {
                progressBar.setVisibility(View.GONE);
                swipeRefresh.setRefreshing(false);
                if (!isLocked) {
                    webView.setVisibility(View.GONE);
                    errorView.setVisibility(View.VISIBLE);
                    errorText.setText("Impossible de se connecter au serveur.\nVérifiez votre connexion Internet.");
                }
            }
        }
    }

    private class AntiVolChromeClient extends WebChromeClient {
        @Override
        public void onProgressChanged(WebView view, int newProgress) {
            super.onProgressChanged(view, newProgress);
            progressBar.setProgress(newProgress);
        }
    }
}
