package com.antivol.mobile;

import android.app.AlertDialog;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class AlertesActivity extends AppCompatActivity {

    private TextView tvEnCours, tvResolues, tvTotal, tvEmpty;
    private LinearLayout layoutAlertes;
    private Button btnReport;
    private OkHttpClient client;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_alerts);

        client = AppConfig.getHttpClient();

        tvEnCours = findViewById(R.id.tvEnCours);
        tvResolues = findViewById(R.id.tvResolues);
        tvTotal = findViewById(R.id.tvTotal);
        tvEmpty = findViewById(R.id.tvEmpty);
        layoutAlertes = findViewById(R.id.layoutAlertes);
        btnReport = findViewById(R.id.btnReport);

        btnReport.setOnClickListener(v -> showReportDialog());
    }

    @Override
    protected void onResume() {
        super.onResume();
        loadAlertes();
    }

    private void loadAlertes() {
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
                        .url(apiUrl + "/alertes")
                        .post(body)
                        .build();

                try (Response response = client.newCall(request).execute()) {
                    if (response.isSuccessful()) {
                        ResponseBody rb = response.body();
                        if (rb != null) {
                            JSONArray alertes = new JSONArray(rb.string());
                            runOnUiThread(() -> displayAlertes(alertes));
                        }
                    }
                }
            } catch (Exception ignored) {}
        }).start();
    }

    private void displayAlertes(JSONArray alertes) {
        layoutAlertes.removeAllViews();

        int enCours = 0, resolues = 0, total = alertes.length();

        if (total == 0) {
            tvEmpty.setVisibility(View.VISIBLE);
            return;
        }
        tvEmpty.setVisibility(View.GONE);

        SimpleDateFormat sdf = new SimpleDateFormat("dd/MM/yyyy HH:mm", Locale.getDefault());

        for (int i = 0; i < alertes.length(); i++) {
            try {
                JSONObject a = alertes.getJSONObject(i);
                String type = a.optString("type", "?");
                String statut = a.optString("statut", "?");
                String description = a.optString("description", "");
                int id = a.optInt("id", 0);

                if ("en_cours".equals(statut)) enCours++;
                else resolues++;

                View card = getLayoutInflater().inflate(R.layout.item_alerte, null);
                TextView tvType = card.findViewById(android.R.id.text1);
                TextView tvDesc = card.findViewById(android.R.id.text2);
                Button btnResoudre = card.findViewById(R.id.btnResoudre);

                String typeIcon = "vol".equals(type) ? "🚨" : "perte".equals(type) ? "🔍" : "⚠️";
                tvType.setText(typeIcon + " " + type.toUpperCase() + " — " + statut.replace("_", " "));
                tvDesc.setText(description.isEmpty() ? "Aucune description" : description);

                if ("en_cours".equals(statut)) {
                    final int alerteId = id;
                    btnResoudre.setVisibility(View.VISIBLE);
                    btnResoudre.setOnClickListener(v -> resoudreAlerte(alerteId));
                } else {
                    btnResoudre.setVisibility(View.GONE);
                }

                layoutAlertes.addView(card);
            } catch (Exception ignored) {}
        }

        tvEnCours.setText(String.valueOf(enCours));
        tvResolues.setText(String.valueOf(resolues));
        tvTotal.setText(String.valueOf(total));
    }

    private void resoudreAlerte(int alerteId) {
        new Thread(() -> {
            try {
                String apiUrl = AppConfig.getApiUrl(getApplicationContext());
                int userId = AppConfig.getUserId(getApplicationContext());

                MediaType JSON = MediaType.parse("application/json; charset=utf-8");
                JSONObject json = new JSONObject();
                json.put("user_id", userId);

                RequestBody body = RequestBody.create(json.toString(), JSON);
                Request request = new Request.Builder()
                        .url(apiUrl + "/alertes/" + alerteId + "/resoudre")
                        .post(body)
                        .build();

                try (Response response = client.newCall(request).execute()) {
                    runOnUiThread(() -> {
                        if (response.isSuccessful()) {
                            Toast.makeText(this, "Alerte résolue", Toast.LENGTH_SHORT).show();
                            loadAlertes();
                        } else {
                            Toast.makeText(this, "Erreur lors de la résolution", Toast.LENGTH_SHORT).show();
                        }
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Erreur: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    private void showReportDialog() {
        AlertDialog.Builder builder = new AlertDialog.Builder(this);
        builder.setTitle("Signaler un vol / perte");

        builder.setSingleChoiceItems(new String[]{"Vol", "Perte", "Anomalie"}, 0, (d, w) -> {});
        builder.setPositiveButton("Signaler", (d, w) -> {
            int selected = ((AlertDialog) d).getListView().getCheckedItemPosition();
            String[] types = {"vol", "perte", "anomalie"};
            String type = types[selected];
            signalerAlerte(type);
        });
        builder.setNegativeButton("Annuler", null);
        builder.show();
    }

    private void signalerAlerte(String type) {
        new Thread(() -> {
            try {
                String apiUrl = AppConfig.getApiUrl(getApplicationContext());
                int userId = AppConfig.getUserId(getApplicationContext());
                int appareilId = AppConfig.getAppareilId(getApplicationContext());

                if (appareilId == -1) {
                    runOnUiThread(() -> Toast.makeText(this, "Aucun appareil enregistré", Toast.LENGTH_SHORT).show());
                    return;
                }

                MediaType JSON = MediaType.parse("application/json; charset=utf-8");
                JSONObject json = new JSONObject();
                json.put("user_id", userId);
                json.put("appareil_id", appareilId);
                json.put("type_alerte", type);
                json.put("description", "Signalé depuis l'application mobile");

                RequestBody body = RequestBody.create(json.toString(), JSON);
                Request request = new Request.Builder()
                        .url(apiUrl + "/alertes/signaler")
                        .post(body)
                        .build();

                try (Response response = client.newCall(request).execute()) {
                    runOnUiThread(() -> {
                        if (response.isSuccessful()) {
                            Toast.makeText(this, "Alerte signalée !", Toast.LENGTH_SHORT).show();
                            loadAlertes();
                        } else {
                            Toast.makeText(this, "Erreur lors du signalement", Toast.LENGTH_SHORT).show();
                        }
                    });
                }
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "Erreur: " + e.getMessage(), Toast.LENGTH_SHORT).show());
            }
        }).start();
    }
}
