package fr.eva.satellite

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.media.ToneGenerator
import android.speech.tts.TextToSpeech
import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.math.max
import kotlin.math.sqrt

const val TAUX = 16000
const val TRAME = 480                 // 30 ms
private const val PREROLL = 12        // ~350 ms gardés avant la parole
private const val FIN_SILENCE = 24    // 700 ms de silence = fin de phrase
private const val MIN_PAROLE = 10     // 300 ms
private const val MAX_PAROLE = 400    // 12 s

fun rms(t: ShortArray): Double {
    var s = 0.0
    for (x in t) s += x.toDouble() * x
    return sqrt(s / max(1, t.size))
}

/** Force de la parole : 90e centile de l'énergie par tranche de 30 ms (comme le satellite PC). */
fun niveau(trames: List<ShortArray>): Double {
    if (trames.isEmpty()) return 0.0
    val n = trames.map { rms(it) }.sorted()
    return n[((n.size - 1) * 0.9).toInt()]
}

fun wav(trames: List<ShortArray>): ByteArray {
    val nb = trames.sumOf { it.size }
    val b = ByteBuffer.allocate(44 + nb * 2).order(ByteOrder.LITTLE_ENDIAN)
    b.put("RIFF".toByteArray()).putInt(36 + nb * 2).put("WAVE".toByteArray()).put("fmt ".toByteArray())
        .putInt(16).putShort(1).putShort(1).putInt(TAUX).putInt(TAUX * 2).putShort(2).putShort(16)
        .put("data".toByteArray()).putInt(nb * 2)
    for (t in trames) for (x in t) b.putShort(x)
    return b.array()
}

/** Micro continu : lit des tranches de 30 ms dans une file ; phrase() rend une phrase complète (détection de voix simple). */
class Micro {
    private val file = ArrayBlockingQueue<ShortArray>(400)
    @Volatile private var actif = false
    @Volatile var sourd = false            // pendant qu'EVA parle : on n'écoute pas sa propre voix
    var seuil = 400.0
    private var fil: Thread? = null

    @SuppressLint("MissingPermission")
    fun demarrer() {
        if (actif) return
        actif = true
        fil = Thread {
            val min = AudioRecord.getMinBufferSize(TAUX, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
            val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, TAUX, AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT, max(min, TRAME * 2 * 8))
            try {
                rec.startRecording()
                val calib = mutableListOf<Double>()
                while (actif) {
                    val t = ShortArray(TRAME)
                    var lu = 0
                    while (lu < TRAME && actif) {
                        val n = rec.read(t, lu, TRAME - lu)
                        if (n <= 0) break
                        lu += n
                    }
                    if (lu < TRAME) continue
                    if (calib.size < 50) {                           // 1,5 s de bruit de fond pour régler le seuil
                        calib.add(rms(t))
                        if (calib.size == 50) seuil = max(calib.sorted()[25] * 3.0, 250.0)
                        continue
                    }
                    if (sourd) continue
                    if (!file.offer(t)) { file.poll(); file.offer(t) }
                }
            } finally {
                try { rec.stop() } catch (e: Exception) {}
                rec.release()
            }
        }.apply { isDaemon = true; start() }
    }

    fun arreter() {
        actif = false
        fil?.join(500)
        file.clear()
    }

    fun vider() = file.clear()

    /** Attend une phrase complète ; null si rien n'est dit avant attenteMaxMs (ou si on s'arrête). */
    fun phrase(attenteMaxMs: Long = 0, continuer: () -> Boolean = { true }): List<ShortArray>? {
        val avant = ArrayDeque<ShortArray>()
        val voix = mutableListOf<ShortArray>()
        var silence = 0
        var parle = 0
        val debut = System.currentTimeMillis()
        while (continuer()) {
            if (voix.isEmpty() && attenteMaxMs > 0 && System.currentTimeMillis() - debut > attenteMaxMs) return null
            val t = file.poll(500, TimeUnit.MILLISECONDS) ?: continue
            val fort = rms(t) > seuil
            if (voix.isEmpty()) {
                avant.addLast(t)
                if (avant.size > PREROLL) avant.removeFirst()
                parle = if (fort) parle + 1 else 0
                if (parle >= 3) voix.addAll(avant)
                continue
            }
            voix.add(t)
            silence = if (fort) 0 else silence + 1
            if (silence >= FIN_SILENCE || voix.size >= MAX_PAROLE) {
                if (voix.size - silence >= MIN_PAROLE) return voix.toList()
                voix.clear(); avant.clear(); silence = 0; parle = 0
            }
        }
        return null
    }
}

