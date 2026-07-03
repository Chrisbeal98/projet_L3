package com.antivol.mobile.data.api

import com.antivol.mobile.data.model.*
import retrofit2.Response
import retrofit2.http.*

interface ApiService {

    @POST("auth/login")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    @POST("auth/register")
    suspend fun register(@Body request: RegisterRequest): Response<RegisterResponse>

    @POST("auth/me")
    suspend fun getProfile(@Body body: Map<String, Int>): Response<Map<String, UserData>>

    @POST("dashboard/stats")
    suspend fun getDashboardStats(@Body body: Map<String, Int>): Response<StatsResponse>

    @POST("appareils/register")
    suspend fun registerDevice(@Body request: RegisterDeviceRequest): Response<RegisterDeviceResponse>

    @GET("appareils/{id}/statut")
    suspend fun getDeviceStatus(@Path("id") appareilId: Int): Response<DeviceStatusResponse>

    @POST("appareils/{id}/verifier-code")
    suspend fun verifyCode(@Path("id") appareilId: Int, @Body request: VerifyCodeRequest): Response<Unit>

    @POST("localisation/update")
    suspend fun updateLocation(@Body request: LocationUpdateRequest): Response<Unit>

    @POST("alertes")
    suspend fun getAlertes(@Body body: Map<String, Int>): Response<List<AlerteItem>>

    @POST("alertes/signaler")
    suspend fun signalerAlerte(@Body request: SignalerAlerteRequest): Response<Unit>

    @POST("alertes/{id}/resoudre")
    suspend fun resoudreAlerte(@Path("id") alerteId: Int, @Body body: ResolveAlerteRequest): Response<Unit>

    @POST("fcm/register-token")
    suspend fun registerFcmToken(@Body request: FcmTokenRequest): Response<Unit>
}
