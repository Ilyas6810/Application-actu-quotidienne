from datetime import datetime, timezone

import communs as c


def test_url_canonique_retire_suivi_et_fragment():
    brute = "https://www.lemonde.fr/international/article/x_123.html?xtor=RSS-3208&utm_source=rss#suite"
    assert c.url_canonique(brute) == "https://lemonde.fr/international/article/x_123.html"


def test_url_canonique_normalise_hote_et_barre_finale():
    assert c.url_canonique("http://BBC.co.uk/news/world-123/") == "https://bbc.co.uk/news/world-123"
    assert c.url_canonique("https://exemple.org/article/amp") == "https://exemple.org/article"


def test_url_canonique_garde_les_parametres_utiles():
    assert c.url_canonique("https://site.com/page?utm_medium=x&id=5") == "https://site.com/page?id=5"


def test_nettoyer_html():
    assert c.nettoyer_html("<p>Bonjour&nbsp;<b>le</b>   monde&amp;co</p>") == "Bonjour le monde&co"


def test_compter_mots_apostrophes_et_traits_d_union():
    assert c.compter_mots("L'Élysée a peut-être annoncé 22 % de hausse.") == 7


def test_tronquer_sur_une_frontiere_de_mot():
    assert c.tronquer("un deux trois quatre", 10) == "un deux…"
    assert c.tronquer("court", 10) == "court"


def test_dates():
    moment = datetime(2026, 9, 11, 1, 40, tzinfo=timezone.utc)
    assert c.iso(moment) == "2026-09-11T01:40:00Z"
    assert c.lire_date("2026-09-11T01:40:00Z") == moment
    assert c.lire_date("pas une date") is None


def test_date_locale_utc_plus_4():
    # 22 h UTC le 10 septembre = 2 h du matin le 11 à La Réunion
    assert c.date_locale(datetime(2026, 9, 10, 22, 0, tzinfo=timezone.utc)).isoformat() == "2026-09-11"


def test_pays_du_domaine():
    assert c.pays_du_domaine("elmundo.es") == "ES"
    assert c.pays_du_domaine("clicanoo.re") == "FR"
    assert c.pays_du_domaine("example.com") is None


CONF = {
    "sources": [
        {"nom": "BBC News", "groupe": "BBC", "sites": ["bbc.co.uk", "bbc.com"], "alias": ["BBC"]},
        {"nom": "Le Monde", "groupe": "Groupe Le Monde", "sites": ["lemonde.fr"], "alias": ["Le Monde"]},
    ],
    "agences": [{"nom": "AFP", "motifs": [r"\bAFP\b"], "sites": ["afp.com"]}],
}


def test_index_sources_par_domaine():
    index = c.IndexSources(CONF)
    assert index.source_du_domaine("news.bbc.co.uk")["nom"] == "BBC News"
    assert index.source_du_domaine("afp.com")["groupe"] == "AFP"
    assert index.source_du_domaine("co.uk") is None


def test_index_sources_agences_et_citations():
    index = c.IndexSources(CONF)
    assert index.agences_citees("Paris (AFP) - Le gouvernement a annoncé") == ["AFP"]
    assert index.agences_citees("une adresse afp.example") == []
    assert index.groupes_cites("selon la BBC, trois blessés", "Groupe Le Monde") == ["BBC"]
    assert index.groupes_cites("selon la BBC", "BBC") == []
    assert index.groupes_cites("le monde entier regarde", "BBC") == []


def test_configuration_des_sources():
    conf = c.charger_yaml("sources.yaml")
    noms = [s["nom"] for s in conf["sources"]]
    assert len(noms) == len(set(noms))
    for source in conf["sources"]:
        assert {"nom", "groupe", "type", "niveau"} <= source.keys(), source["nom"]
        for flux in source.get("flux", []):
            assert flux["url"].startswith("http"), source["nom"]
            assert flux.get("rubrique", "") in ("",) + c.RUBRIQUES, flux["url"]


def test_configuration_des_modeles():
    conf = c.charger_yaml("llm.yaml")
    assert conf["fournisseurs"]
    for fournisseur in conf["fournisseurs"]:
        assert {"nom", "base_url", "modele", "cle_env"} <= fournisseur.keys()


def test_url_canonique_deballe_une_redirection():
    emballee = "https://redir.folha.com.br/redir/online/mundo/rss091/*https://www1.folha.uol.com.br/mundo/2026/09/x.shtml"
    assert c.url_canonique(emballee) == "https://www1.folha.uol.com.br/mundo/2026/09/x.shtml"
