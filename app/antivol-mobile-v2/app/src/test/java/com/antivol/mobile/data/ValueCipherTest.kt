package com.antivol.mobile.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.SecureRandom
import javax.crypto.AEADBadTagException
import javax.crypto.KeyGenerator

/**
 * Couvre le format de [ValueCipher] sur une clé JVM ordinaire.
 *
 * Ces tests sont protectors : sans eux, une régression de format laisserait
 * l'application lire des octets arbitraires comme du texte, ou perdreait le
 * secret d'appareil sans le dire.
 */
class ValueCipherTest {

    private fun cle(): javax.crypto.SecretKey =
        KeyGenerator.getInstance("AES").apply { init(256) }.generateKey()

    @Test
    fun `un texte chiffre puis dechiffre retrouve la valeur`() {
        val c = cle()
        for (texte in listOf("", "simple", "motdepasse-9f3a", "sécret-ünïcode-🔒", "a".repeat(5000))) {
            val blob = ValueCipher.chiffrer(c, texte)
            val lu = ValueCipher.lire(c, blob)
            assertTrue(lu is ValueCipher.Lecture.Chiffree)
            assertEquals(texte, (lu as ValueCipher.Lecture.Chiffree).texte)
        }
    }

    @Test
    fun `le texte chiffre ne contient pas le secret en clair`() {
        val c = cle()
        val blob = ValueCipher.chiffrer(c, "secret-appareil-tres-long-et-unique")
        assertFalse(blob.contains("secret-appareil"))
        assertTrue(ValueCipher.estChiffre(blob))
    }

    @Test
    fun `deux chiffrement du meme texte donnent des blobs differents`() {
        val c = cle()
        // GCM est probabiliste : deux IV distincts, donc deux blobs distincts
        // pour un même contenu. Des blobs identiques trahiraient une réutilisation
        // d'IV, qui en GCM permet de récupérer le texte clair.
        val a = ValueCipher.chiffrer(c, "appareil_secret")
        val b = ValueCipher.chiffrer(c, "appareil_secret")
        assertFalse(a == b)
    }

    @Test
    fun `un blob altere est rejete et non rendu partiellement`() {
        val c = cle()
        val blob = ValueCipher.chiffrer(c, "code-verrouillage-4417")
        // On retourne le dernier caractère hexadécimal, qui touche au ciphertext
        // ou au tag. Il faut rester dans l'alphabet minuscule, sinon `estChiffre`
        // refuserait d'abord le blob et l'altération ne serait pas testée.
        val dernier = blob.last()
        val remplacement = if (dernier == '0') '1' else '0'
        val altere = blob.dropLast(1) + remplacement
        val lu = ValueCipher.lire(c, altere)
        assertTrue("un blob altéré ne doit jamais être décodé", lu is ValueCipher.Lecture.Illisible)
    }

    @Test
    fun `un contenu non hexadecimal apres le prefixe est traite comme du legacy`() {
        // Cas de migration : une donnée existante contenant la chaîne « AV1: »
        // ne doit pas être prise pour un blob chiffré. Le contrôle de l'hexadécimal
        // est ce qui évite de tenter un déchiffrement sur du texte arbitraire.
        assertFalse(ValueCipher.estChiffre("AV1:ceci-n-est-pas-un-blob"))
        assertTrue(ValueCipher.lire(cle(), "AV1:ceci-n-est-pas-un-blob") is ValueCipher.Lecture.ClairLegacy)
    }

    @Test
    fun `un hexadecimal de longueur impaire est traite comme du legacy`() {
        assertFalse(ValueCipher.estChiffre("AV1:abc"))
    }

    @Test
    fun `un blob hexadecimal corrompu est illisible`() {
        // Structure valide pour l'enveloppe, contenu faux : le déchiffrement
        // doit échouer proprement, sans rendre les octets lus comme du texte.
        val faux = "AV1:" + "0c".repeat(20)
        assertTrue(ValueCipher.estChiffre(faux))
        assertEquals(ValueCipher.Lecture.Illisible, ValueCipher.lire(cle(), faux))
    }

    @Test
    fun `une cle differente ne dechiffre pas`() {
        val blob = ValueCipher.chiffrer(cle(), "secret")
        val lu = ValueCipher.lire(cle(), blob)
        assertTrue(lu is ValueCipher.Lecture.Illisible)
    }

    @Test
    fun `une cle perdue rend le blob illisible et jamais du clair`() {
        val blob = ValueCipher.chiffrer(cle(), "appareil_secret")
        val lu = ValueCipher.lire(null, blob)
        // C'est le cas Keystore invalidé : rendre le blob lui-même ferait croire
        // à l'UI que l'appareil est encore enrôlé.
        assertEquals(ValueCipher.Lecture.Illisible, lu)
    }

    @Test
    fun `une valeur legacy en clair est signalee comme telle pour migrer`() {
        val lu = ValueCipher.lire(cle(), "ancien-secret-en-clair")
        assertTrue(lu is ValueCipher.Lecture.ClairLegacy)
        assertEquals("ancien-secret-en-clair", (lu as ValueCipher.Lecture.ClairLegacy).texte)
    }

    @Test
    fun `une valeur absente est vide et exploitable`() {
        for (vide in listOf(null, "")) {
            val lu = ValueCipher.lire(cle(), vide)
            assertTrue(lu is ValueCipher.Lecture.ClairLegacy)
            assertEquals("", (lu as ValueCipher.Lecture.ClairLegacy).texte)
        }
    }

    @Test
    fun `le blob survit a un aller-retour par octets`() {
        // Ce qui est écrit est ce qui est relu après passage par le disque,
        // encodage compris.
        val c = cle()
        val secret = "cookie_session=session=abc123; Path=/"
        val blob = ValueCipher.chiffrer(c, secret)
        val relu = ValueCipher.lire(c, blob) as ValueCipher.Lecture.Chiffree
        assertEquals(secret, relu.texte)
    }

    @Test
    fun `une taille iv aberrante est rejetee`() {
        // Un blob forgé annonce un IV plus grand que les données disponibles :
        // il ne doit pas provoquer de crash sur une copie d'array.
        val forge = "AV1:" + "ff".repeat(20)
        assertEquals(ValueCipher.Lecture.Illisible, ValueCipher.lire(cle(), forge))
    }
}
