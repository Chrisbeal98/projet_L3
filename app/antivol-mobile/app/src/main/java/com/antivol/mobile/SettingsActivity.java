package com.antivol.mobile;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

public class SettingsActivity extends AppCompatActivity {

    private EditText etApiUrl, etAppareilId;
    private TextView tvUserEmail;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);

        tvUserEmail = findViewById(R.id.tvUserEmail);
        etApiUrl = findViewById(R.id.etApiUrl);
        etAppareilId = findViewById(R.id.etAppareilId);
        Button btnSave = findViewById(R.id.btnSave);
        Button btnLogout = findViewById(R.id.btnLogout);

        tvUserEmail.setText(AppConfig.getUserEmail(this));
        etApiUrl.setText(AppConfig.getApiUrl(this));

        int appareilId = AppConfig.getAppareilId(this);
        if (appareilId != -1) {
            etAppareilId.setText(String.valueOf(appareilId));
        }

        btnSave.setOnClickListener(v -> saveSettings());
        btnLogout.setOnClickListener(v -> logout());
    }

    private void saveSettings() {
        String url = etApiUrl.getText().toString().trim();
        String idStr = etAppareilId.getText().toString().trim();

        if (!url.isEmpty()) {
            AppConfig.setApiUrl(this, url);
        }

        if (!idStr.isEmpty()) {
            try {
                int id = Integer.parseInt(idStr);
                AppConfig.setAppareilId(this, id);
            } catch (NumberFormatException e) {
                Toast.makeText(this, "ID invalide", Toast.LENGTH_SHORT).show();
                return;
            }
        }

        Toast.makeText(this, "Paramètres sauvegardés", Toast.LENGTH_SHORT).show();
    }

    private void logout() {
        AppConfig.logout(this);
        startActivity(new Intent(this, LoginActivity.class));
        finishAffinity();
    }
}
