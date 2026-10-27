package fr.eva.satellite

import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Reconnaissance vocale du TÉLÉPHONE (Google sur la plupart des Android), comme l'appli Momory : bien plus juste en français
 * que Whisper sur un NAS, et rapide. Utilisée depuis un fil de travail : ecouter() bloque jusqu'au résultat (ou null).
 * Les petits « bips » de démarrage de l'écoute sont coupés pendant l'écoute continue.
 */
class Reconnaisseur(private val context: Context) {
    private val principal = Handler(Looper.getMainLooper())
    private var reco: SpeechRecognizer? = null
    private val audio = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    @Volatile var niveau = 0f          // volume entendu (pour le diagnostic)

    fun disponible(): Boolean = SpeechRecognizer.isRecognitionAvailable(context)

    private fun bips(couper: Boolean) {
        for (flux in intArrayOf(AudioManager.STREAM_SYSTEM, AudioManager.STREAM_NOTIFICATION)) {
            try { audio.adjustStreamVolume(flux, if (couper) AudioManager.ADJUST_MUTE else AudioManager.ADJUST_UNMUTE, 0) } catch (e: Exception) {}
        }
    }

    /** Écoute une phrase ; null si rien (silence, bruit) ou délai dépassé. */
    fun ecouter(delaiMs: Long = 10_000, silencieux: Boolean = true): String? {
        val fini = CountDownLatch(1)
        var texte: String? = null
        principal.post {
            try {
                if (reco == null) reco = SpeechRecognizer.createSpeechRecognizer(context)
                if (silencieux) bips(true)
                reco?.setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) {}
                    override fun onBeginningOfSpeech() {}
                    override fun onRmsChanged(rmsdB: Float) { niveau = rmsdB }
                    override fun onBufferReceived(buffer: ByteArray?) {}
                    override fun onEndOfSpeech() {}
                    override fun onError(error: Int) { fini.countDown() }
                    override fun onResults(results: Bundle?) {
                        texte = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()?.trim()
                        fini.countDown()
                    }
                    override fun onPartialResults(partialResults: Bundle?) {}
                    override fun onEvent(eventType: Int, params: Bundle?) {}
                })
                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, "fr-FR")
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                    putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1200L)
                    putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1000L)
                }
                reco?.startListening(intent)
            } catch (e: Exception) {
                fini.countDown()
            }
        }
        fini.await(delaiMs + 2000, TimeUnit.MILLISECONDS)
        principal.post { try { reco?.cancel() } catch (e: Exception) {} }
        if (silencieux) Thread.sleep(150)
        return texte?.takeIf { it.isNotBlank() }
    }

    fun fermer() {
        principal.post {
            try { reco?.destroy() } catch (e: Exception) {}
            reco = null
            bips(false)
        }
    }

    fun rendreLesBips() = principal.post { bips(false) }
}
