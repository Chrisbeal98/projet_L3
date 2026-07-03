package com.antivol.mobile.ui.alerts

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.antivol.mobile.ViewModelFactory
import com.antivol.mobile.AntiVolApp
import androidx.compose.runtime.remember
import com.antivol.mobile.data.model.AlerteItem

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AlertesScreen(
    onNavigateBack: () -> Unit
) {
    val app = LocalContext.current.applicationContext as AntiVolApp
    val factory = remember { ViewModelFactory(app.preferencesManager) }
    val viewModel: AlertsViewModel = viewModel(factory = factory)
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current

    LaunchedEffect(Unit) {
        viewModel.loadAlertes()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Alertes") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Retour")
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.showReportDialog(context) }) {
                        Icon(Icons.Default.Add, contentDescription = "Signaler")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
        ) {
            // Stats
            Row(modifier = Modifier.fillMaxWidth()) {
                StatChip("En cours", state.enCours.toString(), MaterialTheme.colorScheme.error, Modifier.weight(1f))
                Spacer(modifier = Modifier.width(8.dp))
                StatChip("Résolues", state.resolues.toString(), MaterialTheme.colorScheme.primary, Modifier.weight(1f))
                Spacer(modifier = Modifier.width(8.dp))
                StatChip("Total", state.alertes.size.toString(), MaterialTheme.colorScheme.onSurfaceVariant, Modifier.weight(1f))
            }

            Spacer(modifier = Modifier.height(16.dp))

            if (state.alertes.isEmpty()) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Text("Aucune alerte", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else {
                LazyColumn {
                    items(state.alertes) { alerte ->
                        AlerteCard(alerte, onResolve = { viewModel.resoudreAlerte(alerte.id) })
                        Spacer(modifier = Modifier.height(8.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun StatChip(label: String, value: String, color: androidx.compose.ui.graphics.Color, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(value, style = MaterialTheme.typography.titleLarge, color = color, fontWeight = FontWeight.Bold)
            Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun AlerteCard(alerte: AlerteItem, onResolve: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val icon = when (alerte.type) {
                    "vol" -> "🚨"
                    "perte" -> "🔍"
                    else -> "⚠️"
                }
                Text(icon, fontSize = 20.sp)
                Spacer(modifier = Modifier.width(8.dp))
                Text(alerte.type.uppercase(), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.weight(1f))
                Text(
                    if (alerte.statut == "en_cours") "En cours" else "Résolue",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (alerte.statut == "en_cours") MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.primary
                )
            }
            Spacer(modifier = Modifier.height(4.dp))
            Text(alerte.description ?: "Aucune description", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)

            if (alerte.statut == "en_cours") {
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedButton(onClick = onResolve, modifier = Modifier.fillMaxWidth()) {
                    Text("Résoudre")
                }
            }
        }
    }
}
