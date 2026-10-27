package fr.eva.satellite

/** Mêmes règles que le satellite PC : mot d'éveil « EVA » et phrases inventées par Whisper sur du bruit. */
object Texte {
    private val eveil = Regex(
        "^\\W*(?:(?:hey|h[eé]|dis|ok|okay|bonjour|salut|coucou)\\W+)?(?:[eé]h?\\W*)?[eé]+v(?:a|ah|ha|e)\\b[\\s,.!?:;-]*",
        RegexOption.IGNORE_CASE
    )
    private val hallucinations = listOf(
        "sous-?titr", "amara\\.org", "merci d'avoir regard", "abonne", "^\\W*merci\\W*$",
        "^\\W*(?:\\.{2,}|…|♪+)\\W*$", "^\\W*(?:euh+|hum+|hmm+|ah+|oh+)\\W*$"
    ).map { Regex(it, RegexOption.IGNORE_CASE) }

    /** « EVA, allume la cuisine » → « Allume la cuisine » ; « EVA » seul → "" ; pas de mot d'éveil → null. */
    fun commandeApresEveil(texte: String): String? {
        val m = eveil.find(texte) ?: return null
        if (m.range.first != 0) return null
        val reste = texte.substring(m.range.last + 1).trim()
        return if (reste.isEmpty()) "" else reste.substring(0, 1).uppercase() + reste.substring(1)
    }

    fun hallucination(texte: String?): Boolean {
        val t = texte?.trim() ?: return true
        return t.length < 2 || hallucinations.any { it.containsMatchIn(t) }
    }
}
