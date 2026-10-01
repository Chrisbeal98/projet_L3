package com.antivol.mobile.data.api

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl

/**
 * Conservation des cookies de session : persistée sur disque, et limitée à
 * l'hôte de l'API.
 *
 * ## Pourquoi il faut persister
 *
 * `/auth/login` ne renvoie aucun jeton : l'authentification repose
 * entièrement sur le cookie de session posé par Flask. Un jar en mémoire le
 * perd dès que le processus est tué — et Android tue les processus
 * d'arrière-plan sans préavis, parfois au bout de quelques minutes.
 *
 * Après un simple passage en arrière-plan, l'application se retrouvait donc
 * sans cookie alors que les préférences affirmaient toujours être connectées :
 * le tableau de bord s'affichait vide, sans message d'erreur, et l'utilisateur
 * devait se reconnecter à la main. C'est la régression v1 → v2 que le cahier
 * des charges §13 désigne par « persistance du token d'authentification ».
 *
 * Le repli par `user_id` dans le corps des requêtes cachait le problème — et
 * ouvrait au passage une faille d'usurpation d'identité, puisque n'importe quel
 * client pouvait dès lors réclamer la session d'autrui. On ne peut pas garder
 * les deux : il faut persister la session, pas la falsifier.
 *
 * ## Pourquoi le filtre de domaine est conservé
 *
 * Persister le cookie sans le restreindre aggraverait la fuite que ce jar
 * corrigeait : l'application permet de changer d'URL de serveur dans les
 * réglages, et un cookie restauré depuis le disque serait renvoyé tel quel à
 * ce nouveau serveur. Le filtre est donc appliqué à chaque lecture, restauration
 * comprise.
 *
 * ## Pourquoi cette classe ignore Android
 *
 * Elle ne dépend ni de `Context` ni de `SharedPreferences` : la persistance est
 * abstraite derrière [Stockage]. Le comportement — filtre de domaine,
 * expiration, aller-retour de sérialisation — est donc vérifiable sur la JVM,
 * dans `SessionCookieJarTest`, au lieu d'être seulement vérifiable sur un
 * téléphone.
 */
internal class SessionCookieJar(private val stockage: Stockage? = null) : CookieJar {

    /** Support d'écriture du jar, fourni par l'appelant. */
    interface Stockage {
        /** Renvoie la dernière chaîne sérialisée, ou `null` s'il n'y en a pas. */
        fun lire(): String?

        /** Doit accepter une chaîne vide, qui signifie « plus aucun cookie ». */
        fun ecrire(serialise: String)
    }

    /**
     * Forme sérialisée d'un cookie.
     *
     * Tous les champs sont nullables et ont une valeur par défaut : Gson
     * n'appelle pas le constructeur primaire et n'honore donc pas les valeurs
     * par défaut de Kotlin. Un fichier de préférences corrompu, ou amputé par
     * une mise à jour, produirait sinon des `NullPointerException` au premier
     * accès — c'est-à-dire au démarrage de l'application, avant même
     * l'affichage de l'écran de connexion.
     *
     * Il n'y a pas de champ « persistant » : OkHttp le déduit de
     * `expiresAt` à la construction, et `Cookie.Builder` ne permet pas de le
     * fixer. Le restaurer tel quel, à partir de la même expiration, redonne
     * donc la même valeur.
     */
    private data class CookiePersiste(
        val nom: String? = null,
        val valeur: String? = null,
        val domaine: String? = null,
        val chemin: String? = null,
        val expiration: Long = 0L,
        val securise: Boolean = false,
        val hoteSeulement: Boolean = false
    )

    private val gson = Gson()
    private val cookies = mutableListOf<Cookie>()

    init {
        stockage?.lire()?.let { restaurer(it) }
    }

