package com.antivol.mobile.ui.profile

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.antivol.mobile.AntiVolApp
import com.antivol.mobile.ViewModelFactory
import com.antivol.mobile.data.model.UserData
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone

/**
 * Écran « Profil ».
 *
 * L'état est piloté par `ProfileViewModel` : cet écran ne touche plus ni aux
 * préférences ni au réseau. Voir ce ViewModel pour les deux bugs qu'il corrige
 * (mauvais fichier de préférences, client HTTP sans cookie de session).
 *
 * Trois états, tous atteignables et tous affichés : chargement, erreur,
 * profil. Aucun n'est simulé par du texte de remplacement — un champ vide se
 * dit « Non renseigné », ce qui distingue une donnée absente d'un écran cassé.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileScreen(onNavigateBack: () -> Unit) {
    val app = LocalContext.current.applicationContext as AntiVolApp
    val factory = remember { ViewModelFactory(app.preferencesManager) }
    val viewModel: ProfileViewModel = viewModel(factory = factory)
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Profil") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Retour")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            when {
                state.isLoading -> CircularProgressIndicator(
                    modifier = Modifier.align(Alignment.Center)
                )

                state.error != null -> ErreurProfil(
                    message = state.error!!,
                    onRetry = { viewModel.charger() },
                    modifier = Modifier.align(Alignment.Center)
                )

                else -> ContenuProfil(state.user!!)
            }
        }
    }
}

@Composable
private fun ContenuProfil(utilisateur: UserData) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(modifier = Modifier.height(16.dp))

        val initiales = listOf(utilisateur.prenom, utilisateur.nom)
            .mapNotNull { it.trim().firstOrNull()?.uppercaseChar() }
            .joinToString("")
            .ifEmpty { "?" }

        Box(
            modifier = Modifier
                .size(100.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.primary),
            contentAlignment = Alignment.Center
        ) {
            Text(
                initiales,
                style = MaterialTheme.typography.displayMedium,
                color = MaterialTheme.colorScheme.onPrimary,
                fontWeight = FontWeight.Bold
            )
        }

        Spacer(modifier = Modifier.height(16.dp))

        val nomComplet = listOf(utilisateur.prenom, utilisateur.nom)
            .filter { it.isNotBlank() }
            .joinToString(" ")
        Text(
            nomComplet.ifBlank { "Profil sans nom" },
            style = MaterialTheme.typography.headlineSmall,
            color = MaterialTheme.colorScheme.onBackground
        )
        Text(
            libelleRole(utilisateur.role),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.primary
        )

        Spacer(modifier = Modifier.height(32.dp))

        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant
            )
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                ProfileRow(
                    Icons.Default.Email,
                    "Email",
                    utilisateur.email.ifBlank { nonRenseigne() }
                )
                HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp))
                ProfileRow(
                    Icons.Default.Phone,
                    "Téléphone",
                    utilisateur.telephone?.takeIf { it.isNotBlank() } ?: nonRenseigne()
                )
                HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp))
                ProfileRow(
                    Icons.Default.CalendarMonth,
                    "Membre depuis",
                    formaterDate(utilisateur.dateCreation) ?: nonRenseigne()
                )
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Rappel utile : l'identité affichée ici vient du serveur, et c'est la
        // session qui fait foi. Aucun identifiant n'est stocké pour servir de
        // preuve locale.
        Text(
            "Votre identité est vérifiée par le serveur à chaque appel.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
private fun ErreurProfil(
    message: String,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(
            Icons.Default.CloudOff,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.error,
            modifier = Modifier.size(56.dp)
        )
        Spacer(modifier = Modifier.height(16.dp))
        Text(
            "Profil indisponible",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onBackground
        )
        Spacer(modifier = Modifier.height(8.dp))
        Text(
            message,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(modifier = Modifier.height(24.dp))
        Button(onClick = onRetry) {
            Icon(Icons.Default.Refresh, contentDescription = null)
            Spacer(modifier = Modifier.width(8.dp))
            Text("Réessayer")
        }
    }
}

@Composable
private fun ProfileRow(icon: ImageVector, label: String, value: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        Spacer(modifier = Modifier.width(12.dp))
        Column {
            Text(
                label,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                value,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurface
            )
        }
    }
}

private fun nonRenseigne(): String = "Non renseigné"

/** "admin" → "Administrateur", le reste → "Utilisateur". */
private fun libelleRole(role: String): String =
    if (role.equals("admin", ignoreCase = true)) "Administrateur" else "Utilisateur"

/**
 * Date d'inscription, en français, à partir d'un ISO 8601 serveur.
 *
 * Le serveur renvoie `2026-01-14T09:23:11+00:00` (ou avec `.ffffff`). Le motif
 * court d'avant ne gérait ni le fuseau ni les fractions de seconde : l'écran
 * retombait alors sur une troncature brute de la chaîne. On normalise donc
 * d'abord, puis on formate en `Locale.FRENCH` — la locale du téléphone
 * donnerait `01/14/2026` pour un utilisateur anglophone, ce qui est illisible
 * dans une interface française.
 */
private fun formaterDate(iso: String?): String? {
    if (iso.isNullOrBlank()) return null

    val patterns = listOf(
        "yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXX",
        "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
        "yyyy-MM-dd'T'HH:mm:ssXXX",
        "yyyy-MM-dd'T'HH:mm:ss'Z'"
    )
    for (pattern in patterns) {
        try {
            val lecture = SimpleDateFormat(pattern, Locale.US).apply {
                if (pattern.endsWith("'Z'")) timeZone = TimeZone.getTimeZone("UTC")
                isLenient = false
            }
            val date = lecture.parse(iso) ?: continue
            return SimpleDateFormat("d MMMM yyyy", Locale.FRENCH).format(date)
        } catch (_: Exception) {
            // Format non reconnu : on tente le suivant.
        }
    }
    // Dernier recours : les dix premiers caractères d'une date ISO sont déjà
    // « AAAA-MM-JJ », ce qui reste affichable même sans année UTC correctement
    // interprétée.
    return iso.take(10).ifBlank { null }
}
