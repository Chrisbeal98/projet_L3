# ProGuard rules for Antivol Intelligent

# OkHttp
-dontwarn okhttp3.**
-keep class okhttp3.** { *; }
-keep interface okhttp3.** { *; }

# Okio
-dontwarn okio.**
-keep class okio.** { *; }

# JSON
-keep class org.json.** { *; }

# Firebase / FCM
-keep class com.google.firebase.** { *; }
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.firebase.**
-dontwarn com.google.android.gms.**

# Keep JSON model classes
-keepclassmembers class com.antivol.mobile.** {
    public *;
}

# Keep service classes (needed for manifest registration)
-keep class com.antivol.mobile.MonitorService { *; }
-keep class com.antivol.mobile.AntivolFirebaseService { *; }
-keep class com.antivol.mobile.AdminReceiver { *; }
-keep class com.antivol.mobile.BootReceiver { *; }

# Don't obfuscate SharedPreferences keys
-keepclassmembers class com.antivol.mobile.AppConfig {
    private static final java.lang.String PREFS_NAME;
    private static final java.lang.String KEY_API_URL;
    private static final java.lang.String KEY_APPAREIL_ID;
    private static final java.lang.String KEY_API_TOKEN;
    private static final java.lang.String KEY_APPAREIL_IMEI;
    private static final java.lang.String KEY_USER_ID;
    private static final java.lang.String KEY_USER_EMAIL;
}

# Gson (if used by Google Play Services)
-keepattributes Signature
-keepattributes *Annotation*
-dontwarn sun.misc.**
-keep class com.google.gson.** { *; }
