package fr.eva.satellite

import android.content.Context
import android.net.Uri

/** Réglages du satellite (adresse d'EVA, clé, certificat, modes), gardés sur le téléphone. */
class Reglages(context: Context) {
    private val p = context.applicationContext.getSharedPreferences("eva-satellite", Context.MODE_PRIVATE)

    var eva: String
        get() = p.getString("eva", "") ?: ""
        set(v) = p.edit().putString("eva", v.trim().trimEnd('/')).apply()
    var jeton: String
        get() = p.getString("jeton", "") ?: ""
        set(v) = p.edit().putString("jeton", v.trim()).apply()
    var certificat: String
        get() = p.getString("certificat", "") ?: ""
        set(v) = p.edit().putString("certificat", v).apply()
    var mainsLibres: Boolean
        get() = p.getBoolean("mains_libres", true)
        set(v) = p.edit().putBoolean("mains_libres", v).apply()
    var seulementEnCharge: Boolean
        get() = p.getBoolean("en_charge", false)
        set(v) = p.edit().putBoolean("en_charge", v).apply()
    var voixEva: Boolean                                  // false : voix du téléphone (comme Momory), true : voix d'EVA
        get() = p.getBoolean("voix_eva2", false)
        set(v) = p.edit().putBoolean("voix_eva2", v).apply()
    var ecouteTelephone: Boolean                          // true : reconnaissance du téléphone (Google), false : celle d'EVA (Whisper)
        get() = p.getBoolean("ecoute_tel", true)
        set(v) = p.edit().putBoolean("ecoute_tel", v).apply()

    val pret: Boolean get() = eva.startsWith("http") && jeton.startsWith("evasat_")

    /** evasat://config?eva=https://192.168.1.10:8443&jeton=evasat_… (lien ou QR code donné par EVA). */
    fun depuisLien(uri: Uri?): Boolean {
        if (uri == null || uri.scheme != "evasat") return false
        val e = uri.getQueryParameter("eva") ?: return false
        val j = uri.getQueryParameter("jeton") ?: return false
        if (!e.startsWith("http") || !j.startsWith("evasat_")) return false
        eva = e
        jeton = j
        certificat = ""
        return true
    }
}
