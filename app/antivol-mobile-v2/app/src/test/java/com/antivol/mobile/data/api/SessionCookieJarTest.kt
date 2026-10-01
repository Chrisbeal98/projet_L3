package com.antivol.mobile.data.api

import okhttp3.Cookie
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Vérifie le cookie jar de session : sa persistance et son cloisonnement.
 *
 * Le test décisif est `leCookieSurvitARedemarrage`. Il couvre la régression
 * décrite dans `SessionCookieJar` : le cookie de session est la seule preuve
 * d'authentification du client, et un jar en mémoire le perd dès que le
 * processus est tué — ce que fait Android en arrière-plan sans prévenir.
 *
 * Le second risque couvert est l'inverse : un cookie restauré depuis le disque
 * ne doit jamais être renvoyé à un autre serveur. L'application permet de
 * changer d'URL dans les réglages, et ce cookie vaut la session du compte.
 */
class SessionCookieJarTest {

    private val api = "https://antivol.onrender.com/api/".toHttpUrl()
    private val sousDomaine = "https://sous.antivol.onrender.com/api/".toHttpUrl()
    private val autreServeur = "https://serveur-de-test.example.com/api/".toHttpUrl()

    /**
     * Hôte qui se termine par la chaîne du domaine du cookie sans être un
     * sous-domaine de celui-ci. C'est le piège de la comparaison par suffixe.
     */
    private val leurre = "https://evillantivol.onrender.com/api/".toHttpUrl()

    /** Double du support d'écriture : la persistance tient en une chaîne. */
    private class StockageMemoire(var contenu: String? = null) : SessionCookieJar.Stockage {
        override fun lire(): String? = contenu
        override fun ecrire(serialise: String) {
            contenu = serialise
        }
    }

    private fun cookieSession(
        domain: String = "antivol.onrender.com",
        hostOnly: Boolean = true
    ): Cookie {
        val builder = Cookie.Builder()
            .name("session")
            .value("eyJ1c2VyX2lkIjoxfQ.Zabc")
            .path("/")
            .expiresAt(System.currentTimeMillis() + 3_600_000L)
        // `hostOnlyDomain` et `domain` s'excluent, et l'API n'expose qu'un
        // constructeur sans argument : cf. `SessionCookieJar.restaurer`.
        return if (hostOnly) {
            builder.hostOnlyDomain(domain).build()
        } else {
            builder.domain(domain).build()
        }
    }

    private fun enregistrer(jar: SessionCookieJar) {
        jar.saveFromResponse(api, listOf(cookieSession()))
    }

    private fun valeurs(rendus: List<Cookie>) = rendus.map { it.value }

    @Test
    fun leCookieEstRenvoyeAuMemeHote() {
        val jar = SessionCookieJar()
        enregistrer(jar)
        assertEquals(1, jar.loadForRequest(api).size)
    }

    @Test
    fun leCookieNEstPasRenvoyeAUnAutreServeur() {
        val jar = SessionCookieJar(StockageMemoire())
        enregistrer(jar)
        assertTrue(jar.loadForRequest(autreServeur).isEmpty())
    }

    @Test
    fun leCookieNEstPasRenvoyeAUnHoteQuiSeTermineParLeDomaine() {
        val jar = SessionCookieJar(StockageMemoire())
        enregistrer(jar)
        assertTrue(jar.loadForRequest(leurre).isEmpty())
    }

    /** Un cookie de domaine (`Domain=`) est légitime sur les sous-domaines. */
    @Test
    fun unCookieDeDomaineEstEnvoyeAuxSousDomaines() {
        val jar = SessionCookieJar(StockageMemoire())
        jar.saveFromResponse(api, listOf(cookieSession(domain = "onrender.com", hostOnly = false)))
        assertEquals(1, jar.loadForRequest(sousDomaine).size)
    }

    @Test
    fun unCookieDeHoteNEstPasEnvoyeAuxSousDomaines() {
        val jar = SessionCookieJar(StockageMemoire())
        enregistrer(jar)
        assertTrue(jar.loadForRequest(sousDomaine).isEmpty())
    }