    @Synchronized
    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        val now = System.currentTimeMillis()
        var modifie = false
        for (cookie in cookies) {
            // Un nouveau cookie remplace l'ancien pour le même nom.
            this.cookies.removeAll { it.name == cookie.name && it.domain == cookie.domain }
            if (cookie.expiresAt > now) {
                this.cookies.add(cookie)
                modifie = true
            }
        }
        if (modifie) persister()
    }

    @Synchronized
    override fun loadForRequest(url: HttpUrl): List<Cookie> {
        val now = System.currentTimeMillis()
        val perimes = cookies.filter { it.expiresAt <= now }
        if (perimes.isNotEmpty()) {
            cookies.removeAll(perimes.toSet())
            persister()
        }
        return cookies.filter { domaineAutorise(url.host, it) }
    }

    /** Déconnexion : plus aucun cookie, ni en mémoire ni sur le disque. */
    @Synchronized
    fun clear() {
        cookies.clear()
        stockage?.ecrire("")
    }

    /**
     * Ce cookie a-t-il le droit d'être envoyé à cet hôte ?
     *
     * Deux règles, et les deux sont nécessaires :
     *
     * - un cookie **de domaine** (`Domain=`, `hostOnly == false`) vaut pour
     *   l'hôte et ses sous-domaines ;
     * - un cookie **propre à un hôte** (`hostOnly == true`) ne vaut que pour
     *   cet hôte exact. Le cookie de session de Flask est de ce type : le
     *   laisser remonter vers un sous-domaine élargirait sa portée sans
     *   raison.
     *
     * La comparaison se fait par frontière et non par suffixe : sans elle, un
     * cookie de `antivol.onrender.com` serait renvoyé à
     * `evillantivol.onrender.com`, qui se termine par la même chaîne — et avec
     * lui la session du compte.
     */
    private fun domaineAutorise(hote: String, cookie: Cookie): Boolean {
        val d = cookie.domain.removePrefix(".").lowercase()
        val h = hote.lowercase()
        if (h == d) return true
        if (cookie.hostOnly) return false
        return h.endsWith(".$d")
    }

    private fun persister() {
        val cible = stockage ?: return
        if (cookies.isEmpty()) {
            cible.ecrire("")
            return
        }
        cible.ecrire(
            gson.toJson(
                cookies.map {
                    CookiePersiste(
                        nom = it.name,
                        valeur = it.value,
                        domaine = it.domain,
                        chemin = it.path,
                        expiration = it.expiresAt,
                        securise = it.secure,
                        hoteSeulement = it.hostOnly
                    )
                }
            )
        )
    }

    private fun restaurer(serialise: String) {
        if (serialise.isBlank()) return
        val lus: List<CookiePersiste> = try {
            val type = object : TypeToken<List<CookiePersiste>>() {}.type
            gson.fromJson<List<CookiePersiste>>(serialise, type) ?: emptyList()
        } catch (_: Exception) {
            // Préférences illisibles : on repart d'un jar vide. Faire planter
            // l'application au démarrage serait bien pire que d'exiger une
            // reconnexion.
            return
        }

        val now = System.currentTimeMillis()
        for (c in lus) {
            val nom = c.nom
            val valeur = c.valeur
            val domaine = c.domaine
            val chemin = c.chemin
            if (nom.isNullOrEmpty() || valeur == null || domaine.isNullOrEmpty() ||
                chemin.isNullOrEmpty() || c.expiration <= now
            ) {
                continue
            }
            try {
                val builder = Cookie.Builder()
                    .name(nom)
                    .value(valeur)
                    .path(chemin)
                    .expiresAt(c.expiration)
                // `hostOnlyDomain` et `domain` ne sont pas cumulables : le
                // premier marque le cookie comme propre à cet hôte, le second
                // l'étend à ses sous-domaines. L'API n'expose qu'un
                // constructeur sans argument, d'où le `if`.
                if (c.hoteSeulement) builder.hostOnlyDomain(domaine) else builder.domain(domaine)
                if (c.securise) builder.secure()
                cookies.add(builder.build())
            } catch (_: IllegalArgumentException) {
                // Un seul enregistrement illisible ne doit pas priver
                // l'utilisateur des cookies valides du même fichier.
            }
        }
    }
}
