package fr.eva.satellite

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ServiceInfo
import android.os.BatteryManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import org.json.JSONArray
import org.json.JSONObject

/** Le satellite tourne ici, même écran éteint : écoute « EVA… », réponses à voix haute, annonces et ordres d'EVA. */
class SatelliteService : Service() {
    companion object {
        const val DEMARRER = "fr.eva.satellite.DEMARRER"
        const val PARLER = "fr.eva.satellite.PARLER"
        const val ARRETER = "fr.eva.satellite.ARRETER"
        const val TAIRE = "fr.eva.satellite.TAIRE"
        private const val CANAL = "satellite"
        private const val EVEIL_MS = 8000L

        fun lancer(c: Context, action: String = DEMARRER) {
            val i = Intent(c, SatelliteService::class.java).setAction(action)
            if (action == ARRETER) c.startService(i) else c.startForegroundService(i)
        }
    }

    private lateinit var reglages: Reglages
    private val micro = Micro()
    private lateinit var parole: Parole
    private lateinit var reco: Reconnaisseur
    private var eva: EvaClient? = null
    @Volatile private var enMarche = false
    @Volatile private var pttDemande = false
    @Volatile private var pauseEva = false          // écoute coupée depuis EVA (Maison › Satellites)
    private var verrou: PowerManager.WakeLock? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        reglages = Reglages(this)
        parole = Parole(this, micro)
        reco = Reconnaisseur(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ARRETER -> { arreter(); return START_NOT_STICKY }
            TAIRE -> { parole.couper(); Etat.arretSonnerie = true }
            PARLER -> { premierPlan(); pttDemande = true; parole.couper(); demarrer() }
            else -> { premierPlan(); demarrer() }
        }
        return START_STICKY
    }

    private fun notification(texte: String): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CANAL) == null) {
            nm.createNotificationChannel(NotificationChannel(CANAL, "Satellite EVA", NotificationManager.IMPORTANCE_LOW))
        }
        val ouvrir = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE)
        val parler = PendingIntent.getService(this, 1, Intent(this, SatelliteService::class.java).setAction(PARLER), PendingIntent.FLAG_IMMUTABLE)
        val taire = PendingIntent.getService(this, 2, Intent(this, SatelliteService::class.java).setAction(TAIRE), PendingIntent.FLAG_IMMUTABLE)
        return NotificationCompat.Builder(this, CANAL)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("EVA écoute")
            .setContentText(texte)
            .setOngoing(true)
            .setContentIntent(ouvrir)
            .addAction(0, "Parler", parler)
            .addAction(0, "Se taire", taire)
            .build()
    }

    private fun premierPlan() {
        val type = if (Build.VERSION.SDK_INT >= 30) ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK else 0
        ServiceCompat.startForeground(this, 1, notification(if (reglages.mainsLibres) "Dis « EVA… »" else "Touche « Parler »"), type)
    }

    private fun demarrer() {
        if (enMarche) return
        if (!reglages.pret) {
            Etat.statut.value = "À configurer : adresse d'EVA et clé du satellite"
            stopSelf()
            return
        }
        enMarche = true
        Etat.actif.value = true
        verrou = (getSystemService(POWER_SERVICE) as PowerManager).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "eva:satellite").apply {
            setReferenceCounted(false); acquire()
        }
        Thread({ boucle() }, "eva-ecoute").start()
    }

    private fun arreter() {
        enMarche = false
        reco.fermer()
        micro.arreter()
        parole.couper()
        Etat.actif.value = false
        Etat.ecoute.value = false
        Etat.statut.value = "Arrêté"
        try { verrou?.release() } catch (e: Exception) {}
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        enMarche = false
        reco.fermer()
        micro.arreter()
        parole.fermer()
        try { verrou?.release() } catch (e: Exception) {}
        Etat.actif.value = false
        super.onDestroy()
    }

    private fun infos() = JSONObject()
        .put("capacites", JSONArray(listOf("dire", "telephone")))
        .put("systeme", "Android ${Build.VERSION.RELEASE} (${Build.MANUFACTURER} ${Build.MODEL})")
        .put("applis", JSONArray())
        .put("en_pause", pauseEva || !reglages.mainsLibres)
        .put("version", "android-" + androidx.core.content.pm.PackageInfoCompat.getLongVersionCode(packageManager.getPackageInfo(packageName, 0)))

    private fun enCharge(): Boolean {
        val b = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED)) ?: return true
        val s = b.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
        return s == BatteryManager.BATTERY_STATUS_CHARGING || s == BatteryManager.BATTERY_STATUS_FULL
    }

    private fun connecter(): EvaClient {
        if (reglages.certificat.isBlank() && reglages.eva.startsWith("https")) {
            try { reglages.certificat = EvaClient.recupererCertificat(reglages.eva) } catch (e: Exception) {
                Etat.journal("Certificat d'EVA non récupéré : ${e.message}")
            }
        }
        val c = EvaClient(reglages.eva, reglages.jeton, reglages.certificat)
        val info = c.bonjour(infos())
        pauseEva = info.optBoolean("pause", false)
        val nom = info.optString("nom", "")
        Etat.satellite.value = nom + (info.optString("piece", "").let { if (it.isNotEmpty()) " · $it" else "" })
        Etat.journal("Connecté à EVA : « $nom »")
        val v = c.versionAndroid()
        val moi = androidx.core.content.pm.PackageInfoCompat.getLongVersionCode(packageManager.getPackageInfo(packageName, 0))
        Etat.majDisponible.value = if (v > moi) v else 0
        return c
    }

    private fun boucle() {
        while (enMarche && eva == null) {
            try {
                eva = connecter()
            } catch (e: JetonRefuse) {
                Etat.statut.value = e.message ?: "Clé refusée"; Etat.journal(e.message ?: ""); arreter(); return
            } catch (e: Exception) {
                Etat.statut.value = "EVA injoignable (${e.message}) : nouvel essai dans 10 s"
                Thread.sleep(10_000)
            }
        }
        val c = eva ?: return
        parole.eva = c
        parole.voixEva = reglages.voixEva
        Thread({ signesDeVie(c) }, "eva-vie").apply { isDaemon = true; start() }
        Thread({ ordres(c) }, "eva-ordres").apply { isDaemon = true; start() }
        var eveilleJusqua = 0L
        while (enMarche) {
            try {
                parole.voixEva = reglages.voixEva
                val ptt = pttDemande
                if (!ptt && (pauseEva || !reglages.mainsLibres || (reglages.seulementEnCharge && !enCharge()))) {
                    if (Etat.ecoute.value) { micro.arreter(); Etat.ecoute.value = false }
                    Etat.statut.value = when {
                        pauseEva -> "⏸ En pause depuis EVA (Maison › Satellites) : touche « Parler » au besoin"
                        !reglages.mainsLibres -> "Prêt : touche « Parler »"
                        else -> "En pause : le téléphone n'est pas en charge"
                    }
                    Thread.sleep(1000)
                    continue
                }
                if (reglages.ecouteTelephone && reco.disponible()) {
                    // Reconnaissance du téléphone (Google) : bien plus juste ; le micro d'EVA reste éteint (un seul à la fois).
                    if (Etat.ecoute.value) { micro.arreter(); Etat.ecoute.value = false }
                    parole.attendre()
                    if (ptt) {
                        pttDemande = false
                        parole.bip()
                        Etat.statut.value = "Je t'écoute…"
                        val t = reco.ecouter(8000, silencieux = false) ?: continue
                        traiter(c, Texte.commandeApresEveil(t)?.takeIf { it.isNotEmpty() } ?: t)
                        continue
                    }
                    val suiteTel = System.currentTimeMillis() < eveilleJusqua
                    Etat.statut.value = if (suiteTel) "Je t'écoute…" else "Dis « EVA… »"
                    val t = reco.ecouter(if (suiteTel) 8000 else 15_000) ?: continue
                    val cmd = if (suiteTel) (Texte.commandeApresEveil(t) ?: t) else Texte.commandeApresEveil(t)
                    if (cmd == null) { Etat.journal("Entendu sans « EVA » : $t"); continue }
                    if (cmd.isEmpty()) { parole.bip(); eveilleJusqua = System.currentTimeMillis() + EVEIL_MS; continue }
                    eveilleJusqua = 0
                    traiter(c, cmd)
                    continue
                }
                reco.rendreLesBips()
                if (!Etat.ecoute.value) { micro.demarrer(); Etat.ecoute.value = true }
                if (ptt) {
                    pttDemande = false
                    parole.attendre()
                    parole.bip()
                    Etat.statut.value = "Je t'écoute…"
                    micro.vider()
                    val p = micro.phrase(8000) { enMarche } ?: continue
                    val t = c.transcrire(wav(p))
                    if (!Texte.hallucination(t)) traiter(c, Texte.commandeApresEveil(t)?.takeIf { it.isNotEmpty() } ?: t)
                    continue
                }
                Etat.statut.value = if (System.currentTimeMillis() < eveilleJusqua) "Je t'écoute…" else "Dis « EVA… »"
                val p = micro.phrase(1500) { enMarche && !pttDemande } ?: continue
                val suite = System.currentTimeMillis() < eveilleJusqua
                // Plusieurs satellites ont entendu : seul celui qui entend le mieux continue.
                if (!c.eveil(niveau(p) / maxOf(micro.seuil, 1.0), suite)) continue
                val texte = c.transcrire(wav(p))
                if (Texte.hallucination(texte)) continue
                val commande = if (suite) (Texte.commandeApresEveil(texte) ?: texte) else Texte.commandeApresEveil(texte)
                if (commande == null) continue
                if (commande.isEmpty()) {
                    parole.bip()
                    eveilleJusqua = System.currentTimeMillis() + EVEIL_MS
                    continue
                }
                eveilleJusqua = 0
                traiter(c, commande)
            } catch (e: JetonRefuse) {
                Etat.statut.value = e.message ?: "Clé refusée"; Etat.journal(e.message ?: ""); arreter(); return
            } catch (e: InterruptedException) {
                return
            } catch (e: Exception) {
                Etat.journal("Erreur : ${e.message}")
                Etat.statut.value = "EVA injoignable : nouvel essai…"
                Thread.sleep(3000)
            }
        }
    }

    /** Une demande : réponse dite au fil de l'eau ; les demandes d'accord (« Tu confirmes ? ») se règlent à la voix. */
    private fun traiter(c: EvaClient, commande: String) {
        Etat.toi.value = commande
        Etat.eva.value = "…"
        Etat.journal("Toi : $commande")
        Etat.statut.value = "Je réfléchis…"
        var question = derouler(c, "/api/satellite/demander", commande)
        var n = 0
        while (question != null && n < 4) {
            n++
            parole.dire(question)
            parole.attendre()
            parole.bip(aigu = true)
            Etat.statut.value = "Oui ou non ?"
            val rep = if (reglages.ecouteTelephone && reco.disponible()) {
                reco.ecouter(10_000, silencieux = false) ?: "non"
            } else {
                micro.vider()
                micro.phrase(10_000) { enMarche }?.let { c.transcrire(wav(it)) }?.takeUnless { Texte.hallucination(it) } ?: "non"
            }
            Etat.journal("Accord : $rep")
            question = derouler(c, "/api/satellite/repondre", rep)
        }
    }

    private fun derouler(c: EvaClient, chemin: String, texte: String): String? {
        var dit = false
        var question: String? = null
        val morceaux = StringBuilder()
        c.flux(chemin, texte) { ev ->
            when {
                ev.has("attente") && !ev.has("question") -> { Etat.statut.value = ev.optString("attente"); parole.dire(ev.optString("attente")); true }
                ev.has("dire") -> {
                    dit = true
                    morceaux.append(ev.optString("dire")).append(' ')
                    Etat.eva.value = morceaux.toString().trim()
                    parole.dire(ev.optString("dire")); true
                }
                ev.has("question") -> { question = ev.optString("question"); Etat.eva.value = question ?: ""; false }
                ev.has("reponse") -> {
                    val r = ev.optString("reponse")
                    Etat.eva.value = r
                    Etat.journal("EVA : $r")
                    if (ev.optBoolean("dire_aussi") || !dit) parole.dire(r)
                    false
                }
                else -> true
            }
        }
        parole.attendre()
        return question
    }

    private fun signesDeVie(c: EvaClient) {
        while (enMarche) {
            Thread.sleep(60_000)
            try { pauseEva = c.bonjour(infos()).optBoolean("pause", pauseEva) } catch (e: Exception) {}
        }
    }

    /** Ordres d'EVA : annonce à voix haute, « fais sonner mon téléphone », désinstallation depuis EVA. */
    private fun ordres(c: EvaClient) {
        while (enMarche) {
            try {
                for (o in c.ordres()) {
                    val res = try {
                        when (o.optString("type")) {
                            "controle" -> when (o.optString("action")) {
                                "parler" -> { pttDemande = true; JSONObject().put("ok", true) }
                                "arreter" -> {
                                    Thread { Thread.sleep(1000); arreter() }.start()
                                    JSONObject().put("ok", true).put("info", "Satellite arrêté : rouvre l'appli sur le téléphone pour le relancer.")
                                }
                                "redemarrer" -> {
                                    Thread {
                                        Thread.sleep(1000)
                                        micro.arreter(); Etat.ecoute.value = false
                                        Etat.journal("Redémarrage demandé par EVA")
                                    }.start()
                                    JSONObject().put("ok", true).put("info", "Micro relancé.")
                                }
                                else -> JSONObject().put("error", "Action inconnue.")
                            }
                            "ecoute" -> {
                                pauseEva = !o.optBoolean("actif", true)
                                Etat.journal(if (pauseEva) "Écoute mise en pause depuis EVA" else "Écoute réactivée depuis EVA")
                                JSONObject().put("ok", true).put("en_pause", pauseEva)
                            }
                            "dire" -> { parole.bip(aigu = true); parole.dire(o.optString("texte")); JSONObject().put("ok", true) }
                            "telephone" -> when (o.optString("action")) {
                                "sonner" -> {
                                    Thread { parole.sonner(o.optInt("secondes", 30)) }.start()
                                    JSONObject().put("ok", true).put("info", "Le téléphone sonne (touche « Se taire » pour arrêter).")
                                }
                                else -> JSONObject().put("error", "Action inconnue sur le téléphone.")
                            }
                            "desinstaller" -> {
                                Etat.journal("EVA a retiré ce satellite : tu peux désinstaller l'appli.")
                                Thread {
                                    Thread.sleep(1500)
                                    reglages.jeton = ""; reglages.certificat = ""
                                    Etat.statut.value = "Retiré d'EVA : désinstalle l'appli (appui long sur l'icône › Désinstaller)"
                                    arreter()
                                }.start()
                                JSONObject().put("ok", true).put("info", "Satellite Android arrêté et oublié ; l'appli se désinstalle depuis le téléphone.")
                            }
                            else -> JSONObject().put("error", "Ordre non pris en charge par le satellite Android.")
                        }
                    } catch (e: Exception) { JSONObject().put("error", e.message ?: "erreur") }
                    c.resultat(o.optString("id"), res)
                }
            } catch (e: JetonRefuse) {
                return
            } catch (e: Exception) {
                Thread.sleep(5000)
            }
        }
    }
}