    /** Test de non-régression central : la session survit au processus. */
    @Test
    fun leCookieSurvitARedemarrage() {
        val stockage = StockageMemoire()
        enregistrer(SessionCookieJar(stockage))

        // Le processus est tué : seul le disque survit.
        val rendus = SessionCookieJar(stockage).loadForRequest(api)
        assertEquals(1, rendus.size)
        assertEquals("session", rendus[0].name)
        assertEquals(listOf("eyJ1c2VyX2lkIjoxfQ.Zabc"), valeurs(rendus))
    }

    @Test
    fun leFiltreDeDomaineSurvitAuRedemarrage() {
        val stockage = StockageMemoire()
        enregistrer(SessionCookieJar(stockage))
        assertTrue(SessionCookieJar(stockage).loadForRequest(autreServeur).isEmpty())
        assertTrue(SessionCookieJar(stockage).loadForRequest(leurre).isEmpty())
    }

    @Test
    fun laDeconnexionEffaceLeCookieSurDisque() {
        val stockage = StockageMemoire()
        val jar = SessionCookieJar(stockage)
        enregistrer(jar)
        assertTrue(stockage.contenu!!.isNotEmpty())

        jar.clear()
        assertEquals("", stockage.contenu)
        assertTrue(SessionCookieJar(stockage).loadForRequest(api).isEmpty())
    }

    @Test
    fun unCookieExpireNEstNiServiNiPersiste() {
        val stockage = StockageMemoire()
        val jar = SessionCookieJar(stockage)
        jar.saveFromResponse(
            api,
            listOf(
                Cookie.Builder()
                    .name("session")
                    .value("perime")
                    .hostOnlyDomain("antivol.onrender.com")
                    .path("/")
                    .expiresAt(System.currentTimeMillis() - 1_000L)
                    .build()
            )
        )
        assertTrue(jar.loadForRequest(api).isEmpty())
        // Un cookie déjà périmé n'a jamais rien à écrire : le support reste
        // vide, ce qui se lit « aucune session ».
        assertTrue(stockage.contenu.isNullOrEmpty())
    }

    /** Un cookie déjà expiré au moment de la sauvegarde ne ressuscite pas. */
    @Test
    fun unCookieExpireNEstPasRestaure() {
        val stockage = StockageMemoire()
        enregistrer(SessionCookieJar(stockage))

        // On rend la copie sur disque expirée, sans réécrire le schéma.
        stockage.contenu = stockage.contenu!!.replace(Regex("\"expiration\":\\d+"), "\"expiration\":1")
        assertTrue(SessionCookieJar(stockage).loadForRequest(api).isEmpty())
    }

    @Test
    fun desPreferencesCorrompuesNeFontPasPlanter() {
        val jar = SessionCookieJar(StockageMemoire("{ ceci n'est pas du json"))
        assertTrue(jar.loadForRequest(api).isEmpty())
    }

    @Test
    fun unEnregistrementInvalideNEmpechePasLesValides() {
        val stockage = StockageMemoire()
        enregistrer(SessionCookieJar(stockage))

        // On insère un enregistrement à trous devant un cookie valide.
        stockage.contenu = stockage.contenu!!.replaceFirst(
            "[",
            "[{\"nom\":null,\"valeur\":null,\"domaine\":null,\"chemin\":null},"
        )
        assertEquals(listOf("eyJ1c2VyX2lkIjoxfQ.Zabc"), valeurs(SessionCookieJar(stockage).loadForRequest(api)))
    }

    @Test
    fun unNouveauCookieRemplaceLePrecedent() {
        val jar = SessionCookieJar(StockageMemoire())
        enregistrer(jar)
        jar.saveFromResponse(
            api,
            listOf(
                Cookie.Builder()
                    .name("session")
                    .value("rafraichi")
                    .domain("antivol.onrender.com")
                    .path("/")
                    .expiresAt(System.currentTimeMillis() + 3_600_000L)
                    .build()
            )
        )
        assertEquals(listOf("rafraichi"), valeurs(jar.loadForRequest(api)))
    }
}