/** EVA parle : sa propre voix (eva-voice) si possible, sinon la synthèse vocale du téléphone. Une phrase après l'autre. */
class Parole(private val context: Context, private val micro: Micro) {
    var eva: EvaClient? = null
    var voixEva = true
    private val file = LinkedBlockingQueue<String>()
    @Volatile private var occupe = false
    @Volatile private var lecteur: MediaPlayer? = null
    @Volatile private var coupe: CountDownLatch? = null
    private var tts: TextToSpeech? = null
    private var ttsPret = false
    private val bips = try { ToneGenerator(AudioManager.STREAM_MUSIC, 70) } catch (e: Exception) { null }

    init {
        tts = TextToSpeech(context.applicationContext) { s ->
            if (s == TextToSpeech.SUCCESS) { tts?.language = Locale.FRENCH; ttsPret = true }
        }
        Thread {
            while (true) {
                val texte = file.take()
                occupe = true
                micro.sourd = true
                try { lire(texte) } catch (e: Exception) { Etat.journal("Voix : ${e.message}") }
                if (file.isEmpty()) {
                    Thread.sleep(250)
                    micro.vider()
                    micro.sourd = false
                    occupe = false
                }
            }
        }.apply { isDaemon = true; start() }
    }

    private fun lire(texte: String) {
        val client = eva
        if (voixEva && client != null) {
            try {
                val donnees = client.voix(texte)
                if (donnees.size > 44) {
                    val f = File.createTempFile("eva", ".wav", context.cacheDir)
                    f.writeBytes(donnees)
                    val fini = CountDownLatch(1)
                    coupe = fini
                    val mp = MediaPlayer()
                    lecteur = mp
                    mp.setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
                    mp.setDataSource(f.absolutePath)
                    mp.setOnCompletionListener { fini.countDown() }
                    mp.setOnErrorListener { _, _, _ -> fini.countDown(); true }
                    mp.prepare()
                    mp.start()
                    fini.await(120, TimeUnit.SECONDS)
                    try { mp.release() } catch (e: Exception) {}
                    lecteur = null
                    f.delete()
                    return
                }
            } catch (e: Exception) {
                Etat.journal("Voix d'EVA indisponible, voix du téléphone : ${e.message}")
            }
        }
        if (ttsPret) {
            val id = "eva-${System.nanoTime()}"
            tts?.speak(texte, TextToSpeech.QUEUE_ADD, null, id)
            Thread.sleep(300)
            while (tts?.isSpeaking == true) Thread.sleep(100)
        }
    }

    fun dire(texte: String) {
        if (texte.isNotBlank()) { micro.sourd = true; file.put(texte) }
    }

    /** Attend la fin de ce qui est en cours de lecture. */
    fun attendre() {
        Thread.sleep(100)
        while (occupe || file.isNotEmpty()) Thread.sleep(100)
    }

    fun couper() {
        file.clear()
        try { lecteur?.stop() } catch (e: Exception) {}
        coupe?.countDown()
        tts?.stop()
    }

    fun bip(aigu: Boolean = false) {
        bips?.startTone(if (aigu) ToneGenerator.TONE_PROP_BEEP2 else ToneGenerator.TONE_PROP_BEEP, 150)
        Thread.sleep(200)
    }

    /** « Où est mon téléphone ? » : sonnerie forte pendant `secondes`, même en mode silencieux (flux alarme). */
    fun sonner(secondes: Int) {
        val g = try { ToneGenerator(AudioManager.STREAM_ALARM, 100) } catch (e: Exception) { return }
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val avant = am.getStreamVolume(AudioManager.STREAM_ALARM)
        am.setStreamVolume(AudioManager.STREAM_ALARM, am.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0)
        val fin = System.currentTimeMillis() + secondes * 1000L
        while (System.currentTimeMillis() < fin && !Etat.arretSonnerie) {
            g.startTone(ToneGenerator.TONE_CDMA_ALERT_CALL_GUARD, 600)
            Thread.sleep(900)
        }
        Etat.arretSonnerie = false
        am.setStreamVolume(AudioManager.STREAM_ALARM, avant, 0)
        g.release()
    }

    fun fermer() {
        couper()
        tts?.shutdown()
    }
}
