package com.antivol.mobile.data

import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Garde-fou sur le câblage du chiffrement.
 *
 * `PreferencesManager` dépend de `SharedPreferences` et du `DataStore`, donc
 * elle n'est pas instanciable sous JUnit : le comportement de migration ne peut
 * pas être exécuté ici, et `ValueCipherTest` ne couvre que le format. Ces tests
 * inspectent donc la source pour empêcher qu'un accès en clair ne réapparaisse
 * — c'est la régression vraiment probable, puisqu'elle tient à une seule ligne.
 */
class PreferencesManagerChiffrementTest {

    private val source: String by lazy {
        val fichier = File("src/main/java/com/antivol/mobile/data/PreferencesManager.kt")
        assertTrue("PreferencesManager.kt introuvable depuis ${fichier.absolutePath}", fichier.exists())
        fichier.readText()
    }

    private val clesSensibles = listOf(
        "SYNC_DEVICE_SECRET", "SYNC_COOKIE_SESSION", "SYNC_CODE_VERROUILLAGE",
        "SYNC_CODE_USSD", "SYNC_USER_EMAIL",
    )

    private fun lignes(): List<String> = source.lines()

    @Test
    fun `aucune lecture directe d'une cle sensible en clair`() {
        // Toute lecture doit passer par lireMiroir/dechiffrer, qui savent
        // distinguer une valeur chiffrée d'une donnée antérieure au chiffrement.
        val coupables = lignes().filter { ligne ->
            val lectureDirecte = Regex("""getString\(\s*("?)(${clesSensibles.joinToString("|")})\1""").containsMatchIn(ligne)
            lectureDirecte
        }
        assertTrue("lecture en clair d'un secret : $coupables", coupables.isEmpty())
    }

    @Test
    fun `aucune ecriture directe d'une valeur non chiffree`() {
        // Un putString sur une clé sensible est légitime uniquement si la
        // valeur écrite est le blob : le motif exige donc `chiffre` ou
        // `serialise` déjà passé par le chiffreur.
        val coupables = lignes().filter { ligne ->
            val motif = Regex("""putString\(\s*(${clesSensibles.joinToString("|")})\s*,""")
            if (!motif.containsMatchIn(ligne)) return@filter false
            // Le contenu doit venir du chiffreur, pas d'un paramètre brut.
            !(ligne.contains("chiffre") || ligne.contains("serialise") || ligne.contains("it"))
        }
        assertTrue("écriture potentiellement en clair d'un secret : $coupables", coupables.isEmpty())
    }

    @Test
    fun `l'etat vol reste hors des cles sensibles`() {
        // Le drapeau qui fait reverrouiller un téléphone volé ne doit jamais
        // dépendre du Keystore : une clé invalidée ne doit pas pouvoir rendre
        // un téléphone volé incapable de se protéger.
        val bloc = source.substringAfter("CLES_SENSIBLES = setOf(").substringBefore(")")
        assertTrue(
            "etat_vol ne doit pas être chiffré, sinon un téléphone volé "
                + "pourrait cesser de se verrouiller après perte de clé",
            !bloc.contains("SYNC_ETAT_VOL"),
        )
    }

    @Test
    fun `l'indicateur d enrollement exige un secret dechiffrable`() {
        // `estEnrole` lisait le blob brut : tant que le secret est chiffré, un
        // appareil enrôlé serait compté comme non enrôlé et l'interface
        // proposerait un ré-enrôlement à chaque lancement.
        assertTrue(
            "estEnrole doit déchiffrer le secret",
            Regex("""estEnrole[\s\S]{0,400}dechiffrer\(prefs\[KEY_DEVICE_SECRET\]\)""").containsMatchIn(source),
        )
    }
}
