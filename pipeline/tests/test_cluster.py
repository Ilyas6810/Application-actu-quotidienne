import numpy as np

import cluster
import communs as c


def item(identifiant, groupe, niveau=1, agences=(), cites=(), rubrique="", titre="Titre", langue="fr"):
    maintenant = c.iso(c.maintenant())
    return {"id": identifiant, "url": f"https://{identifiant}.example/a", "titre": titre, "resume": "",
            "date": maintenant, "vu_le": maintenant, "langue": langue, "source": groupe, "groupe": groupe,
            "pays": "FR", "niveau": niveau, "type": "presse", "rubrique_flux": rubrique,
            "agences": list(agences), "cites": list(cites), "via": "rss"}


def test_independance_groupes_agences_citations():
    items = [
        item("a", "BBC"), item("b", "Guardian Media Group"),
        item("c", "Groupe Le Monde", agences=["AFP"]), item("d", "Groupe Figaro", agences=["AFP"]),
        item("e", "France Médias Monde"), item("f", "France Médias Monde"),
        item("g", "Libération", cites=["BBC"]),
        item("h", "exemple.es", niveau=2),
    ]
    # BBC + Libération (citation), Guardian, Le Monde + Figaro (même dépêche AFP), France 24 + RFI (même groupe)
    assert len(cluster.composantes_independantes(items)) == 4


def test_classement_des_rubriques():
    assert cluster.classer([item("a", "A", rubrique="monde"), item("b", "B", rubrique="france"),
                            item("c", "C", rubrique="france")]) == "france"
    assert cluster.classer([item("a", "A", rubrique="economie"), item("b", "B", rubrique="economie")]) == "economie"
    guerre = "Nouvelles frappes de drones sur la capitale, l'armée riposte"
    assert cluster.classer([item("a", "A", rubrique="monde", titre=guerre),
                            item("b", "B", rubrique="monde", titre=guerre)]) == "geopolitique"
    assert cluster.classer([item("a", "A", titre="Le PSG remporte le match de Ligue des champions")]) == "sport"
    # Le mot-outil « des » ne doit pas suffire à classer en Sport.
    assert cluster.classer([item("a", "A", titre="La hausse des loyers inquiète les locataires")]) != "sport"


def test_regrouper_deux_groupes():
    matrice = np.array([[1, .9, .1, .1], [.9, 1, .1, .1], [.1, .1, 1, .8], [.1, .1, .8, 1]], dtype=np.float32)
    etiquettes = cluster.regrouper(matrice, 0.45)
    assert etiquettes[0] == etiquettes[1]
    assert etiquettes[2] == etiquettes[3]
    assert etiquettes[0] != etiquettes[2]


def test_tfidf_rapproche_un_meme_evenement():
    textes = ["Un séisme de magnitude 7 frappe le nord du Chili", "Le nord du Chili frappé par un fort séisme",
              "La BCE relève ses taux directeurs d'un quart de point"]
    matrice = cluster.matrice_tfidf(textes)
    assert matrice[0, 1] > 0.3
    assert matrice[0, 2] < 0.1


def test_construire_sur_un_petit_pool():
    titres = {
        "a": ("Un séisme de magnitude 7 frappe le nord du Chili", "Groupe Le Monde"),
        "b": ("Le nord du Chili frappé par un fort séisme de magnitude 7", "Groupe Figaro"),
        "c": ("La BCE relève ses taux directeurs d'un quart de point", "Groupe Le Monde"),
    }
    pool = {k: item(k, groupe, titre=titre) for k, (titre, groupe) in titres.items()}
    clusters = cluster.construire(pool, methode="tfidf")
    groupes = sorted(sorted(cl["items"]) for cl in clusters)
    assert ["a", "b"] in groupes
    assert ["c"] in groupes
    seisme = next(cl for cl in clusters if sorted(cl["items"]) == ["a", "b"])
    assert seisme["independants"] == 2 and seisme["publiable"]
