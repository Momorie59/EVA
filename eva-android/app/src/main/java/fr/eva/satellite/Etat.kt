package fr.eva.satellite

import kotlinx.coroutines.flow.MutableStateFlow
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Ce que l'écran de l'appli affiche (mis à jour par le service, lu par l'interface). */
object Etat {
    val actif = MutableStateFlow(false)
    val statut = MutableStateFlow("Arrêté")
    val satellite = MutableStateFlow("")
    val toi = MutableStateFlow("")
    val eva = MutableStateFlow("")
    val ecoute = MutableStateFlow(false)
    val majDisponible = MutableStateFlow(0)
    val lignes = MutableStateFlow<List<String>>(emptyList())
    @Volatile var arretSonnerie = false

    private val heure = SimpleDateFormat("HH:mm:ss", Locale.FRANCE)

    fun journal(t: String) {
        lignes.value = (listOf("${heure.format(Date())}  $t") + lignes.value).take(40)
    }
}
