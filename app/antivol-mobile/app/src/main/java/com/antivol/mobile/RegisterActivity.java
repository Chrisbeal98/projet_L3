package com.antivol.mobile;

import android.content.Intent;
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

public class RegisterActivity extends AppCompatActivity {

    private EditText etNom, etPrenom, etEmail, etTelephone, etPassword, etConfirm;
    private TextView tvError;
    private OkHttpClient client;
    private boolean passVisible = false, confirmVisible = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        if (AppConfig.getUserId(this) != -1) {
            goToMain();
            return;
        }

        setContentView(R.layout.activity_register);
        client = AppConfig.getHttpClient();

        etNom = findViewById(R.id.etNom);
        etPrenom = findViewById(R.id.etPrenom);
        etEmail = findViewById(R.id.etEmail);
        etTelephone = findViewById(R.id.etTelephone);
        etPassword = findViewById(R.id.etPassword);
        etConfirm = findViewById(R.id.etConfirmPassword);
        tvError = findViewById(R.id.tvError);

        etPassword.setOnLongClickListener(v -> {
            togglePass();
            return true;
        });
        etConfirm.setOnLongClickListener(v -> {
            toggleConfirm();
            return true;
        });
    }

    private void togglePass() {
        if (passVisible) {
            etPassword.setTransformationMethod(PasswordTransformationMethod.getInstance());
            passVisible = false;
        } else {
            etPassword.setTransformationMethod(HideReturnsTransformationMethod.getInstance());
            passVisible = true;
        }
        etPassword.setSelection(etPassword.getText().length());
    }

    private void toggleConfirm() {
        if (confirmVisible) {
            etConfirm.setTransformationMethod(PasswordTransformationMethod.getInstance());
            confirmVisible = false;
        } else {
            etConfirm.setTransformationMethod(HideReturnsTransformationMethod.getInstance());
            confirmVisible = true;
        }
        etConfirm.setSelection(etConfirm.getText().length());
    }

    public void register(View view) {
        String nom = etNom.getText().toString().trim();
        String prenom = etPrenom.getText().toString().trim();
        String email = etEmail.getText().toString().trim();
        String telephone = etTelephone.getText().toString().trim();
        String password = etPassword.getText().toString();
        String confirm = etConfirm.getText().toString();

        if (nom.isEmpty() || prenom.isEmpty() || email.isEmpty() || password.isEmpty()) {
            showError("Veuillez remplir tous les champs obligatoires");
            return;
        }

        if (!password.equals(confirm)) {
            showError("Les mots de passe ne correspondent pas");
            return;
        }

        if (password.length() < 6) {
            showError("Le mot de passe doit contenir au moins 6 caractères");
            return;
        }

        new Thread(() -> {
            try {
                String apiUrl = AppConfig.getApiUrl(getApplicationContext());
                MediaType JSON = MediaType.parse("application/json; charset=utf-8");

                JSONObject json = new JSONObject();
                json.put("nom", nom);
                json.put("prenom", prenom);
                json.put("email", email);
                json.put("telephone", telephone);
                json.put("password", password);

                RequestBody body = RequestBody.create(json.toString(), JSON);
                Request request = new Request.Builder()
                        .url(apiUrl + "/auth/register")
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
                            Toast.makeText(this, "Compte créé avec succès", Toast.LENGTH_SHORT).show();
                            goToMain();
                        } catch (Exception e) {
                            showError("Erreur de données");
                        }
                    } else {
                        try {
                            JSONObject res = new JSONObject(responseBody);
                            showError(res.getString("error"));
                        } catch (Exception e) {
                            showError("Erreur d'inscription");
                        }
                    }
                });
            } catch (Exception e) {
                runOnUiThread(() -> showError("Erreur serveur: " + e.getMessage()));
            }
        }).start();
    }

    public void goToLogin(View view) {
        finish();
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
