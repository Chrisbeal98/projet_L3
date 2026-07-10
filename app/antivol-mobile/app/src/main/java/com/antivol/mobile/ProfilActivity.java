package com.antivol.mobile;

import android.os.Bundle;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;

import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Locale;

public class ProfilActivity extends AppCompatActivity {

    private TextView tvAvatar, tvFullName, tvRole, tvEmail, tvTelephone, tvDateCreation;
    private OkHttpClient client;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_profil);

        client = AppConfig.getHttpClient();

        tvAvatar = findViewById(R.id.tvAvatar);
        tvFullName = findViewById(R.id.tvFullName);
        tvRole = findViewById(R.id.tvRole);
        tvEmail = findViewById(R.id.tvEmail);
        tvTelephone = findViewById(R.id.tvTelephone);
        tvDateCreation = findViewById(R.id.tvDateCreation);

        loadProfile();
    }

    private void loadProfile() {
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
                        .url(apiUrl + "/auth/me")
                        .post(body)
                        .build();

                try (Response response = client.newCall(request).execute()) {
                    if (response.isSuccessful()) {
                        ResponseBody rb = response.body();
                        if (rb != null) {
                            JSONObject data = new JSONObject(rb.string());
                            JSONObject user = data.getJSONObject("user");

                            final String nom = user.optString("nom", "");
                            final String prenom = user.optString("prenom", "");
                            final String email = user.optString("email", "");
                            final String telephone = user.optString("telephone", "");
                            final String role = user.optString("role", "utilisateur");
                            final String dateStr = user.optString("date_creation", "");

                            runOnUiThread(() -> {
                                String initials = (prenom.isEmpty() ? "" : prenom.substring(0, 1))
                                        + (nom.isEmpty() ? "" : nom.substring(0, 1));
                                tvAvatar.setText(initials.isEmpty() ? "?" : initials.toUpperCase());
                                tvFullName.setText(prenom + " " + nom);
                                tvRole.setText(role.isEmpty() ? "?" : role.substring(0, 1).toUpperCase() + role.substring(1));
                                tvEmail.setText(email);
                                tvTelephone.setText(telephone.isEmpty() ? "Non renseigné" : telephone);

                                if (!dateStr.isEmpty()) {
                                    try {
                                        SimpleDateFormat iso = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault());
                                        SimpleDateFormat out = new SimpleDateFormat("dd/MM/yyyy", Locale.getDefault());
                                        tvDateCreation.setText(out.format(iso.parse(dateStr)));
                                    } catch (Exception e) {
                                        tvDateCreation.setText(dateStr.substring(0, 10));
                                    }
                                } else {
                                    tvDateCreation.setText("--");
                                }
                            });
                        }
                    }
                }
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Erreur: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }
}
