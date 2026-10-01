package com.antivol.mobile.data.model

import com.google.gson.annotations.SerializedName

data class LoginRequest(val email: String, val password: String)

data class LoginResponse(
    val user: UserData,
    val message: String? = null
)

data class RegisterRequest(
    val nom: String,
    val prenom: String,
    val email: String,
    val telephone: String,
    val password: String
)

data class RegisterResponse(
    val user: UserData,
    val message: String? = null
)

data class UserData(
    val id: Int,
    val nom: String,
    val prenom: String,
    val email: String,
    val telephone: String? = null,
    val role: String = "utilisateur",
    @SerializedName("date_creation") val dateCreation: String? = null
)

data class StatsResponse(
    @SerializedName("total_appareils") val totalAppareils: Int = 0,
    @SerializedName("total_alertes") val totalAlertes: Int = 0,
    @SerializedName("total_voles") val totalVoles: Int = 0,
    @SerializedName("total_verrouilles") val totalVerrouilles: Int = 0
)

data class DeviceStatusResponse(
    val statut: String,
    val verrouille: Boolean
)

data class RegisterDeviceRequest(
    /**
     * Identifiant matériel du téléphone.
     *
     * Le champ porte le nom `imei` pour rester compatible avec le serveur et
     * les anciens clients, mais il reçoit `ANDROID_ID` : `getImei()` est
     * interdit aux applications ordinaires depuis Android 10. Voir
     * `EnrollementAppareil`.
     */
    val imei: String,
    val modele: String,
    val marque: String
)

data class RegisterDeviceResponse(
    val id: Int,
    val imei: String? = null,
    @SerializedName("code_verrouillage") val codeVerrouillage: String? = null,
    /**
     * Code PIN, que le serveur nomme `code_pin`.
     *
     * On accepte aussi `code_ussd` : c'est le nom de la colonne en base, et il
     * a déjà été renvoyé par d'anciennes versions. Mantenir les deux évite de
     * laisser un champ à null selon la version du serveur déployée.
     */
    @SerializedName("code_pin") val codePin: String? = null,
    @SerializedName("code_ussd") val codeUssd: String? = null,
    /**
     * Secret d'appareil, renvoyé UNE SEULE FOIS à l'inscription.
     *
     * Il ouvre le canal de commande : sans lui, aucun topic ntfy ne peut être
     * calculé et aucune commande n'arrive. Il ne faut donc pas le perdre.
     */
    @SerializedName("device_token") val deviceToken: String? = null
) {
    /** Code PIN, quelle que soit la version du serveur qui a répondu. */
    val codePinEffectif: String?
        get() = codePin ?: codeUssd
}

data class LocationUpdateRequest(
    @SerializedName("appareil_id") val appareilId: Int,
    val latitude: Double,
    val longitude: Double,
    @SerializedName("precision_m") val precisionM: Float,
    val source: String = "gps"
)

data class AlerteItem(
    val id: Int,
    val type: String,
    val statut: String,
    val description: String? = null,
    @SerializedName("date_creation") val dateCreation: String? = null
)

data class SignalerAlerteRequest(
    @SerializedName("appareil_id") val appareilId: Int,
    @SerializedName("type_alerte") val typeAlerte: String,
    val description: String = "Signalé depuis l'application mobile"
)

data class FcmTokenRequest(
    @SerializedName("fcm_token") val fcmToken: String
)

data class VerifyCodeRequest(val code: String)

/**
 * Enveloppe de `/auth/me`.
 *
 * Le serveur répond `{"user": {...}}`, pas l'objet utilisateur nu : sans cette
 * classe, Gson chercherait un champ `id` à la racine, ne le trouverait pas et
 * renverrait un profil vide — l'écran afficherait « -- » sans qu'aucune erreur
 * ne soit visible.
 */
data class ProfileResponse(val user: UserData)

data class ApiError(val error: String)
