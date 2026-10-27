package fr.eva.satellite

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.internal.tls.OkHostnameVerifier
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.IOException
import java.security.KeyStore
import java.security.SecureRandom
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import javax.net.ssl.X509TrustManager

class JetonRefuse : IOException("Clé refusée : ce satellite a été supprimé ou réinstallé dans EVA (Maison › Satellites).")

/** Dialogue avec EVA : mêmes adresses que le satellite PC (jeton du satellite dans l'en-tête Authorization). */
class EvaClient(private val url: String, private val jeton: String, certificatPem: String) {
    private val json = "application/json; charset=utf-8".toMediaType()
    private val client: OkHttpClient = construire(certificatPem)
    private val long: OkHttpClient = client.newBuilder().readTimeout(270, TimeUnit.SECONDS).build()

    companion object {
        /** Premier contact : récupère le certificat d'EVA sans le vérifier (réseau de la maison), comme les installateurs PC. */
        fun recupererCertificat(url: String): String {
            val tm = object : X509TrustManager {
                override fun checkClientTrusted(c: Array<X509Certificate>, a: String) {}
                override fun checkServerTrusted(c: Array<X509Certificate>, a: String) {}
                override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
            }
            val ctx = SSLContext.getInstance("TLS").apply { init(null, arrayOf(tm), SecureRandom()) }
            val c = OkHttpClient.Builder().sslSocketFactory(ctx.socketFactory, tm).hostnameVerifier { _, _ -> true }
                .connectTimeout(10, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS).build()
            c.newCall(Request.Builder().url(url.trimEnd('/') + "/api/https/install/eva-certificat.crt").build()).execute().use { r ->
                if (!r.isSuccessful) return ""
                val t = r.body?.string() ?: ""
                return if (t.contains("BEGIN CERTIFICATE")) t else ""
            }
        }

        private fun lireCa(pem: String): X509Certificate? = try {
            if (pem.isBlank()) null
            else CertificateFactory.getInstance("X.509").generateCertificate(ByteArrayInputStream(pem.toByteArray())) as X509Certificate
        } catch (e: Exception) { null }

        private fun construire(pem: String): OkHttpClient {
            val b = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS)
            val ca = lireCa(pem) ?: return b.build()
            // Confiance : les autorités du téléphone, PLUS le certificat d'EVA (autorité locale de Caddy).
            val systeme = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).apply { init(null as KeyStore?) }
                .trustManagers.filterIsInstance<X509TrustManager>().first()
            val ks = KeyStore.getInstance(KeyStore.getDefaultType()).apply { load(null, null); setCertificateEntry("eva", ca) }
            val evaTm = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).apply { init(ks) }
                .trustManagers.filterIsInstance<X509TrustManager>().first()
            val tm = object : X509TrustManager {
                override fun checkClientTrusted(c: Array<X509Certificate>, a: String) = systeme.checkClientTrusted(c, a)
                override fun checkServerTrusted(c: Array<X509Certificate>, a: String) {
                    try { systeme.checkServerTrusted(c, a) } catch (e: Exception) {
                        try { evaTm.checkServerTrusted(c, a) } catch (e2: Exception) {
                            if (!signeParEva(c, ca)) throw e2
                        }
                    }
                }
                override fun getAcceptedIssuers(): Array<X509Certificate> = systeme.acceptedIssuers + ca
            }
            val ctx = SSLContext.getInstance("TLS").apply { init(null, arrayOf(tm), SecureRandom()) }
            return b.sslSocketFactory(ctx.socketFactory, tm)
                .hostnameVerifier { host, session ->
                    // Adresse IP de la maison : le certificat d'EVA peut porter un autre nom ; il suffit qu'il vienne d'EVA.
                    OkHostnameVerifier.verify(host, session) ||
                        try { signeParEva(session.peerCertificates.filterIsInstance<X509Certificate>().toTypedArray(), ca) } catch (e: Exception) { false }
                }.build()
        }

        private fun signeParEva(chaine: Array<X509Certificate>, ca: X509Certificate): Boolean =
            chaine.any { c -> c == ca || try { c.verify(ca.publicKey); true } catch (e: Exception) { false } }
    }

    private fun req(chemin: String) = Request.Builder().url(url + chemin).header("Authorization", "Bearer $jeton")

    private fun postJson(chemin: String, corps: JSONObject, c: OkHttpClient = client): JSONObject {
        c.newCall(req(chemin).post(corps.toString().toRequestBody(json)).build()).execute().use { r ->
            if (r.code == 401) throw JetonRefuse()
            if (!r.isSuccessful) throw IOException("EVA a répondu ${r.code}")
            val t = r.body?.string() ?: "{}"
            return if (t.trim().startsWith("{")) JSONObject(t) else JSONObject()
        }
    }

    fun bonjour(infos: JSONObject): JSONObject = postJson("/api/satellite/bonjour", infos)

    fun eveil(score: Double, suite: Boolean): Boolean = try {
        postJson("/api/satellite/eveil", JSONObject().put("score", score).put("suite", suite)).optBoolean("repondre", true)
    } catch (e: JetonRefuse) { throw e } catch (e: Exception) { true }

    fun transcrire(wav: ByteArray): String {
        val corps = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("audio", "phrase.wav", wav.toRequestBody("audio/wav".toMediaType())).build()
        client.newCall(req("/voice/stt?mode=fast").post(corps).build()).execute().use { r ->
            if (r.code == 401) throw JetonRefuse()
            if (!r.isSuccessful) throw IOException("Reconnaissance vocale : ${r.code}")
            return JSONObject(r.body?.string() ?: "{}").optString("text", "").trim()
        }
    }

    fun voix(texte: String): ByteArray {
        client.newCall(req("/voice/tts").post(JSONObject().put("text", texte).toString().toRequestBody(json)).build()).execute().use { r ->
            if (!r.isSuccessful) throw IOException("Voix d'EVA : ${r.code}")
            return r.body?.bytes() ?: ByteArray(0)
        }
    }

    /** Réponse au fil de l'eau : {"attente"}, {"dire"}, puis {"question"} ou {"reponse"} (une ligne JSON par événement). */
    fun flux(chemin: String, texte: String, recu: (JSONObject) -> Boolean) {
        long.newCall(req("${chemin}_flux").post(JSONObject().put("texte", texte).toString().toRequestBody(json)).build()).execute().use { r ->
            if (r.code == 401) throw JetonRefuse()
            if (!r.isSuccessful) throw IOException("EVA a répondu ${r.code}")
            val src = r.body?.source() ?: return
            while (true) {
                val ligne = src.readUtf8Line() ?: break
                if (ligne.isBlank()) continue
                val ev = try { JSONObject(ligne) } catch (e: Exception) { continue }
                if (!recu(ev)) break
            }
        }
    }

    fun ordres(): List<JSONObject> {
        val o = postJson("/api/satellite/ordres", JSONObject(), long)
        val a = o.optJSONArray("ordres") ?: JSONArray()
        return (0 until a.length()).map { a.getJSONObject(it) }
    }

    fun resultat(id: String, res: JSONObject) {
        postJson("/api/satellite/resultat", JSONObject().put("id", id).put("resultat", res))
    }

    /** Version de l'appli Android servie par EVA (0 si EVA n'en a pas). */
    fun versionAndroid(): Int = try {
        client.newCall(Request.Builder().url("$url/api/public/satellite/version").build()).execute().use { r ->
            JSONObject(r.body?.string() ?: "{}").optInt("android", 0)
        }
    } catch (e: Exception) { 0 }
}
