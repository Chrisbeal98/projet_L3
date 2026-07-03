package com.antivol.mobile;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.text.method.HideReturnsTransformationMethod;
import android.text.method.PasswordTransformationMethod;
import android.view.View;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import org.json.JSONObject;

public class LoginActivity extends AppCompatActivity {

    private EditText etEmail, etPassword;
    private TextView tvError;
    private OkHttpClient client;
    private boolean passwordVisible = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (AppConfig.getUserId(this) != -1) {
            goToMain();
            return;
        }

        setContentView(R.layout.activity_login);
        client = AppConfig.getHttpClient();

        etEmail = findViewById(R.id.etEmail);
        etPassword = findViewById(R.id.etPassword);
        tvError = findViewById(R.id.tvError);

        findViewById(R.id.tvForgotPassword).setOnClickListener(v -> {
            String apiUrl = AppConfig.getApiUrl(this);
            String baseUrl = apiUrl.replace("/api", "");
            Intent browserIntent = new Intent(Intent.ACTION_VIEW, Uri.parse(baseUrl + "/reset-password"));
            startActivity(browserIntent);
        });

        etPassword.setOnLongClickListener(v -> {
            togglePasswordVisibility();
            return true;
        });
    }

    private void togglePasswordVisibility() {
        if (passwordVisible) {
            etPassword.setTransformationMethod(PasswordTransformationMethod.getInstance());
            passwordVisible = false;
        } else {
            etPassword.setTransformationMethod(HideReturnsTransformationMethod.getInstance());
            passwordVisible = true;
        }
        etPassword.setSelection(etPassword.getText().length());
    }

    public void login(View view) {
        String email = etEmail.getText().toString().trim();
        String password = etPassword.getText().toString();

        if (email.isEmpty() || password.isEmpty()) {
            showError("Veuillez remplir tous les champs");
            return;
        }

        new Thread(() -> {
            try {
                String apiUrl = AppConfig.getApiUrl(getApplicationContext());
                MediaType JSON = MediaType.parse("application/json; charset=utf-8");

                JSONObject json = new JSONObject();
                json.put("email", email);
                json.put("password", password);

                RequestBody body = RequestBody.create(json.toString(), JSON);
                Request request = new Request.Builder()
                        .url(apiUrl + "/auth/login")
                        .post(body)
                        .build();

                Response response = client.newCall(request).execute();
                String responseBody = response.body() != null ? response.body().string() : "";

                runOnUiThread(() -> {
                    if (response.isSuccessful()) {
                        try {
                            JSONObject res = new JSONObject(responseBody);
                            JSONObject user = res.getJSONObject("user");
                            int userId = user.getInt("id");
                            AppConfig.setUserId(getApplicationContext(), userId);
                            AppConfig.setUserEmail(getApplicationContext(), user.getString("email"));
                            Toast.makeText(this, "Connexion réussie", Toast.LENGTH_SHORT).show();
                            goToMain();
                        } catch (Exception e) {
                            showError("Erreur de données");
                        }
                    } else {
                        try {
                            JSONObject res = new JSONObject(responseBody);
                            showError(res.getString("error"));
                        } catch (Exception e) {
                            showError("Erreur de connexion");
                        }
                    }
                });
            } catch (Exception e) {
                runOnUiThread(() -> showError("Erreur serveur: " + e.getMessage()));
            }
        }).start();
    }

    public void goToRegister(View view) {
        startActivity(new Intent(this, RegisterActivity.class));
    }

    private void goToMain() {
        startActivity(new Intent(this, MainActivity.class));
        finish();
    }

    private void showError(String msg) {
        tvError.setText(msg);
        tvError.setVisibility(View.VISIBLE);
    }
}
