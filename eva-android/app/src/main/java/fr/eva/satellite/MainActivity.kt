package fr.eva.satellite

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.core.content.pm.PackageInfoCompat

private val Or = Color(0xFFFFC857)
private val Fond = Color(0xFF1B1F3B)
private val Carte = Color(0xFF262B52)

class MainActivity : ComponentActivity() {
    private lateinit var reglages: Reglages
    private val permissions = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { res ->
        if (res[Manifest.permission.RECORD_AUDIO] == true) SatelliteService.lancer(this)
        else Toast.makeText(this, "Sans le micro, EVA ne peut pas t'entendre.", Toast.LENGTH_LONG).show()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        reglages = Reglages(this)
        lienRecu(intent)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Or, background = Fond, surface = Carte)) {
                Ecran(reglages, ::demarrer, ::parler)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        lienRecu(intent)
    }

    private fun lienRecu(i: Intent?) {
        if (reglages.depuisLien(i?.data)) {
            Toast.makeText(this, "Satellite configuré : connexion à EVA…", Toast.LENGTH_LONG).show()
            SatelliteService.lancer(this, SatelliteService.ARRETER)
            demarrer()
        }
    }

    fun demarrer() {
        val manque = mutableListOf<String>()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) manque.add(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            manque.add(Manifest.permission.POST_NOTIFICATIONS)
        if (manque.isEmpty()) SatelliteService.lancer(this) else permissions.launch(manque.toTypedArray())
    }

    fun parler() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) { demarrer(); return }
        SatelliteService.lancer(this, SatelliteService.PARLER)
    }
}

