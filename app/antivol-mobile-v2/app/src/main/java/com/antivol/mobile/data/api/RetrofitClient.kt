package com.antivol.mobile.data.api

import android.util.Log
import com.antivol.mobile.data.PreferencesManager
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Client HTTP unique de l'application.
 *
 * Trois points de vigilance, tous traités ici :
 *
 * 1. **Aucun secret dans les journaux.** Le niveau `BODY` de l'intercepteur
 *    HTTP écrit l'intégralité des requêtes et des réponses dans logcat :
 *    cookie de session, secret d'appareil, codes de verrouillage, positions
 *    GPS. N'importe quelle application ayant l permission `READ_LOGS` — ou
 *    simplement un `adb logcat` sur un appareil de débogage — les obtient en
 *    clair. Le niveau est donc `NONE` en production.
 *
 * 2. **Le cookie de session ne sort pas du domaine de l'API.** L'application
 *    permet de changer d'URL de serveur (réglages, déploiement sur une
 *    instance de test). Un jar qui renvoie tous les cookies à toutes les URL
 *    enverrait le cookie de session à ce nouveau serveur — c'est-à-dire
 *    donnerait la session à qui on le demande. `SessionCookieJar` applique ce
 *    filtre, y compris sur les cookies restaurés depuis le disque.
 *
 * 3. **L'identité d'appareil est jointe automatiquement.** Le téléphone
 *    s'authentifie avec son secret `X-Device-Token` : sans cet en-tête, le
 *    serveur refuse sa position et ses commandes. Ce secret ne remplace pas
 *    la session : il ne donne accès qu'aux points d'entrée réservés à
 *    l'appareil.
 */
object RetrofitClient {

    private const val TAG = "RetrofitClient"

    private var currentBaseUrl: String = ""
    private var apiService: ApiService? = null

    /**
     * Construit par [init], car sa persistance a besoin des préférences.
     *
     * Le stockage est Branché sur `PreferencesManager` à cet instant : le jar
     * relit alors le cookie de session sur disque et l'application démarre
     * connectée, même après que le système a tué son processus.
     */
    private var cookieJar: SessionCookieJar? = null

    /** Mis à jour par `AntiVolApp` : source du secret d'appareil. */
    private var preferencesManager: PreferencesManager? = null

    fun init(preferencesManager: PreferencesManager) {
        this.preferencesManager = preferencesManager
        cookieJar = SessionCookieJar(stockageCookie(preferencesManager))
        // Le client dépend de l'URL et du secret : on le reconstruit.
        apiService = null
        currentBaseUrl = ""
    }

    /**
     * Support d'écriture du jar, adossé aux préférences synchrones.
     *
     * `apply()` et non `commit()` : l'écriture est différée, ce qui convient à
     * une capture de cookie qui arrive en réponse d'un appel réseau, et
     * surtout ne retarde pas l'appel en cours. Perdre la toute dernière
     * écriture si le processus est tué dans la fenêtre n'a pas de
     * conséquence : le cookie vient d'être reçu du serveur, et la session
     * se reconstitue en se reconnectant.
     */
    private fun stockageCookie(preferencesManager: PreferencesManager) =
        object : SessionCookieJar.Stockage {
            override fun lire(): String? = preferencesManager.getCookieSessionSync()
            override fun ecrire(serialise: String) = preferencesManager.saveCookieSessionSync(serialise)
        }


    fun getApiService(baseUrl: String): ApiService {
        val normalizedUrl = baseUrl.trimEnd('/') + "/"
        if (apiService == null || normalizedUrl != currentBaseUrl) {
            currentBaseUrl = normalizedUrl
            apiService = construire(normalizedUrl)
        }
        return apiService!!
    }

    private fun construire(baseUrl: String): ApiService {
        val jar = cookieJar
            ?: error("RetrofitClient.init() doit être appelé avant getApiService()")

        val logging = HttpLoggingInterceptor { message -> Log.d(TAG, message) }.apply {
            // Jamais BODY ni HEADERS : voir l'en-tête du fichier.
            level = HttpLoggingInterceptor.Level.NONE
            redactHeader("Authorization")
            redactHeader("X-Device-Token")
            redactHeader("Cookie")
            redactHeader("Set-Cookie")
        }

        val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .writeTimeout(10, TimeUnit.SECONDS)
            .cookieJar(jar)
            .addInterceptor(EnteteAppareilInterceptor())
            .addInterceptor(logging)
            .build()

        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }

    /** Déconnexion : le cookie disparaît aussi du disque, pas seulement en mémoire. */
    fun clearCookies() {
        cookieJar?.clear()
    }

    /**
     * Joint le secret d'appareil à chaque requête.
     *
     * L'en-tête est posé même quand le secret est absent : le serveur répond
     * alors 403 avec un message explicite, ce qui permet à l'application de
     * distinguer « pas enrôlé » d'un échec réseau, au lieu d'un 404 trompeur.
     */
    private class EnteteAppareilInterceptor : Interceptor {
        override fun intercept(chain: Interceptor.Chain): Response {
            val secret = preferencesManager?.getDeviceSecretSync().orEmpty()
            val requete = chain.request().newBuilder()
                .header("X-Device-Token", secret)
                .build()
            return chain.proceed(requete)
        }
    }
}
