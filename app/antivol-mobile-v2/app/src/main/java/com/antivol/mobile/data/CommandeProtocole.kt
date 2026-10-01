package com.antivol.mobile.data

import org.json.JSONObject
import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Protocole du canal de commande (ntfy).
 *
 * Ce fichier est le pendant Android exact de `app/commandes.py`. Les deux
 * implémentations doivent produire les mêmes octets : si elles divergent, le
 * téléphone rejette les messages légitimes. Tout écart doit être corrigé
 * ici ET dans le Python, jamais dans un seul des deux.
 *
 * ─── Ce que cela protège contre ───
 *
 * Avant, le topic ntfy valait `antivol-u<numéro d'utilisateur>` et n'était
 * signé par personne. ntfy.sh étant un service public, cela laissait deux
 * attaques ouvertes :
 *
 *  1. INJECTION : publier `{"topic":"antivol-u5","command":"LOCK"}` faisait
 *     verrouiller le téléphone d'une victime, sans connaître son compte.
 *  2. INTERCEPTION : s'abonner à `antivol-u1` suffisait à recevoir la
 *     position et les alertes de cette personne.
 *
 * Ici, le topic est dérivé du secret du téléphone (non devinable) et chaque
 * message est signé (HMAC-SHA-256). Un topic découvert ne permet plus de
 * forger un ordre : le message est rejeté.
 *
 * ─── Limite assumée ───
 *
 * Sans compte ntfy, on ne peut pas poser de jeton d'accès : un topic reste
 * techniquement lisible par quiconque le devine. La protection repose donc
 * sur le secret (aléa de 256 bits), pas sur une autorisation du service. Sur
 * un serveur ntfy auto-hébergé, ajouter `Authorization: Bearer <token>`.
 */
object CommandeProtocole {

    private const val VERSION_SIGNATURE = "v1"

    /** Tolérance d'horloge, en secondes, comme dans `app/commandes.py`. */
    private const val TOLERANCE_HORLOGE_S = 300L

    private const val PREFIXE_TOPIC = "antivol-a"
    private const val LONGUEUR_EMPREINTE_TOPIC = 32

    /**
     * Topic ntfy correspondant au secret de ce téléphone.
     *
     * Recalculé à chaque démarrage : le téléphone n'a besoin de connaître que
     * son propre secret, jamais que le serveur lui rappelle son topic.
     */
    fun topicPourSecret(secret: String?): String? {
        if (secret.isNullOrEmpty()) return null
        val empreinte = sha256Hex("antivol-topic:$secret")
        return PREFIXE_TOPIC + empreinte.substring(0, LONGUEUR_EMPREINTE_TOPIC)
    }

    /**
     * Vérifie la signature d'un message avant de lui obéir.
     *
     * @return true si le message provient bien du serveur pour CE téléphone.
     */
    fun verifierSignature(secret: String?, data: JSONObject?, maintenant: Long = System.currentTimeMillis() / 1000): Boolean {
        if (secret.isNullOrEmpty() || data == null) return false

        val signatureRecue = data.optString("sig", "")
        val horodatage = data.optLong("ts", -1L)
        if (signatureRecue.isEmpty() || horodatage < 0) return false

        // Fenêtre d'horloge : rejette un ordre ancien rejoué plus tard, par
        // exemple un « verrouille » émis avant la revente du téléphone.
        if (kotlin.math.abs(maintenant - horodatage) > TOLERANCE_HORLOGE_S) return false

        // La signature porte sur le message SANS `sig`, plus la version et
        // l'horodatage, dans un ordre de clés déterministe.
        val aSigner = JSONObject()
        val cles = data.keys()
        while (cles.hasNext()) {
            val cle = cles.next()
            if (cle == "sig") continue
            aSigner.put(cle, data.get(cle))
        }
        aSigner.put("v", data.optString("v", VERSION_SIGNATURE))
        aSigner.put("ts", horodatage)

        val canonique = canonicaliser(aSigner) ?: return false
        val attendu = hmacHex(secret, canonique)
        // Comparaison à temps constant : évite de fuir le préfixe correct par
        // mesure du temps de réponse.
        return constantTimeEquals(attendu, signatureRecue)
    }

    /**
     * Sérialisation canonique : clés triées par point de code Unicode,
     * séparateurs `,` et `:`, aucun caractère échappé en ASCII.
     *
     * Doit reproduire exactement `json.dumps(..., sort_keys=True,
     * separators=(',', ':'), ensure_ascii=False)`.
     *
     * Retourne null si le message contient un type que le protocole n'a jamais
     * prévu (un flottant, un objet imbriqué) : on rejute alors le message
     * plutôt que de risquer de valider une signature calculée différemment
     * du serveur.
     */
    private fun canonicaliser(json: JSONObject): ByteArray? {
        val cles = mutableListOf<String>()
        val iterateur = json.keys()
        while (iterateur.hasNext()) cles.add(iterateur.next())
        cles.sort()

        val builder = StringBuilder("{")
        var premier = true
        for (cle in cles) {
            val valeur = valeurJson(json.get(cle)) ?: return null
            if (!premier) builder.append(",")
            premier = false
            builder.append(quoteJson(cle))
            builder.append(":")
            builder.append(valeur)
        }
        builder.append("}")
        return builder.toString().toByteArray(Charsets.UTF_8)
    }

    /**
     * Échappement JSON compatible avec `json.dumps(ensure_ascii=False)`.
     *
     * Python utilise des raccourcis (`\t`, `\n`, ...) et `\u00xx` seulement
     * pour les autres caractères de contrôle. Produire `\u0009` là où Python
     * produit `\t` changerait la chaîne signée et ferait rejeter tous les
     * messages légitimes.
     */
    private fun quoteJson(valeur: String): String {
        val b = StringBuilder("\"")
        for (c in valeur) {
            when (c) {
                '"' -> b.append("\\\"")
                '\\' -> b.append("\\\\")
                '\n' -> b.append("\\n")
                '\r' -> b.append("\\r")
                '\t' -> b.append("\\t")
                '\b' -> b.append("\\b")
                '\u000C' -> b.append("\\f")
                else -> if (c < ' ') {
                    b.append(String.format("\\u%04x", c.code))
                } else {
                    b.append(c)
                }
            }
        }
        return b.append("\"").toString()
    }

    /**
     * Représentation JSON d'une valeur, ou null si le type n'est pas supporté.
     *
     * Le serveur n'envoie que des chaînes et des entiers : `_data_pour_app`
     * convertit tout en `str(v)`, et l'horodatage est un entier. Tout autre
     * type est refusé plutôt que deviné.
     */
    private fun valeurJson(valeur: Any?): String? = when (valeur) {
        null -> "null"
        is String -> quoteJson(valeur)
        is Boolean -> valeur.toString()
        is Int, is Long, is Short, is Byte -> valeur.toString()
        else -> null
    }

    private fun sha256Hex(entree: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(entree.toByteArray(Charsets.UTF_8))
        return digest.joinToString("") { String.format("%02x", it) }
    }

    private fun hmacHex(secret: String, message: ByteArray): String {
        val mac = Mac.getInstance("HmacSHA256")
        val spec = SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256")
        mac.init(spec)
        return mac.doFinal(message).joinToString("") { String.format("%02x", it) }
    }

    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.length != b.length) return false
        var diff = 0
        for (i in a.indices) {
            diff = diff or (a[i].code xor b[i].code)
        }
        return diff == 0
    }
}