@Composable
private fun Ecran(reglages: Reglages, demarrer: () -> Unit, parler: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val actif by Etat.actif.collectAsState()
    val statut by Etat.statut.collectAsState()
    val satellite by Etat.satellite.collectAsState()
    val toi by Etat.toi.collectAsState()
    val eva by Etat.eva.collectAsState()
    val lignes by Etat.lignes.collectAsState()
    val maj by Etat.majDisponible.collectAsState()
    var pret by remember { mutableStateOf(reglages.pret) }
    var adresse by remember { mutableStateOf(reglages.eva.ifEmpty { "https://192.168.1.10:8443" }) }
    var cle by remember { mutableStateOf(reglages.jeton) }
    var mainsLibres by remember { mutableStateOf(reglages.mainsLibres) }
    var enCharge by remember { mutableStateOf(reglages.seulementEnCharge) }
    var voixEva by remember { mutableStateOf(reglages.voixEva) }
    var ecouteTel by remember { mutableStateOf(reglages.ecouteTelephone) }
    var journal by remember { mutableStateOf(false) }
    if (!pret && reglages.pret) pret = true

    Column(Modifier.fillMaxSize().background(Fond).verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("EVA", color = Or, fontSize = 34.sp, fontWeight = FontWeight.Bold)
        Text(if (satellite.isNotEmpty()) "Satellite « $satellite »" else "Satellite de la maison", color = Color.White.copy(alpha = .8f))

        if (maj > 0) {
            Card(colors = CardDefaults.cardColors(containerColor = Or)) {
                Column(Modifier.padding(14.dp)) {
                    Text("Nouvelle version de l'appli disponible", color = Fond, fontWeight = FontWeight.Bold)
                    TextButton(onClick = {
                        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(reglages.eva + "/api/public/satellite/eva-satellite.apk")))
                    }) { Text("Télécharger et installer", color = Fond) }
                }
            }
        }

        if (!pret) {
            Card(colors = CardDefaults.cardColors(containerColor = Carte)) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Relier ce téléphone à EVA", color = Color.White, fontWeight = FontWeight.Bold)
                    Text("Dans EVA : Maison › Satellites › Ajouter, choisis Android, puis touche « Ouvrir dans l'appli » sur ce téléphone " +
                        "(ou scanne le QR code). Sinon, recopie l'adresse et la clé ici.", color = Color.White.copy(alpha = .75f), fontSize = 14.sp)
                    OutlinedTextField(adresse, { adresse = it }, label = { Text("Adresse d'EVA") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(cle, { cle = it }, label = { Text("Clé du satellite (evasat_…)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Button(onClick = {
                        reglages.eva = adresse; reglages.jeton = cle; reglages.certificat = ""
                        if (reglages.pret) { pret = true; demarrer() } else Toast.makeText(ctx, "Adresse (https://…) ou clé (evasat_…) invalide.", Toast.LENGTH_LONG).show()
                    }) { Text("Enregistrer et démarrer") }
                }
            }
            return@Column
        }

        Card(colors = CardDefaults.cardColors(containerColor = Carte), shape = RoundedCornerShape(18.dp)) {
            Column(Modifier.padding(18.dp).fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(statut, color = Color.White)
                Button(onClick = parler, shape = CircleShape, modifier = Modifier.size(150.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Or, contentColor = Fond)) {
                    Text("🎙️\nParler", fontSize = 22.sp, fontWeight = FontWeight.Bold)
                }
                if (toi.isNotEmpty()) Text("Toi : $toi", color = Color.White.copy(alpha = .8f))
                if (eva.isNotEmpty()) Text("EVA : $eva", color = Or)
            }
        }

        Card(colors = CardDefaults.cardColors(containerColor = Carte)) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Reglage("Écoute « EVA… » (mains libres)", "Désactive pour couper le micro ; le bouton Parler marche toujours. Consomme de la batterie.", mainsLibres) {
                    mainsLibres = it; reglages.mainsLibres = it
                }
                Reglage("Seulement quand le téléphone est en charge", "Idéal pour un vieux téléphone posé dans une pièce.", enCharge) {
                    enCharge = it; reglages.seulementEnCharge = it
                }
                Reglage("Reconnaissance du téléphone (Google)", "Comprend bien mieux. Sinon : celle d'EVA, sur ton serveur (rien ne part chez Google).", ecouteTel) {
                    ecouteTel = it; reglages.ecouteTelephone = it
                }
                Reglage("Voix d'EVA", "Sinon : la voix du téléphone, plus naturelle et instantanée.", voixEva) {
                    voixEva = it; reglages.voixEva = it
                }
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (actif) OutlinedButton(onClick = { SatelliteService.lancer(ctx, SatelliteService.ARRETER) }) { Text("Arrêter") }
            else Button(onClick = demarrer) { Text("Démarrer") }
            OutlinedButton(onClick = { journal = !journal }) { Text(if (journal) "Masquer le journal" else "Journal") }
        }
        if (journal) {
            Card(colors = CardDefaults.cardColors(containerColor = Carte)) {
                Column(Modifier.padding(12.dp)) { lignes.forEach { Text(it, color = Color.White.copy(alpha = .75f), fontSize = 12.sp) } }
            }
        }
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = {
            SatelliteService.lancer(ctx, SatelliteService.ARRETER)
            reglages.jeton = ""; reglages.certificat = ""; pret = false
        }) { Text("Oublier ce satellite (changer d'adresse ou de clé)", color = Color.White.copy(alpha = .6f)) }
        Text("Version " + PackageInfoCompat.getLongVersionCode(ctx.packageManager.getPackageInfo(ctx.packageName, 0)) +
            " · Pour désinstaller : appui long sur l'icône › Désinstaller, puis supprime le satellite dans EVA.",
            color = Color.White.copy(alpha = .45f), fontSize = 12.sp)
    }
}

@Composable
private fun Reglage(titre: String, aide: String, valeur: Boolean, change: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.weight(1f)) {
            Text(titre, color = Color.White)
            Text(aide, color = Color.White.copy(alpha = .6f), fontSize = 12.sp)
        }
        Switch(valeur, change)
    }
}
