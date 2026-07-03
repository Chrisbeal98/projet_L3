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
    val imei: String,
    val modele: String,
    val marque: String,
    @SerializedName("user_id") val userId: Int
)

data class RegisterDeviceResponse(
    val id: Int,
    val imei: String? = null,
    @SerializedName("code_verrouillage") val codeVerrouillage: String? = null,
    @SerializedName("code_ussd") val codeUssd: String? = null
)

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
    @SerializedName("user_id") val userId: Int,
    @SerializedName("appareil_id") val appareilId: Int,
    @SerializedName("type_alerte") val typeAlerte: String,
    val description: String = "Signalé depuis l'application mobile"
)

data class ResolveAlerteRequest(
    @SerializedName("user_id") val userId: Int
)

data class VerifyCodeRequest(val code: String)

data class FcmTokenRequest(
    @SerializedName("user_id") val userId: Int,
    @SerializedName("fcm_token") val fcmToken: String
)

data class ApiError(val error: String)
