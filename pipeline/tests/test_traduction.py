import llm
import publie
import traduction


def article(ident, titre, chapeau, corps):
    return {"id": ident, "rubrique": "monde", "titre": titre, "chapeau": chapeau, "corps": corps}


def test_lots_par_nombre_de_mots():
    articles = [article(f"a{i}", "Titre court", "Chapeau court.", "mot " * 300) for i in range(5)]
    assert [len(lot) for lot in traduction.lots(articles, mots_max=700)] == [2, 2, 1]


def test_nombres_insensibles_aux_separateurs():
    assert traduction.nombres("30 000 personnes, 2,5 % et 14 h 30") == traduction.nombres("30,000 people, 2.5% and 14:30")


def test_traduction_qui_perd_un_nombre_refusee():
    fr = article("x", "Un ferry chavire", "Six morts.", "Le bilan est de 6 morts et 130 disparus.")
    en = {"titre": "A ferry capsizes", "chapeau": "Six dead.", "corps": "The toll is 6 dead and many missing."}
    assert any("130" in e for e in traduction.erreurs(fr, en))


def test_intertitre_normalise():
    en = traduction.normaliser({"titre": "T.", "chapeau": "C", "corps": "A.\n\nWhat the sources say:\n\nB."})
    assert en["corps"] == "A.\n\n## What the sources say\n\nB."
    assert en["titre"] == "T"


def test_traduire_avec_le_modele_factice():
    articles = [
        article("a1", "Titre un", "Chapeau un.", "Corps 12.\n\n## Ce que disent les sources\n\nVersion A."),
        article("a2", "Titre deux", "Chapeau deux.", "Corps 34."),
    ]
    assert traduction.traduire(articles, llm.Cascade.depuis_config(factice=True)) == 2
    assert articles[0]["en"]["titre"] == "[EN] Titre un"
    assert "## What the sources say" in articles[0]["en"]["corps"]


def test_publication_garde_la_traduction():
    a = article("", "T", "C", "X")
    a["en"] = {"titre": "T en", "chapeau": "C en", "corps": "X en"}
    edition = publie.construire_edition([a], "2026-09-14", "2026-09-14T00:00:00Z")
    assert edition["articles"][0]["en"]["titre"] == "T en"
