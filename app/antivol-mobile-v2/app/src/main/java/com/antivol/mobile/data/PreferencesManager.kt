package com.antivol.mobile.data

import android.content.Context
import android.content.SharedPreferences
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.*
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "antivol_prefs")

class PreferencesManager(private val context: Context) {

    companion object {
        private val KEY_API_URL = stringPreferencesKey("api_url")
        private val KEY_APPAREIL_ID = intPreferencesKey("appareil_id")
        private val KEY_APPAREIL_IMEI = stringPreferencesKey("appareil_imei")
        private val KEY_APPAREIL_CODE_VERROUILLAGE = stringPreferencesKey("appareil_code_verrouillage")
        private val KEY_APPAREIL_CODE_USSD = stringPreferencesKey("appareil_code_ussd")
        private val KEY_USER_ID = intPreferencesKey("user_id")
        private val KEY_USER_EMAIL = stringPreferencesKey("user_email")

        private const val DEFAULT_API_URL = "http://192.168.46.54:8000/api"
    }

    private val prefs: SharedPreferences by lazy {
        context.getSharedPreferences("antivol_prefs_sync", Context.MODE_PRIVATE)
    }

    val apiUrl: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_API_URL] ?: DEFAULT_API_URL
    }

    val appareilId: Flow<Int> = context.dataStore.data.map { prefs ->
        prefs[KEY_APPAREIL_ID] ?: -1
    }

    val appareilImei: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_APPAREIL_IMEI] ?: ""
    }

    val userId: Flow<Int> = context.dataStore.data.map { prefs ->
        prefs[KEY_USER_ID] ?: -1
    }

    val userEmail: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_USER_EMAIL] ?: ""
    }

    val codeVerrouillage: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_APPAREIL_CODE_VERROUILLAGE] ?: ""
    }

    val codeUssd: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_APPAREIL_CODE_USSD] ?: ""
    }

    val isLoggedIn: Flow<Boolean> = userId.map { it != -1 }

    fun getApiUrlSync(): String = prefs.getString("api_url", DEFAULT_API_URL) ?: DEFAULT_API_URL
    fun getAppareilIdSync(): Int = prefs.getInt("appareil_id", -1)
    fun getAppareilImeiSync(): String = prefs.getString("appareil_imei", "") ?: ""
    fun getUserIdSync(): Int = prefs.getInt("user_id", -1)
    fun getUserEmailSync(): String = prefs.getString("user_email", "") ?: ""
    fun getCodeVerrouillageSync(): String = prefs.getString("code_verrouillage", "") ?: ""
    fun getCodeUssdSync(): String = prefs.getString("code_ussd", "") ?: ""

    private fun syncToSharedPrefs() {
        val s = prefs
        s.edit()
            .putString("api_url", getApiUrlSync())
            .putInt("appareil_id", getAppareilIdSync())
            .putString("appareil_imei", getAppareilImeiSync())
            .putString("user_email", getUserEmailSync())
            .putInt("user_id", getUserIdSync())
            .putString("code_verrouillage", getCodeVerrouillageSync())
            .putString("code_ussd", getCodeUssdSync())
            .apply()
    }

    suspend fun setApiUrl(url: String) {
        context.dataStore.edit { prefs -> prefs[KEY_API_URL] = url }
        prefs.edit().putString("api_url", url).apply()
    }

    suspend fun setAppareilId(id: Int) {
        context.dataStore.edit { prefs -> prefs[KEY_APPAREIL_ID] = id }
        prefs.edit().putInt("appareil_id", id).apply()
    }

    suspend fun setAppareilImei(imei: String) {
        context.dataStore.edit { prefs -> prefs[KEY_APPAREIL_IMEI] = imei }
        prefs.edit().putString("appareil_imei", imei).apply()
    }

    suspend fun setCodeVerrouillage(code: String) {
        context.dataStore.edit { prefs -> prefs[KEY_APPAREIL_CODE_VERROUILLAGE] = code }
        prefs.edit().putString("code_verrouillage", code).apply()
    }

    suspend fun setCodeUssd(code: String) {
        context.dataStore.edit { prefs -> prefs[KEY_APPAREIL_CODE_USSD] = code }
        prefs.edit().putString("code_ussd", code).apply()
    }

    suspend fun setUserId(id: Int) {
        context.dataStore.edit { prefs -> prefs[KEY_USER_ID] = id }
        prefs.edit().putInt("user_id", id).apply()
    }

    suspend fun setUserEmail(email: String) {
        context.dataStore.edit { prefs -> prefs[KEY_USER_EMAIL] = email }
        prefs.edit().putString("user_email", email).apply()
    }

    suspend fun saveUserSession(userId: Int, email: String) {
        context.dataStore.edit { prefs ->
            prefs[KEY_USER_ID] = userId
            prefs[KEY_USER_EMAIL] = email
        }
        prefs.edit().putInt("user_id", userId).putString("user_email", email).apply()
    }

    suspend fun clearSession() {
        context.dataStore.edit { prefs ->
            prefs.remove(KEY_USER_ID)
            prefs.remove(KEY_USER_EMAIL)
        }
        prefs.edit().remove("user_id").remove("user_email").apply()
    }

    suspend fun clearAll() {
        context.dataStore.edit { it.clear() }
        prefs.edit().clear().apply()
    }
}
