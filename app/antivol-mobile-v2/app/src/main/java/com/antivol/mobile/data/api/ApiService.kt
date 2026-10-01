package com.antivol.mobile.data.api

import com.antivol.mobile.data.model.*
import retrofit2.Response
import retrofit2.http.*

/**
 * Surface de l'API Flask.
 *
 * ─── Pourquoi presque aucune requête n'envoie d'identifiant ───
 *
 * Le client n'expose AUCUN `user_id`. Il y a longtemps, chaque appel portait
 * l'identifiant de l'utilisateur dans son corps JSON, et le serveur le croyait
 * sur parole : n'importe quelle application pouvait donc envoyer l'identifiant
 * d'une victime et agir en son nom — y compris verrouiller ses appareils.
 *
 * L'identité vient désormais de la seule session serveur, jointe
 * automatiquement par le cookie du `SessionCookieJar`, et le secret d'appareil
 * par l'en-tête `X-Device-Token` posé dans `RetrofitClient`. Aucun de ces deux
 * éléments n'apparaît donc dans les signatures ci-dessous : il est
 * structurellement impossible d'y mettre un `user_id`.
 *
 * Conséquence pratique : les points d'entrée qui n'attendent rien d'autre que
 * « qui suis-je » sont des `GET` sans corps, et non des `POST` mempilotés par
 * une clé étrangère locale. Le serveur accepte les deux formes ; la forme
 * sans corps dit exactement ce qu'elle fait.
 */
interface ApiService {

    @POST("auth/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @POST("auth/register")
    suspend fun register(@Body request: RegisterRequest): Response<RegisterResponse>

    @GET("auth/me")
    suspend fun getProfile(): Response<ProfileResponse>

    @GET("dashboard/stats")
    suspend fun getDashboardStats(): Response<StatsResponse>

    @POST("appareils/register")
    suspend fun registerDevice(@Body request: RegisterDeviceRequest): Response<RegisterDeviceResponse>

    @GET("appareils/{id}/statut")
    suspend fun getDeviceStatus(@Path("id") appareilId: Int): Response<DeviceStatusResponse>

    @POST("appareils/{id}/verifier-code")
    suspend fun verifyCode(@Path("id") appareilId: Int, @Body request: VerifyCodeRequest): Response<Unit>

    @POST("localisation/update")
    suspend fun updateLocation(@Body request: LocationUpdateRequest): Response<Unit>

    @GET("alertes")
    suspend fun getAlertes(): Response<List<AlerteItem>>

    @POST("alertes/signaler")
    suspend fun signalerAlerte(@Body request: SignalerAlerteRequest): Response<Unit>

    @POST("alertes/{id}/resoudre")
    suspend fun resoudreAlerte(@Path("id") alerteId: Int): Response<Unit>

    @POST("fcm/register-token")
    suspend fun registerFcmToken(@Body request: FcmTokenRequest): Response<Unit>
}
