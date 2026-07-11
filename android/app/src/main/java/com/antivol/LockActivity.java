package com.antivol;

import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

public class LockActivity extends AppCompatActivity {
    private static final String TAG = "LockActivity";
    private static final String PREF_NAME = "antivol_prefs";
    private static final String KEY_DEVICE_UUID = "device_uuid";

    private EditText unlockCodeInput;
    private Button unlockButton;
    private TextView unlockError;
    private DevicePolicyManager devicePolicyManager;
    private ComponentName deviceAdminComponent;
    private String serverUrl;
    private String deviceUuid;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        getWindow().addFlags(
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED
            | WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
            | WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
            | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON
        );

        setContentView(R.layout.activity_lock);

        serverUrl = getString(R.string.server_url);
        devicePolicyManager = (DevicePolicyManager) getSystemService(Context.DEVICE_POLICY_SERVICE);
        deviceAdminComponent = new ComponentName(this, AntiVolDeviceAdmin.class);

        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
        deviceUuid = prefs.getString(KEY_DEVICE_UUID, null);

        unlockCodeInput = findViewById(R.id.unlockCodeInput);
        unlockButton = findViewById(R.id.unlockButton);
        unlockError = findViewById(R.id.unlockError);

        unlockButton.setOnClickListener(v -> attemptUnlock());

        lockScreen();
    }

    @Override
    protected void onResume() {
        super.onResume();
        lockScreen();
    }

    @Override
    public void onBackPressed() {
        // Empêcher le retour — verrouillage total
    }

    @Override
    protected void onPause() {
        super.onPause();
        // Si l'activité est mise en pause (ex: écran éteint), ne pas la détruire
        if (!isFinishing()) {
            moveTaskToBack(false);
        }
    }

    private void lockScreen() {
        if (devicePolicyManager != null && devicePolicyManager.isAdminActive(deviceAdminComponent)) {
            try {
                devicePolicyManager.lockNow();
            } catch (Exception e) {
                Log.e(TAG, "Erreur lockNow", e);
            }
        }
    }

    private void attemptUnlock() {
        String enteredCode = unlockCodeInput.getText().toString().trim();
        if (enteredCode.isEmpty()) {
            unlockError.setText("Entrez le code");
            unlockError.setVisibility(View.VISIBLE);
            return;
        }

        if (deviceUuid == null) {
            unlockError.setText("Erreur: appareil non initialisé");
            unlockError.setVisibility(View.VISIBLE);
            return;
        }

        unlockButton.setEnabled(false);
        unlockError.setVisibility(View.GONE);

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
                        Toast.makeText(this, "Appareil déverrouillé", Toast.LENGTH_SHORT).show();
                        SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
                        prefs.edit().putBoolean("was_locked", false).apply();
                        finish();
                    });
                } else {
                    runOnUiThread(() -> {
                        unlockError.setText("Code incorrect");
                        unlockError.setVisibility(View.VISIBLE);
                        unlockCodeInput.setText("");
                        unlockButton.setEnabled(true);
                    });
                }
            } catch (Exception e) {
                Log.e(TAG, "Erreur déverrouillage", e);
                runOnUiThread(() -> {
                    unlockError.setText("Erreur réseau — réessayez");
                    unlockError.setVisibility(View.VISIBLE);
                    unlockButton.setEnabled(true);
                });
            }
        }).start();
    }
}
