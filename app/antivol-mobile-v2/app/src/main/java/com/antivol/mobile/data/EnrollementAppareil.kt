package com.antivol.mobile.data

import android.content.Context
import android.os.Build
import android.provider.Settings
import android.util.Log
import com.antivol.mobile.data.api.RetrofitClient
import com.antivol.mobile.data.model.RegisterDeviceRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Enrôlement du téléphone auprès du serveur.
 *
 * ─── Pourquoi cette étape est indispensable ───
 *
 * Sans elle, le téléphone n'a ni identifiant serveur (`appareil_id = -1`) ni
 * secret d'appareil. Conséquences, toutes vérifiées dans le code :
 *  - `MonitorService.sendLocation()` sort immédiatement (`if (deviceId == -1)
 *    return`) : le téléphone n'envoie AUCUNE position ;
 *  - le topic ntfy ne peut pas être calculé, donc aucun canal de commande ;
 *  - `BootReceiver` refuse de relancer le service.
 *
 * Autrement dit, sans enrôlement l'application affiche un tableau de bord
 * et ne protège rien. L'enrôlement est donc fait dès que la session existe,
 * et rejoué à chaque démarrage tant qu'il n'a pas abouti.
 *
 * ─── Identifiant matériel ───
 *
 * Le champ s'appelle `imei` côté serveur (héritage du client v0), mais
 * `TelephonyManager.getImei()` est interdit aux applications ordinaires depuis
 * Android 10 : il lève une exception, et tentar de contourner ce refus est
 * interdit par Google Play. On utilise donc `ANDROID_ID`, un identifiant
 * stable par application et par appareil, anonymisé par Android, et sufficient
 * pour reconnaître le téléphone à travers une réinstallation.
 *
 * Ce n'est pas un identifiant unique au monde : deux appareils portant le même
 * `ANDROID_ID` (restauration de sauvegarde, clonage) seraient refusés par le
 * serveur, qui répond 409. C'est le comportement voulu — mieux vaut un refus
 * explicite qu'un rattachement au mauvais compte.
 */
object EnrollementAppareil {

    private const val TAG = "EnrollementAppareil"

    /**
     * Identifiant matériel stable, à passer au champ `imei` du serveur.
     *
     * @return identifiant, ou null si Android refuse de le fournir.
     */
    fun identifiantMateriel(context: Context): String? =
        try {
            Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
                ?.takeIf { it.isNotBlank() }
        } catch (e: Exception) {
            Log.w(TAG, "ANDROID_ID indisponible: ${e.message}")
            null
        }

    fun modele(): String = Build.MODEL ?: "Inconnu"

    fun marque(): String = Build.MANUFACTURER ?: "Inconnu"

    /**
     * Enrôle le téléphone s'il ne l'est pas encore.
     *
     * Idempotent : si l'appareil possède déjà un identifiant ET un secret, on
     * ne fait rien. L'appel est donc sans danger au démarrage, à la
     * reconnexion et après une reconnexion réseau.
     *
     * @return true si le téléphone est enrôlé à la fin de l'appel.
     */
    suspend fun enrollerSiBesoin(
        context: Context,
        preferencesManager: PreferencesManager
    ): Boolean = withContext(Dispatchers.IO) {
        try {
            // Garde-fou local : évite un appel réseau inutile quand aucune session
            // n'existe. Ce n'est PAS une identité — l'identifiant du
            // compte n'est jamais transmis, le serveur déduit le propriétaire
            // du seul cookie de session.
            if (preferencesManager.getUserIdSync() == -1) {
                Log.i(TAG, "Pas de session : enrôlement ignoré")
                return@withContext false
            }

            if (preferencesManager.getAppareilIdSync() != -1 &&
                preferencesManager.getDeviceSecretSync().isNotEmpty()
            ) {
                return@withContext true
            }

            val identifiant = identifiantMateriel(context)
            if (identifiant == null) {
                Log.e(TAG, "Enrôlement impossible : identifiant matériel indisponible")
                return@withContext false
            }

            val apiUrl = preferencesManager.getApiUrlSync()
            val api = RetrofitClient.getApiService(apiUrl)
            val reponse = api.registerDevice(
                RegisterDeviceRequest(
                    imei = identifiant,
                    modele = modele(),
                    marque = marque()
                )
            )

            val corps = reponse.body()
            if (!reponse.isSuccessful || corps == null) {
                Log.e(TAG, "Enrôlement refusé (HTTP ${reponse.code()})")
                return@withContext false
            }

            // Le secret n'est renvoyé qu'à la PREMIÈRE inscription. Si le
            // serveur n'en renvoie aucun, le téléphone est déjà connu et
            // possède déjà un secret : on ne peut rien décider ici, il faut
            // désenrôler le téléphone côté serveur pour en obtenir un neuf.
            val secret = corps.deviceToken
            if (secret.isNullOrEmpty()) {
                Log.w(TAG, "Appareil déjà enrôlé : aucun secret renvoyé")
                return@withContext false
            }

            preferencesManager.setEnrolement(corps.id, secret)
            preferencesManager.setAppareilImei(identifiant)
            corps.codeVerrouillage?.let { preferencesManager.setCodeVerrouillage(it) }
            corps.codePinEffectif?.let { preferencesManager.setCodeUssd(it) }

            Log.i(TAG, "Appareil enrôlé (id=${corps.id})")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Échec de l'enrôlement: ${e.message}")
            false
        }
    }
}
