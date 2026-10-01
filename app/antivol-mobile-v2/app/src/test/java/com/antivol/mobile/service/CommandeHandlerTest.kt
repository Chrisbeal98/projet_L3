package com.antivol.mobile.service

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Normalisation des commandes reçues du serveur.
 *
 * Le serveur envoie la commande dans deux clés : `action` (canonique, en
 * minuscule) et `command` (historique, en majuscules, avec plusieurs alias).
 * Le client doit reconnaître les deux, refuser ce qu'il ne connaît pas, et —
 * surtout — ne jamais exécuter une commande destinée à un autre téléphone.
 */
class CommandeHandlerTest {

    @Test
    fun `les alias de verrouillage sont reconnus`() {
        for (alias in listOf("LOCK", "VERROUILLER", "VOL", "PERTE", "lock", "verrouiller")) {
            assertEquals(
                "alias non reconnu : $alias",
                CommandeHandler.ACTION_LOCK,
                CommandeHandler.normaliser(alias, null)
            )
        }
    }

    @Test
    fun `les alias de deverrouillage sont reconnus`() {
        for (alias in listOf("UNLOCK", "DEVERROUILLER", "unlock", "deverrouiller")) {
            assertEquals(
                "alias non reconnu : $alias",
                CommandeHandler.ACTION_UNLOCK,
                CommandeHandler.normaliser(alias, null)
            )
        }
    }

    @Test
    fun `les alias de localisation sont reconnus`() {
        // FR-CMD-05
        for (alias in listOf("LOCATE", "LOCALISER", "locate", "localiser")) {
            assertEquals(
                "alias non reconnu : $alias",
                CommandeHandler.ACTION_LOCATE,
                CommandeHandler.normaliser(alias, null)
            )
        }
    }

    @Test
    fun `une alerte communautaire ne devient jamais un verrouillage`() {
        // Une alerte communautaire porte `command = ALERT`. Si elle était
        // interprétée comme un ordre, n'importe qui pourrait faire verrouiller
        // le téléphone d'inconnus en déclarant un faux vol.
        assertEquals(
            CommandeHandler.ACTION_ALERT,
            CommandeHandler.normaliser(null, "COMMUNITY_ALERT")
        )
        assertEquals(
            CommandeHandler.ACTION_ALERT,
            CommandeHandler.normaliser(null, "ALERTE")
        )
    }

    @Test
    fun `une commande inconnue est ignoree silencieusement`() {
        // Le client ne doit jamais planter sur une commande qu'il ne connaît
        // pas : le serveur peut être en avance, ou un attaquant peut forger.
        assertNull(CommandeHandler.normaliser(null, "EFFACER"))
        assertNull(CommandeHandler.normaliser(null, "WIPE"))
        assertNull(CommandeHandler.normaliser(null, ""))
        assertNull(CommandeHandler.normaliser(null, null))
    }

    @Test
    fun `la cle action prime sur la cle command`() {
        // Le serveur envoie les deux ; `action` est la valeur canonique.
        assertEquals(
            CommandeHandler.ACTION_LOCATE,
            CommandeHandler.normaliser("locate", "LOCK")
        )
    }

    @Test
    fun `les espaces autour de la commande sont ignores`() {
        assertEquals(
            CommandeHandler.ACTION_LOCK,
            CommandeHandler.normaliser(null, "  LOCK  ")
        )
    }

    @Test
    fun `une commande sans appareil cible s applique`() {
        // Absence d'`appareil_id` : commande générale, on l'exécute.
        assertEquals(true, CommandeHandler.estPourCetAppareil(null, 7))
    }

    @Test
    fun `une commande visant un autre appareil est refusee`() {
        // Règle de sécurité non négociable : une commande destinée au
        // téléphone 3 ne doit jamais être exécutée par le téléphone 5.
        assertEquals(false, CommandeHandler.estPourCetAppareil("3", 5))
        assertEquals(true, CommandeHandler.estPourCetAppareil("5", 5))
    }

    @Test
    fun `un appareil cible de zero vaut absence`() {
        // 0 est la valeur par défaut d'un client qui n'a pas encore
        // d'identifiant : la commande ne lui est pas destinée, mais il ne doit
        // pas non plus se verrouiller lui-même par accident.
        assertEquals(true, CommandeHandler.estPourCetAppareil("0", 5))
    }

    @Test
    fun `un appareil non enregistre refuse toute commande ciblee`() {
        // monAppareilId == -1 : le client ignore encore son propre
        // identifiant. Il ne peut pas savoir si la commande le vise, donc il
        // ne l'exécute pas.
        assertEquals(false, CommandeHandler.estPourCetAppareil("3", -1))
    }
}
