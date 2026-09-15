import time
from datetime import datetime, timedelta, timezone

import collecte
import communs as c
import portail_wikipedia
import radar_gdelt

REGLAGES = {"longueur_resume": 700, "age_max_heures": 72}
SOURCE = {"nom": "Le Monde", "groupe": "Groupe Le Monde", "langue": "fr", "pays": "FR", "niveau": 1, "type": "presse"}


def test_construire_item_normalise_une_entree():
    index = c.IndexSources({"sources": [], "agences": [{"nom": "AFP", "motifs": [r"\bAFP\b"]}]})
    vu_le = c.maintenant()
    entree = {"link": "https://www.lemonde.fr/a.html?xtor=RSS-1", "title": "Titre &amp; suite",
              "summary": "<p>Un résumé (AFP).</p>", "published_parsed": time.gmtime(vu_le.timestamp() - 3600)}
    item = collecte.construire_item(SOURCE, {"url": "u", "rubrique": "monde"}, entree, vu_le, REGLAGES, index)
    assert item["url"] == "https://lemonde.fr/a.html"
    assert item["titre"] == "Titre & suite"
    assert item["agences"] == ["AFP"]
    assert item["rubrique_flux"] == "monde" and not item["date_estimee"]
    vieille = dict(entree, published_parsed=time.gmtime(vu_le.timestamp() - 80 * 3600))
    assert collecte.construire_item(SOURCE, {"url": "u"}, vieille, vu_le, REGLAGES, index) is None


def test_fusion_le_rss_l_emporte_et_garde_la_premiere_vue():
    pool = {"x": {"id": "x", "via": "wikipedia", "date": "2026-09-10T08:00:00Z", "vu_le": "2026-09-10T08:00:00Z",
                  "resume": "texte du portail", "resume_de": "Wikipédia", "rubrique_flux": "monde"}}
    rss = {"id": "x", "via": "rss", "date": "2026-09-10T09:00:00Z", "date_estimee": True,
           "vu_le": "2026-09-10T10:00:00Z", "resume": "vrai résumé", "rubrique_flux": ""}
    assert collecte.fusionner(pool, [rss]) == 0
    assert pool["x"]["via"] == "rss" and "resume_de" not in pool["x"]
    assert pool["x"]["vu_le"] == "2026-09-10T08:00:00Z"
    assert pool["x"]["date"] == "2026-09-10T08:00:00Z"  # date estimée : la première vue fait foi
    assert pool["x"]["rubrique_flux"] == "monde"


HTML_PORTAIL = """<div class="current-events-content description">
<p><b>Armed conflicts and attacks</b></p>
<ul><li><a href="/wiki/Conflict">Some conflict</a>
<ul><li>Troops advance near the border, officials say. <a rel="nofollow" class="external text" href="https://www.reuters.com/world/x">(Reuters)</a> <a rel="nofollow" class="external text" href="https://www.bbc.com/news/y">(BBC)</a></li></ul>
</li></ul>
<p><b>Sports</b></p>
<ul><li>The national team wins the regional championship final in the capital. <a rel="nofollow" class="external text" href="https://apnews.com/article/z">(AP)</a></li></ul>
</div>"""


def test_portail_wikipedia_extrait_les_evenements():
    evenements = portail_wikipedia.evenements(HTML_PORTAIL)
    assert len(evenements) == 2
    premier = evenements[0]
    assert premier["categorie"] == "armed conflicts and attacks"
    assert premier["sujets"] == ["Some conflict"]
    assert premier["texte"] == "Troops advance near the border, officials say."
    assert premier["urls"] == ["https://www.reuters.com/world/x", "https://www.bbc.com/news/y"]
    assert evenements[1]["categorie"] == "sports"


def test_premiere_phrase():
    texte = "A long first sentence about events. Second one here."
    assert portail_wikipedia.premiere_phrase(texte) == "A long first sentence about events."


def mention(evenement, domaine, url, langue="srclc:spa;eng:GT-SPA 1.0"):
    return [evenement, "20260910120000", "20260910121500", "1", domaine, url, "1", "", "", "", "1", "80",
            "1000", "0", langue, ""]


def test_radar_agrege_et_varie_les_pays():
    lignes = [
        mention("1", "site-a.es", "https://site-a.es/n1"),
        mention("1", "site-b.es", "https://site-b.es/n2"),
        mention("1", "site-c.fr", "https://site-c.fr/n3", langue=""),
        mention("2", "vieux.com", "https://vieux.com/x"),
    ]
    lignes[3][1] = "20250101000000"  # événement ancien, simplement recité
    reference = datetime(2026, 9, 10, 13, 0, tzinfo=timezone.utc)
    evenements = radar_gdelt.agreger(lignes, timedelta(days=3), reference)
    assert set(evenements) == {"1"}
    assert evenements["1"].domaines == {"site-a.es", "site-b.es", "site-c.fr"}
    index = c.IndexSources({"sources": [], "agences": []})
    choix = radar_gdelt.choisir_urls(evenements["1"], 3, index, {})
    assert [domaine for _, domaine, _ in choix] == ["site-a.es", "site-c.fr"]
    assert radar_gdelt.langue_de("srclc:spa;eng:GT-SPA 1.0") == "es"
    assert radar_gdelt.langue_de("") == "en"
