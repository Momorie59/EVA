"""Rayons du magasin : la liste de courses se range toute seule (fruits et légumes, crèmerie, boucherie…), comme on
fait ses courses, sans rien régler. Simple dictionnaire de mots ; ce qui n'est pas reconnu va dans « Divers »."""
import re
import unicodedata

ORDRE = ["Fruits et légumes", "Boulangerie", "Boucherie, poisson", "Crèmerie, œufs", "Frais", "Épicerie salée", "Épicerie sucrée",
         "Surgelés", "Boissons", "Bébé", "Hygiène, beauté", "Entretien, maison", "Animaux", "Divers"]

_MOTS = {
    "Fruits et légumes": "pomme poire banane orange citron clementine mandarine raisin fraise framboise myrtille cerise peche abricot prune kiwi "
                         "ananas mangue melon pasteque avocat tomate salade laitue mache roquette epinard carotte pomme de terre patate oignon "
                         "echalote ail poireau courgette aubergine poivron concombre radis chou brocoli chou-fleur haricot vert champignon "
                         "celeri fenouil navet betterave potiron butternut citrouille persil basilic coriandre ciboulette menthe thym gingembre legume fruit",
    "Boulangerie": "pain baguette brioche croissant pain de mie biscotte viennoiserie tortilla wrap pita",
    "Boucherie, poisson": "viande boeuf steak hache poulet dinde porc jambon lardon saucisse merguez chorizo agneau veau escalope roti "
                          "poisson saumon cabillaud thon crevette moule calamar seiche colin sardine truite lieu filet de poisson fruits de mer",
    "Crèmerie, œufs": "lait beurre creme fraiche creme yaourt yogourt fromage gruyere emmental comte mozzarella parmesan chevre feta ricotta "
                      "mascarpone camembert brie raclette oeuf oeufs skyr petit suisse fromage blanc",
    "Frais": "pate fraiche gnocchi quiche pizza fraiche houmous tapenade surimi traiteur",
    "Épicerie salée": "pates spaghetti riz semoule quinoa lentille pois chiche farine sel poivre huile vinaigre moutarde ketchup mayonnaise "
                      "sauce tomate concentre bouillon epice curry paprika conserve thon en boite mais olive cornichon chips cacahuete "
                      "soupe puree levure chapelure",
    "Épicerie sucrée": "sucre chocolat cacao cafe the tisane confiture miel nutella pate a tartiner cereale muesli biscuit gateau compote "
                       "levure chimique sucre vanille sirop bonbon",
    "Surgelés": "surgele glace frites congele poelee",
    "Boissons": "eau jus soda coca biere vin champagne limonade sirop cidre",
    "Bébé": "couche lingette bebe petit pot lait infantile",
    "Hygiène, beauté": "dentifrice brosse a dents shampoing gel douche savon deodorant coton mouchoir papier toilette rasoir creme solaire "
                       "serviette hygienique tampon",
    "Entretien, maison": "lessive adoucissant liquide vaisselle pastille lave-vaisselle eponge sac poubelle essuie-tout javel nettoyant "
                         "ampoule pile aluminium film alimentaire sopalin",
    "Animaux": "croquette patee litiere chat chien",
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower().replace("œ", "oe")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 -]+", " ", t)


# Expressions de plusieurs mots, cherchées en premier (« sauce tomate » n'est pas une tomate, « pomme de terre » pas une pomme).
_EXPR = {
    "pomme de terre": "Fruits et légumes", "haricot vert": "Fruits et légumes", "chou-fleur": "Fruits et légumes",
    "pain de mie": "Boulangerie", "steak hache": "Boucherie, poisson", "fruits de mer": "Boucherie, poisson", "filet de poisson": "Boucherie, poisson",
    "creme fraiche": "Crèmerie, œufs", "fromage blanc": "Crèmerie, œufs", "petit suisse": "Crèmerie, œufs",
    "pate fraiche": "Frais", "pizza fraiche": "Frais",
    "sauce tomate": "Épicerie salée", "concentre de tomate": "Épicerie salée", "pois chiche": "Épicerie salée", "thon en boite": "Épicerie salée",
    "pate a tartiner": "Épicerie sucrée", "levure chimique": "Épicerie sucrée", "sucre vanille": "Épicerie sucrée",
    "lait infantile": "Bébé", "petit pot": "Bébé",
    "papier toilette": "Hygiène, beauté", "gel douche": "Hygiène, beauté", "brosse a dents": "Hygiène, beauté", "creme solaire": "Hygiène, beauté",
    "liquide vaisselle": "Entretien, maison", "sac poubelle": "Entretien, maison", "film alimentaire": "Entretien, maison",
    "essuie-tout": "Entretien, maison", "pastille lave-vaisselle": "Entretien, maison",
}
_INDEX: list[tuple[str, str]] = sorted(((mot, r) for r, mots in _MOTS.items() for mot in mots.split()), key=lambda x: -len(x[0]))


def rayon(texte: str) -> str:
    t = f" {_norm(texte)} "
    for expr, r in sorted(_EXPR.items(), key=lambda x: -len(x[0])):
        if re.search(rf"(?<![a-z]){re.escape(expr).replace(' ', 's? ')}s?(?![a-z])", t):
            return r
    for mot, r in _INDEX:
        if re.search(rf"(?<![a-z]){re.escape(mot)}s?(?![a-z])", t):
            return r
    return "Divers"


def ranger(textes: list[str]) -> list[tuple[str, list[str]]]:
    groupes: dict[str, list[str]] = {}
    for x in textes:
        groupes.setdefault(rayon(x), []).append(x)
    return [(r, groupes[r]) for r in ORDRE if r in groupes]
