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
        private val KEY_DEVICE_SECRET = stringPreferencesKey("appareil_secret")
        private val KEY_ETAT_VOL = booleanPreferencesKey("etat_vol")

        private const val DEFAULT_API_URL = "https://antivol.onrender.com/api"

        /**
         * Deux stockages, une seule source de vérité.
         *
         * `SharedPreferences` sert aux lectures synchrones faites depuis un
         * `Service` ou un `BroadcastReceiver`, où l'on ne peut pas suspendre
         * pour lire le DataStore : `getXxxSync()` est donc un accès direct au
         * miroir. Toute écriture passe par les deux, et c'est le même couple
         * clé/valeur — sans quoi une lecture synchrone renverrait une valeur
         * périmée.
         *
         * Règle à respecter : ce miroir s'appelle `"antivol_prefs_sync"`.
         * `"antivol_prefs"` est le nom du DataStore et ne correspond à AUCUN
         * fichier SharedPreferences — le lire avec `getSharedPreferences`
         * renvoie une source vide, donc `-1` et des chaînes vides.
         */
        private const val SYNC_API_URL = "api_url"
        private const val SYNC_APPAREIL_ID = "appareil_id"
        private const val SYNC_APPAREIL_IMEI = "appareil_imei"
        private const val SYNC_USER_ID = "user_id"
        private const val SYNC_USER_EMAIL = "user_email"
        private const val SYNC_CODE_VERROUILLAGE = "code_verrouillage"
        private const val SYNC_CODE_USSD = "code_ussd"
        private const val SYNC_DEVICE_SECRET = "appareil_secret"
        private const val SYNC_ETAT_VOL = "etat_vol"

        /**
         * Cookie de session, sérialisé, pour le domaine de l'API.
         *
         * Volontairement **hors DataStore** : c'est un identifiant, pas un
         * état d'interface. Le DataStore alimente les `Flow` lus par les
         * `ViewModel` et par Compose ; y mettre un secret l'exposerait à
         * toute la couche UI et à la migration de schéma. Il ne sert qu'au
         * `cookieJar`, qui le lit de façon synchrone au démarrage, avant
         * l'affichage du moindre écran.
         */
        private const val SYNC_COOKIE_SESSION = "cookie_session"
    }

    private val prefs: SharedPreferences by lazy {
        context.getSharedPreferences("antivol_prefs_sync", Context.MODE_PRIVATE)
    }

    /**
     * Contexte applicatif, pour les ViewModels qui doivent lancer une opération
     * nécessitant un `Context` sans en recevoir un (écran de démarrage).
     */
    val appContext: Context get() = context.applicationContext

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

    /**
     * Secret d'appareil : la clé de tout le canal de commande.
     *
     * C'est ce secret qui dérive le topic ntfy (non devinable) et qui signe
     * les messages : sans lui, le téléphone ne reçoit AUCUNE commande et le
     * canal de secours décrit au cahier des charges reste inerte.
     *
     * Il est donné UNE seule fois par le serveur, à l'enregistrement. S'il est
     * perdu, il faut désenrôler puis réenrôler l'appareil : il n'y a pas de
     * « mot de passe oublié », par conception.
     */
    val deviceSecret: Flow<String> = context.dataStore.data.map { prefs ->
        prefs[KEY_DEVICE_SECRET] ?: ""
    }

    /**
     * L'appareil est-il déclaré volé ?
     *
     * Doit survivre à la mort du service et au redémarrage : c'est la
     * régression v1 que la v2 avait perdue. Un téléphone volé qui redémarre
     * doit se reverrouiller tout seul, sans attendre une nouvelle commande.
     */
    val etatVol: Flow<Boolean> = context.dataStore.data.map { prefs ->
        prefs[KEY_ETAT_VOL] ?: false
    }

    val isLoggedIn: Flow<Boolean> = userId.map { it != -1 }

    /** Vrai si le téléphone est enrôlé : il a un identifiant ET un secret. */
    val estEnrole: Flow<Boolean> = context.dataStore.data.map { prefs ->
        (prefs[KEY_APPAREIL_ID] ?: -1) != -1 && !(prefs[KEY_DEVICE_SECRET] ?: "").isEmpty()
    }

    fun getApiUrlSync(): String = prefs.getString(SYNC_API_URL, DEFAULT_API_URL) ?: DEFAULT_API_URL
    fun getAppareilIdSync(): Int = prefs.getInt(SYNC_APPAREIL_ID, -1)
    fun getAppareilImeiSync(): String = prefs.getString(SYNC_APPAREIL_IMEI, "") ?: ""
    fun getUserIdSync(): Int = prefs.getInt(SYNC_USER_ID, -1)
    fun getUserEmailSync(): String = prefs.getString(SYNC_USER_EMAIL, "") ?: ""
    fun getCodeVerrouillageSync(): String = prefs.getString(SYNC_CODE_VERROUILLAGE, "") ?: ""
    fun getCodeUssdSync(): String = prefs.getString(SYNC_CODE_USSD, "") ?: ""

    /** Secret d'appareil, ou chaîne vide si le téléphone n'est pas enrôlé. */
    fun getDeviceSecretSync(): String = prefs.getString(SYNC_DEVICE_SECRET, "") ?: ""

    /** L'appareil est-il déclaré volé ? Lecture synchrone, pour le service. */
    fun estVolSync(): Boolean = prefs.getBoolean(SYNC_ETAT_VOL, false)

    /**
     * Cookie de session sérialisé, ou `null` si l'application n'a jamais été
     * connectée depuis le dernier effacement.
     */
    fun getCookieSessionSync(): String? = prefs.getString(SYNC_COOKIE_SESSION, null)

    /** Enregistre le cookie de session. Une chaîne vide l'efface. */
    fun saveCookieSessionSync(serialise: String) {
        prefs.edit().apply {
            if (serialise.isEmpty()) remove(SYNC_COOKIE_SESSION)
            else putString(SYNC_COOKIE_SESSION, serialise)
        }.apply()
    }

    suspend fun setApiUrl(url: String) {
        context.dataStore.edit { prefs -> prefs[KEY_API_URL] = url }
        prefs.edit().putString(SYNC_API_URL, url).apply()
    }

    suspend fun setAppareilId(id: Int) {
        context.dataStore.edit { prefs -> prefs[KEY_APPAREIL_ID] = id }
        prefs.edit().putInt(SYNC_APPAREIL_ID, id).apply()
    }

    suspend fun setAppareilImei(imei: String) {
        context.dataStore.edit { prefs -> prefs[KEY_APPAREIL_IMEI] = imei }
        prefs.edit().putString(SYNC_APPAREIL_IMEI, imei).apply()
    }

    /**
     * Conserve le secret d'appareil et l'identifiant reçus à l'enregistrement.
     *
     * Les deux vont ensemble : le secret seul ne sert à rien sans l'identifiant
     * (le serveur adresse ses réponses à un appareil précis), et l'identifiant
     * seul ne donne aucun accès (toutes les requêtes d'appareil doivent
     * présenter le secret).
     */
    suspend fun setEnrolement(appareilId: Int, secret: String) {
        context.dataStore.edit { prefs ->
            prefs[KEY_APPAREIL_ID] = appareilId
            prefs[KEY_DEVICE_SECRET] = secret
        }
        prefs.edit()
            .putInt(SYNC_APPAREIL_ID, appareilId)
            .putString(SYNC_DEVICE_SECRET, secret)
            .apply()
    }

    /**
     * Mémorise que l'appareil est déclaré volé.
     *
     * Appelé à chaque verrouillage et à chaque déverrouillage. C'est cette
     * valeur qui survit au redémarrage et qui déclenche le re-verrouillage
     * automatique.
     */
    suspend fun setEtatVol(vol: Boolean) {
        context.dataStore.edit { prefs -> prefs[KEY_ETAT_VOL] = vol }
        prefs.edit().putBoolean(SYNC_ETAT_VOL, vol).apply()
    }

    suspend fun setCodeVerrouillage(code: String) {
        context.dataStore.edit { prefs -> prefs[KEY_APPAREIL_CODE_VERROUILLAGE] = code }
        prefs.edit().putString(SYNC_CODE_VERROUILLAGE, code).apply()
    }

    suspend fun setCodeUssd(code: String) {
        context.dataStore.edit { prefs -> prefs[KEY_APPAREIL_CODE_USSD] = code }
        prefs.edit().putString(SYNC_CODE_USSD, code).apply()
    }

    suspend fun setUserId(id: Int) {
        context.dataStore.edit { prefs -> prefs[KEY_USER_ID] = id }
        prefs.edit().putInt(SYNC_USER_ID, id).apply()
    }

    suspend fun setUserEmail(email: String) {
        context.dataStore.edit { prefs -> prefs[KEY_USER_EMAIL] = email }
        prefs.edit().putString(SYNC_USER_EMAIL, email).apply()
    }

    suspend fun saveUserSession(userId: Int, email: String) {
        context.dataStore.edit { prefs ->
            prefs[KEY_USER_ID] = userId
            prefs[KEY_USER_EMAIL] = email
        }
        prefs.edit().putInt(SYNC_USER_ID, userId).putString(SYNC_USER_EMAIL, email).apply()
    }

    /**
     * Déconnexion : plus rien de l'ancien compte ni de son appareil.
     *
     * L'URL du serveur est conservée — la ressaisir à chaque déconnexion serait
     * une pénibilité gratuite, et ce n'est pas un secret.
     *
     * L'identifiant et le secret d'appareil sont effacés : les garder
     * permettrait au téléphone suivant d'hériter des commandes envoyées à
     * l'ancien compte, puisque le service de surveillance tourne sur la base du
     * seul enrôlement.
     *
     * Le cookie de session part avec. Il est effacé ici, et pas seulement par
     * `RetrofitClient.clearCookies()`, parce que l'écran de réglages appelle
     * `clearSession()` directement : sans cette ligne, « désenrôler
     * l'appareil » laisserait une session valide sur le disque, réutilisable
     * au redémarrage suivant.
     */
    suspend fun clearSession() {
        context.dataStore.edit { prefs ->
            prefs.remove(KEY_USER_ID)
            prefs.remove(KEY_USER_EMAIL)
            prefs.remove(KEY_APPAREIL_ID)
            prefs.remove(KEY_APPAREIL_IMEI)
            prefs.remove(KEY_APPAREIL_CODE_VERROUILLAGE)
            prefs.remove(KEY_APPAREIL_CODE_USSD)
            prefs.remove(KEY_DEVICE_SECRET)
            prefs.remove(KEY_ETAT_VOL)
        }
        prefs.edit()
            .remove(SYNC_USER_ID)
            .remove(SYNC_USER_EMAIL)
            .remove(SYNC_APPAREIL_ID)
            .remove(SYNC_APPAREIL_IMEI)
            .remove(SYNC_CODE_VERROUILLAGE)
            .remove(SYNC_CODE_USSD)
            .remove(SYNC_DEVICE_SECRET)
            .remove(SYNC_ETAT_VOL)
            .remove(SYNC_COOKIE_SESSION)
            .apply()
    }

    /** Remise à zéro complète, URL du serveur comprise. */
    suspend fun clearAll() {
        context.dataStore.edit { it.clear() }
        prefs.edit().clear().apply()
    }
}
