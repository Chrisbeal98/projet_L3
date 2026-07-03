package com.antivol.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import okhttp3.Cookie;
import okhttp3.CookieJar;
import okhttp3.HttpUrl;
import okhttp3.OkHttpClient;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class AppConfig {
    private static final String PREFS_NAME = "antivol_prefs";
    private static final String KEY_API_URL = "api_url";
    private static final String KEY_APPAREIL_ID = "appareil_id";
    private static final String KEY_API_TOKEN = "api_token";

    private static final String DEFAULT_API_URL = "http://192.168.44.35:8000/api";
    private static final int DEFAULT_APPAREIL_ID = -1;

    private static OkHttpClient httpClient;
    private static InMemoryCookieJar cookieJar;

    public static synchronized OkHttpClient getHttpClient() {
        if (httpClient == null) {
            cookieJar = new InMemoryCookieJar();
            httpClient = new OkHttpClient.Builder()
                    .connectTimeout(10, TimeUnit.SECONDS)
                    .readTimeout(10, TimeUnit.SECONDS)
                    .writeTimeout(10, TimeUnit.SECONDS)
                    .cookieJar(cookieJar)
                    .build();
        }
        return httpClient;
    }

    private static class InMemoryCookieJar implements CookieJar {
        private final List<Cookie> cookies = new ArrayList<>();

        @Override
        public void saveFromResponse(HttpUrl url, List<Cookie> cookies) {
            this.cookies.addAll(cookies);
        }

        @Override
        public List<Cookie> loadForRequest(HttpUrl url) {
            List<Cookie> valid = new ArrayList<>();
            List<Cookie> expired = new ArrayList<>();
            for (Cookie cookie : cookies) {
                if (cookie.expiresAt() < System.currentTimeMillis()) {
                    expired.add(cookie);
                } else {
                    valid.add(cookie);
                }
            }
            cookies.removeAll(expired);
            return valid;
        }

        public void clear() {
            cookies.clear();
        }
    }
    
    public static String getApiUrl(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getString(KEY_API_URL, DEFAULT_API_URL);
    }
    
    public static void setApiUrl(Context context, String url) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(KEY_API_URL, url).apply();
    }
    
    public static int getAppareilId(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getInt(KEY_APPAREIL_ID, DEFAULT_APPAREIL_ID);
    }
    
    public static void setAppareilId(Context context, int id) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putInt(KEY_APPAREIL_ID, id).apply();
    }
    
    public static String getApiToken(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getString(KEY_API_TOKEN, "");
    }
    
    public static void setApiToken(Context context, String token) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(KEY_API_TOKEN, token).apply();
    }

    // IMEI
    private static final String KEY_APPAREIL_IMEI = "appareil_imei";

    public static String getAppareilImei(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getString(KEY_APPAREIL_IMEI, "");
    }

    public static void setAppareilImei(Context context, String imei) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(KEY_APPAREIL_IMEI, imei).apply();
    }

    // User ID
    private static final String KEY_USER_ID = "user_id";
    private static final String KEY_USER_EMAIL = "user_email";

    public static int getUserId(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getInt(KEY_USER_ID, -1);
    }

    public static void setUserId(Context context, int id) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putInt(KEY_USER_ID, id).apply();
    }

    public static String getUserEmail(Context context) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        return prefs.getString(KEY_USER_EMAIL, "");
    }

    public static void setUserEmail(Context context, String email) {
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit().putString(KEY_USER_EMAIL, email).apply();
    }

    public static void clearCookies() {
        if (cookieJar != null) {
            cookieJar.clear();
        }
    }

    public static void logout(Context context) {
        clearCookies();
        SharedPreferences prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        prefs.edit()
                .remove(KEY_USER_ID)
                .remove(KEY_USER_EMAIL)
                .remove(KEY_API_TOKEN)
                .apply();
    }
}
