package com.antivol.mobile.data

import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Chiffrement AES-GCM des valeurs sensibles, sans dépendance au Keystore.
 *
 * Le Keystore Android n'est joignable que depuis un `Context`, donc impossible
 * à instancier sous JUnit : tout ce qui est vérifiable est factorisé ici, et
 * [SecurePrefs] se contente de fournir la clé. Les tests de `ValueCipherTest`
 * couvrent donc réellement le format, la détection d'altération et le cas de
 * la clé perdue, et non un substitut.
 *
 * Encodage hexadécimal et non Base64 : `android.util.Base64` n'existe pas sous
 * JUnit, et `java.util.Base64` exige l'API 26 alors que l'application vise 23.
 * L'hexadécimal n'utilise que `0-9a-f`, donc la valeur encodée ne peut jamais
 * contenir le `:` du marqueur, et il se code en trois lignes vérifiables à
 * l'œil.
 *
 * Format stocké : `AV1:` puis, en hexadécimal, la taille de l'IV sur un octet,
 * l'IV, puis le texte chiffré. Le préfixe rend la valeur auto-identifiante, ce
 * qui est ce qui permet de migrer les données déjà en clair.
 */
object ValueCipher {

    private const val MARQUEUR = "AV1:"
    private const val TRANSFORMATION = "AES/GCM/NoPadding"
    private const val TAILLE_IV = 12
    private const val TAILLE_TAG = 128
    private const val HEX = "0123456789abcdef"

    /** Résultat d'une lecture, pour que l'appelant décide au lieu de supposer. */
    sealed interface Lecture {
        /** Valeur chiffrée déchiffrée. */
        data class Chiffree(val texte: String) : Lecture

        /**
         * Valeur écrite avant la mise en place du chiffrement, jamais chiffrée.
         * L'appelant doit la réécrire chiffrée au passage.
         */
        data class ClairLegacy(val texte: String) : Lecture

        /**
         * Chiffré mais illisible : clé Keystore perdue, ou contenu altéré.
         * Traité en échec partout, jamais comme une valeur vide, pour que
         * l'appelant demande un ré-enrôlement au lieu de croire l'appareil
         * encore enrôlé.
         */
        object Illisible : Lecture
    }

    /**
     * Cette chaîne est-elle un blob produit par [chiffrer] ?
     *
     * Le suffixe doit être de l'hexadécimal de longueur paire : c'est ce qui
     * distingue un vrai blob d'une donnée existante qui contiendrait par
     * hasard la chaîne `AV1:`.
     */
    fun estChiffre(blob: String): Boolean {
        if (!blob.startsWith(MARQUEUR)) return false
        val corps = blob.substring(MARQUEUR.length)
        if (corps.isEmpty() || corps.length % 2 != 0) return false
        return corps.all { it in '0'..'9' || it in 'a'..'f' }
    }

    fun chiffrer(cle: SecretKey, texte: String): String {
        val iv = ByteArray(TAILLE_IV).also { SecureRandom().nextBytes(it) }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, cle, GCMParameterSpec(TAILLE_TAG, iv))
        // Un IV neuf à chaque écriture est indispensable : en GCM, réutiliser un
        // IV sous la même clé rend le clair récupérable par XOR de deux
        // messages, et l'authentification de GCM n'en protège pas.
        val chiffre = cipher.doFinal(texte.toByteArray(Charsets.UTF_8))

        val brut = ByteArray(1 + iv.size + chiffre.size)
        brut[0] = iv.size.toByte()
        System.arraycopy(iv, 0, brut, 1, iv.size)
        System.arraycopy(chiffre, 0, brut, 1 + iv.size, chiffre.size)

        return MARQUEUR + versHex(brut)
    }

    fun lire(cle: SecretKey?, blob: String?): Lecture {
        if (blob == null || blob.isEmpty()) return Lecture.ClairLegacy("")
        if (!estChiffre(blob)) return Lecture.ClairLegacy(blob)
        // Un blob marqué « chiffré » sans clé ne peut pas être lu : c'est le
        // cas Keystore invalidé. Renvoyer le blob lui-même le ferait passer
        // pour un secret et serait envoyé au serveur.
        if (cle == null) return Lecture.Illisible

        return try {
            val brut = depuisHex(blob.substring(MARQUEUR.length))
            val tailleIv = brut[0].toInt() and 0xFF
            if (tailleIv <= 0 || tailleIv > brut.size - 1) return Lecture.Illisible
            val iv = brut.copyOfRange(1, 1 + tailleIv)
            val chiffre = brut.copyOfRange(1 + tailleIv, brut.size)

            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, cle, GCMParameterSpec(TAILLE_TAG, iv))
            // doFinal vérifie le tag : un octet modifié lève
            // AEADBadTagException et la valeur est rejetée, au lieu d'être
            // rendue à l'UI comme si elle était fiable.
            Lecture.Chiffree(String(cipher.doFinal(chiffre), Charsets.UTF_8))
        } catch (e: Exception) {
            // AEADBadTagException (altération), InvalidKeyException (clé
            // perdue), valeur tronquée ou de taille d'IV incohérente : tous
            // doivent finir en Illisible, pas en texte partiel ni en exception
            // qui tue le service de surveillance.
            Lecture.Illisible
        }
    }

    private fun versHex(octets: ByteArray): String {
        val sortie = StringBuilder(octets.size * 2)
        for (octet in octets) {
            val v = octet.toInt() and 0xFF
            sortie.append(HEX[v ushr 4]).append(HEX[v and 0x0F])
        }
        return sortie.toString()
    }

    private fun depuisHex(texte: String): ByteArray {
        val sortie = ByteArray(texte.length / 2)
        for (i in sortie.indices) {
            // La position se lit dans l'alphabet, pas dans la chaîne décodée :
            // chercher 'a' dans « 0a » ne donnerait pas 10.
            val haut = HEX.indexOf(texte[i * 2])
            val bas = HEX.indexOf(texte[i * 2 + 1])
            sortie[i] = ((haut shl 4) or bas).toByte()
        }
        return sortie
    }
}
