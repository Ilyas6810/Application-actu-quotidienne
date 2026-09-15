from datetime import datetime

import controle


def test_typographie():
    assert controle.corriger_typographie("Le président — absent — a parlé.") == "Le président, absent, a parlé."
    assert controle.corriger_typographie("— Début de ligne") == "Début de ligne"
    assert controle.corriger_typographie("La saison 2025–2026") == "La saison 2025–2026"
    assert controle.corriger_typographie("un **mot** en gras") == "un mot en gras"


PHRASE = "Le gouvernement a annoncé hier une réforme des retraites qui concerne tous les salariés du secteur privé"


def test_copie_detectee():
    assert controle.passages_copies(f"Selon nos informations. {PHRASE}.", [PHRASE], 12, 15)


def test_citation_courte_toleree():
    source = "Le ministre a dit nous allons réformer les retraites pour tous les salariés dès cette année"
    article = "Le ministre a été clair : « nous allons réformer les retraites pour tous les salariés » a-t-il dit."
    assert controle.passages_copies(article, [source], 12, 15) == []


def test_mots_interdits_et_exceptions():
    assert controle.mots_interdits_trouves("Une réforme historique a été votée.") == ["historique"]
    assert controle.mots_interdits_trouves("Le Massif central est sous la neige.") == []
    assert controle.mots_interdits_trouves("Un incendie massif ravage la forêt.") == ["massif"]
    assert controle.mots_interdits_trouves("Il a été annoncé que les écoles ferment.") == ["Il a été annoncé"]
    assert controle.mots_interdits_trouves("Le monument historique a rouvert.") == []


FORMATS = {"breve": {"min": 150, "max": 250}, "standard": {"min": 400, "max": 600}, "fond": {"min": 800, "max": 1000}}


def test_format_selon_longueur():
    assert controle.format_selon_longueur(500, "standard", FORMATS, 0.1) == "standard"
    assert controle.format_selon_longueur(230, "standard", FORMATS, 0.1) == "breve"
    assert controle.format_selon_longueur(300, "standard", FORMATS, 0.1) == "breve"  # entre deux formats
    assert controle.format_selon_longueur(345, "standard", FORMATS, 0.1) == "standard"
    assert controle.format_selon_longueur(340, "breve", FORMATS, 0.1) == "breve"  # jamais au-dessus
    assert controle.format_selon_longueur(700, "fond", FORMATS, 0.1) == "standard"
    assert controle.format_selon_longueur(650, "fond", FORMATS, 0.1) == "standard"
    assert controle.format_selon_longueur(900, "standard", FORMATS, 0.1) is None


def test_titre():
    assert controle.erreurs_titre("Le gouvernement espagnol annonce un plan pour le logement") == []
    assert len(controle.erreurs_titre("Le plus grand incendie de l'année !")) == 2
    assert controle.erreurs_titre("Pourquoi les prix montent-ils ?")
    assert controle.erreurs_titre("Une découverte rarissime au Chili")
    assert controle.erreurs_titre("Le Premier ministre présente son budget") == []


def test_interpretations_des_nombres():
    assert controle.interpretations("12 000") == {12000.0}
    assert controle.interpretations("12" + chr(0xA0) + "000") == {12000.0}
    assert controle.interpretations("3,5") == {3.5}
    assert controle.interpretations("1,200") == {1.2, 1200.0}
    assert controle.interpretations("1.234,5") == {1234.5}


def test_nombres_absents_des_sources():
    sources = ["The toll rose to 1,450 dead on Tuesday, officials said. Prices rose 11 percent."]
    assert controle.nombres_non_sources("Le bilan atteint 1 450 morts.", sources, []) == []
    assert controle.nombres_non_sources("Les prix ont augmenté de 12 %.", sources, []) == ["12"]
    assert controle.nombres_non_sources("Trois blessés, 3 morts, au 1er étage.", sources, []) == []
    assert controle.nombres_non_sources("Le traité date de 2019.", sources, []) == ["2019"]
    assert controle.nombres_non_sources("Le 15 septembre.", sources, [datetime(2026, 9, 15, 8, 30)]) == []
    assert controle.nombres_non_sources("Un budget de 2,5 milliards.", ["a budget of 2.5 billion"], []) == []


def test_article_conforme():
    article = {
        "titre": "Les autorités confirment les faits dans un communiqué publié mardi",
        "chapeau": "Les autorités ont publié un communiqué mardi. Il confirme les faits.",
        "corps": " ".join(["Les autorités ont confirmé les faits dans un communiqué."] * 50),
        "sources": [{"nom": "A", "url": "https://a.fr/1"}, {"nom": "B", "url": "https://b.fr/2"}],
        "liens_inventes": [],
    }
    contexte = {"textes": ["Une source sans rapport avec le texte."], "dates": [], "officiel_competent": False}
    verdict = controle.verifier(article, contexte, "standard")
    assert verdict.ok, verdict.erreurs
    assert verdict.format == "standard"


def test_chiffre_et_liens_inventes_refuses():
    article = {
        "titre": "Un séisme frappe la région et fait des dégâts importants",
        "chapeau": "Un séisme a frappé la région lundi. Le bilan fait état de 42 morts.",
        "corps": " ".join(["Les secours sont sur place depuis lundi soir."] * 20),
        "sources": [{"nom": "A", "url": "https://a.fr/1"}],
        "liens_inventes": ["https://invente.example/x"],
    }
    contexte = {"textes": ["Earthquake hits the region, dozens killed."], "dates": [], "officiel_competent": False}
    erreurs = " ".join(controle.verifier(article, contexte, "breve").erreurs)
    assert "42" in erreurs
    assert "liens absents" in erreurs
    assert "moins de 2 liens" in erreurs
