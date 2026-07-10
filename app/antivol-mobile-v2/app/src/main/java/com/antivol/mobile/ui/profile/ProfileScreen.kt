package com.antivol.mobile.ui.profile

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(onNavigateBack: () -> Unit) {
    val context = LocalContext.current

    var nom by remember { mutableStateOf("") }
    var prenom by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var telephone by remember { mutableStateOf("--") }
    var role by remember { mutableStateOf("utilisateur") }
    var dateCreation by remember { mutableStateOf("--") }
    var isLoading by remember { mutableStateOf(true) }

    LaunchedEffect(Unit) {
        try {
            val prefs = context.getSharedPreferences("antivol_prefs", Context.MODE_PRIVATE)
            val apiUrl = prefs.getString("api_url", "https://antivol.onrender.com/api") ?: ""
            val userId = prefs.getInt("user_id", -1)
            if (userId == -1) return@LaunchedEffect

            val json = JSONObject().put("user_id", userId)
            val body = json.toString().toRequestBody("application/json; charset=utf-8".toMediaType())

            val (success, data) = withContext(Dispatchers.IO) {
                val client = OkHttpClient()
                val request = Request.Builder().url("$apiUrl/auth/me").post(body).build()
                val response = client.newCall(request).execute()
                val bodyStr = response.body?.string() ?: ""
                Pair(response.isSuccessful, bodyStr)
            }

            if (success) {
                val user = JSONObject(data).getJSONObject("user")
                nom = user.optString("nom", "")
                prenom = user.optString("prenom", "")
                email = user.optString("email", "")
                telephone = user.optString("telephone", "--")
                role = user.optString("role", "utilisateur")
                val dateStr = user.optString("date_creation", "")
                if (dateStr.isNotEmpty()) {
                    try {
                        val iso = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.getDefault())
                        val out = SimpleDateFormat("dd/MM/yyyy", Locale.getDefault())
                        dateCreation = out.format(iso.parse(dateStr)!!)
                    } catch (_: Exception) {
                        dateCreation = dateStr.take(10)
                    }
                }
            }
        } catch (_: Exception) {}
        isLoading = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Profil") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Retour")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
            )
        }
    ) { padding ->
        if (isLoading) {
            Box(modifier = Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Spacer(modifier = Modifier.height(32.dp))

                // Avatar
                val initials = "${prenom.firstOrNull() ?: ""}${nom.firstOrNull() ?: ""}"
                Box(
                    modifier = Modifier
                        .size(100.dp)
                        .clip(CircleShape)
                        .background(MaterialTheme.colorScheme.primary),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        initials.ifEmpty { "?" }.uppercase(),
                        style = MaterialTheme.typography.displayMedium,
                        color = MaterialTheme.colorScheme.onPrimary,
                        fontWeight = FontWeight.Bold
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))

                Text("$prenom $nom", style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.onBackground)
                Text(
                    role.replaceFirstChar { it.uppercase() },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                Spacer(modifier = Modifier.height(32.dp))

                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        ProfileRow(Icons.Default.Email, "Email", email)
                        HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp))
                        ProfileRow(Icons.Default.Phone, "Téléphone", telephone)
                        HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp))
                        ProfileRow(Icons.Default.CalendarMonth, "Membre depuis", dateCreation)
                    }
                }
            }
        }
    }
}

@Composable
private fun ProfileRow(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, value: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        Spacer(modifier = Modifier.width(12.dp))
        Column {
            Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurface)
        }
    }
}
