package com.antivol.mobile;

import android.os.Bundle;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;

import org.json.JSONArray;
import org.json.JSONObject;

public class ZonesActivity extends AppCompatActivity {

    private TextView tvEmpty;
    private LinearLayout layoutZones;
    private OkHttpClient client;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_zones);

        client = AppConfig.getHttpClient();
        tvEmpty = findViewById(R.id.tvEmpty);
        layoutZones = findViewById(R.id.layoutZones);
    }

    @Override
    protected void onResume() {
        super.onResume();
        loadZones();
    }

    private void loadZones() {
        new Thread(() -> {
            try {
                String apiUrl = AppConfig.getApiUrl(getApplicationContext());

                Request request = new Request.Builder()
                        .url(apiUrl + "/zones-risque")
                        .get()
                        .build();

                try (Response response = client.newCall(request).execute()) {
                    if (response.isSuccessful()) {
                        ResponseBody rb = response.body();
                        if (rb != null) {
                            JSONArray zones = new JSONArray(rb.string());
                            runOnUiThread(() -> displayZones(zones));
                        }
                    }
                }
            } catch (Exception ignored) {}
        }).start();
    }

    private void displayZones(JSONArray zones) {
        layoutZones.removeAllViews();

        if (zones.length() == 0) {
            tvEmpty.setVisibility(View.VISIBLE);
            return;
        }
        tvEmpty.setVisibility(View.GONE);

        for (int i = 0; i < zones.length(); i++) {
            try {
                JSONObject z = zones.getJSONObject(i);
                String nom = z.optString("nom", "?");
                String ville = z.optString("ville", "");
                String niveau = z.optString("niveau_risque", "moyen");
                int incidents = z.optInt("nombre_incidents", 0);

                View card = getLayoutInflater().inflate(R.layout.item_alerte, null);
                TextView tvType = card.findViewById(android.R.id.text1);
                TextView tvDesc = card.findViewById(android.R.id.text2);
                card.findViewById(R.id.btnResoudre).setVisibility(View.GONE);

                String icon;
                int color;
                switch (niveau) {
                    case "critique":
                        icon = "\uD83D\uDD34";
                        color = getResources().getColor(android.R.color.holo_red_dark);
                        break;
                    case "élevé":
                    case "eleve":
                        icon = "\uD83D\uDFE0";
                        color = getResources().getColor(android.R.color.holo_orange_dark);
                        break;
                    case "moyen":
                        icon = "\uD83D\uDFE1";
                        color = getResources().getColor(android.R.color.holo_orange_light);
                        break;
                    default:
                        icon = "\uD83D\uDFE2";
                        color = getResources().getColor(android.R.color.holo_green_dark);
                        break;
                }

                tvType.setText(icon + " " + nom + " (" + ville + ")");
                tvType.setTextColor(color);
                tvDesc.setText(niveau.toUpperCase() + " — " + incidents + " incident(s)");

                layoutZones.addView(card);
            } catch (Exception ignored) {}
        }
    }
}
