package com.antivol.mobile.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey

/**
 * Fournit la clé AES gardée par le Keystore Android, et rien d'autre.
 *
 * Volontairement minimal : toute la logique cryptographique est dans
 * [ValueCipher], testable sous JUnit, alors que `KeyStore` et
 * `KeyGenParameterSpec` ne sont joignables que depuis un `Context`.
 *
 * La clé n'est **pas** liée à l'authentification de l'utilisateur
 * (`setUserAuthenticationRequired` reste faux). Le téléphone doit pouvoir
 * re-verrouiller un appareil volé depuis un service d'arrière-plan, donc
 * sans écran déverrouillé et sans invite à chaque commande.
 */
class SecurePrefs(context: Context) {

    companion object {
        private const val ALIAS = "antivol_prefs_aes"
        private const val FOURNITEUR = "AndroidKeyStore"
        private const val TAILLE_CLE = 256
    }

    private val appContext = context.applicationContext

    /**
     * La clé du Keystore, ou `null` si elle est momentanément inaccessible.
     *
     * `null` n'est pas un cas théorique : le Keystore est invalidé quand
     * l'utilisateur change son code d'écran sur certains Android, et
     * l'application est verrouillée par le dannage sur d'autres
     * constructive. Les secrets deviennent alors définitivement illisibles,
     * et l'appareil doit être ré-enrôlé.
     */
    fun cle(): SecretKey? = try {
        val magasin = KeyStore.getInstance(FOURNITEUR).apply { load(null) }
        (magasin.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.secretKey
            ?: creerCle()
    } catch (e: Exception) {
        null
    }

    private fun creerCle(): SecretKey {
        val generateur = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, FOURNITEUR)
        generateur.init(
            KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(TAILLE_CLE)
                // GCM exige un IV unique par message : on laisse le
                // Keystore refuser toute réutilisation plutôt que de
                // dépendre de la discipline de ValueCipher.
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generateur.generateKey()
    }

    fun chiffrer(texte: String): String? = try {
        cle()?.let { ValueCipher.chiffrer(it, texte) }
    } catch (e: Exception) {
        null
    }

    fun lire(blob: String?): ValueCipher.Lecture = ValueCipher.lire(cle(), blob)

    /**
     * Efface la clé du Keystore.
     *
     * À n'appeler qu'après avoir constaté que les secrets sont illisibles :
     * toute donnée chiffrée avec cette clé devient définitivement indéchiffrable
     * et l'appareil doit être ré-enrôlé.
     */
    fun supprimerCle() {
        try {
            KeyStore.getInstance(FOURNITEUR).apply { load(null) }.deleteEntry(ALIAS)
        } catch (e: Exception) {
            // Rien à faire : la clé est déjà absente.
        }
    }
}
