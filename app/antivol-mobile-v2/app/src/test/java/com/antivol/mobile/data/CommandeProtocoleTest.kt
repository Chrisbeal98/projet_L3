package com.antivol.mobile.data

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Vérifie que l'implémentation Kotlin du protocole de commande produit
 * exactement les mêmes résultats que `app/commandes.py` côté serveur.
 *
 * Les vecteurs viennent de `app/src/test/resources/commande_vecteur.json`,
 * généré par le Python. Si les deux implémentations divergent — une fuite
 * d'échappement, un tri de clés différent — ces tests échouent au lieu que
 * le blocage ne se découvre qu'en production, sur un téléphone qui refuse
 * tous les ordres.
 */
class CommandeProtocoleTest {

    private fun vecteurs(): JSONObject {
        val ressource = javaClass.classLoader!!.getResourceAsStream("commande_vecteur.json")
            ?: error("commande_vecteur.json absent des ressources de test")
        val brut = ressource.readBytes().toString(Charsets.UTF_8)
        ressource.close()
        return JSONObject(brut)
    }

    private fun cas(): List<JSONObject> {
        val tableau = vecteurs().getJSONArray("cas")
        return (0 until tableau.length()).map { tableau.getJSONObject(it) }
    }

    @Test
    fun `le topic est bien derive du secret`() {
        for (c in cas()) {
            val secret = c.getString("secret")
            assertEquals(c.getString("topic"), CommandeProtocole.topicPourSecret(secret))
        }
    }

    @Test
    fun `un topic ne depend pas du numero d utilisateur`() {
        val topic = CommandeProtocole.topicPourSecret("secret-de-telephone-1")!!
        assertTrue(topic, topic.startsWith("antivol-a"))
        assertFalse("le topic ne doit pas exposer l'identifiant", topic.contains("u1"))
    }

    @Test
    fun `un secret absent ne donne aucun topic`() {
        assertEquals(null, CommandeProtocole.topicPourSecret(null))
        assertEquals(null, CommandeProtocole.topicPourSecret(""))
    }

    @Test
    fun `les messages du serveur sont acceptes`() {
        for (c in cas()) {
            val message = c.getJSONObject("message")
            // On se place à l'instant exact du vecteur pour que la fenêtre
            // d'horloge ne soit pas ce qui est testé ici.
            val maintenant = c.getLong("ts")
            assertTrue(
                "vecteur « ${c.getString("nom")} » rejeté à tort",
                CommandeProtocole.verifierSignature(c.getString("secret"), message, maintenant)
            )
        }
    }

    @Test
    fun `un message hors tolerance d horloge est rejete`() {
        val c = cas().first()
        val message = c.getJSONObject("message")
        val tolerance = vecteurs().getLong("tolerance_horloge_s")
        assertFalse(
            CommandeProtocole.verifierSignature(
                c.getString("secret"), message, c.getLong("ts") + tolerance + 1
            )
        )
        assertFalse(
            CommandeProtocole.verifierSignature(
                c.getString("secret"), message, c.getLong("ts") - tolerance - 1
            )
        )
    }

    @Test
    fun `une signature alteree est rejetee`() {
        val c = cas().first()
        val message = c.getJSONObject("message")
        val truque = JSONObject(message.toString())
        truque.put("command", "UNLOCK")
        assertFalse(CommandeProtocole.verifierSignature(c.getString("secret"), truque, c.getLong("ts")))
    }

    @Test
    fun `un message signe par un autre secret est rejete`() {
        val c = cas().first()
        assertFalse(
            CommandeProtocole.verifierSignature(
                "secret-dun-autre-telephone", c.getJSONObject("message"), c.getLong("ts")
            )
        )
    }

    @Test
    fun `un message sans signature est rejete`() {
        val c = cas().first()
        val nu = JSONObject(c.getJSONObject("message").toString())
        nu.remove("sig")
        assertFalse(CommandeProtocole.verifierSignature(c.getString("secret"), nu, c.getLong("ts")))
    }

    @Test
    fun `un message sans horodatage est rejete`() {
        val c = cas().first()
        val nu = JSONObject(c.getJSONObject("message").toString())
        nu.remove("ts")
        assertFalse(CommandeProtocole.verifierSignature(c.getString("secret"), nu, c.getLong("ts")))
    }

    @Test
    fun `un message qui contient un type inattendu est rejete`() {
        // Le protocole n'a jamais prévu de flottant : mieux vaut refuser que
        // calculer une signature qui ne correspondra pas à celle du serveur.
        val c = cas().first()
        val bizarre = JSONObject(c.getJSONObject("message").toString())
        bizarre.put("latitude", 5.36)
        assertFalse(CommandeProtocole.verifierSignature(c.getString("secret"), bizarre, c.getLong("ts")))
    }
}
