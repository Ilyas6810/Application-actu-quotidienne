from datetime import date

import pytest

import communs as c
import llm
import redaction


@pytest.fixture(autouse=True)
def isoler(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "USAGE", tmp_path / "llm_usage.json")
    monkeypatch.setattr(c, "EDITIONS", tmp_path / "editions")


def test_la_charte_est_celle_du_cahier():
    assert redaction.CHARTE.startswith("Tu es rédacteur dans un quotidien de référence.")
    assert "ARTICLE_IMPOSSIBLE" in redaction.CHARTE
    assert redaction.CHARTE.endswith("sources (liste de {nom, url}).")


def test_extraire_json_tolerant():
    assert redaction.extraire_json('```json\n{"titre": "a"}\n```') == {"titre": "a"}
    assert redaction.extraire_json('Voici l\'article : {"titre": "b"} Bonne lecture.') == {"titre": "b"}
    assert redaction.extraire_json('<think>réflexion</think>{"titre": "c"}') == {"titre": "c"}
    assert redaction.extraire_json('{"corps": "ligne 1\nligne 2"}')["corps"] == "ligne 1\nligne 2"
    with pytest.raises(ValueError):
        redaction.extraire_json("ARTICLE_IMPOSSIBLE")


ITEMS = [
    {"id": "a", "url": "https://a.fr/1", "titre": "Titre A", "resume": "Résumé A", "source": "Source A",
     "groupe": "A", "date": "2026-09-10T08:00:00Z", "niveau": 1, "pays": "FR", "langue": "fr"},
    {"id": "b", "url": "https://b.co.uk/2", "titre": "Title B", "resume": "Summary B", "source": "Source B",
     "groupe": "B", "date": "2026-09-10T09:00:00Z", "niveau": 1, "pays": "GB", "langue": "en"},
]


def test_normaliser_sources_et_intertitre():
    brut = {
        "titre": "Un titre — avec tiret.",
        "chapeau": "Premier.\nSecond.",
        "corps": "Paragraphe un.\n\nCe que disent les sources\nVersion A.\n\n## Autre",
        "sources": [{"nom": "Source B", "url": "https://www.b.co.uk/2/"}, {"nom": "X", "url": "https://invente.fr"}],
        "niveau_de_confiance": "contesté",
    }
    article = redaction.normaliser(brut, ITEMS)
    assert article["titre"] == "Un titre, avec tiret"
    assert article["chapeau"] == "Premier. Second."
    assert "## Ce que disent les sources" in article["corps"].split("\n\n")
    assert [s["nom"] for s in article["sources"]] == ["Source B", "Source A"]
    assert article["liens_inventes"] == ["https://invente.fr"]
    assert article["niveau_llm"] == "conteste"


def test_niveau_de_confiance():
    assert redaction.niveau_de_confiance({"independants": 3}, "partiel") == "confirme"
    assert redaction.niveau_de_confiance({"independants": 2}, "confirme") == "partiel"
    assert redaction.niveau_de_confiance({"independants": 1, "officiel_competent": True}, "") == "confirme"
    assert redaction.niveau_de_confiance({"independants": 5}, "conteste") == "conteste"


def sujet(identifiant, rubrique, score, independants=2):
    return {"id": identifiant, "rubrique": rubrique, "score": score, "independants": independants,
            "publiable": True, "officiel_competent": False, "items": [], "titre": f"Sujet {identifiant}",
            "premiere_parution": "2026-09-10T08:00:00Z"}


def test_selection_quotas_une_et_formats():
    clusters = [sujet(f"s{i}", "sport", 10 - i * 0.1, independants=6) for i in range(5)]
    clusters += [sujet("m1", "monde", 20, independants=6), sujet("m2", "monde", 0.1)]
    clusters.sort(key=lambda s: s["score"], reverse=True)
    retenus = redaction.selectionner(clusters, {}, redaction.Historique(date(2026, 9, 11), 14))
    assert "m2" not in {s["id"] for s in retenus}  # sous le score minimal
    assert sum(1 for s in retenus if s["rubrique"] == "sport") == 3  # plafond Sport
    m1 = next(s for s in retenus if s["id"] == "m1")
    assert m1["a_la_une"] and m1["format"] == "fond"


def test_rediger_un_article_avec_le_modele_factice():
    pool = {it["id"]: it for it in ITEMS}
    s = sujet("a", "monde", 3.0)
    s.update(items=["a", "b"], format="breve")
    cascade = llm.Cascade.depuis_config(factice=True)
    article, raison = redaction.rediger_article(s, pool, cascade, date(2026, 9, 10))
    assert article is not None, raison
    assert article["format"] == "breve"
    assert len(article["sources"]) == 2
    assert article["niveau_de_confiance"] == "partiel"


def test_normaliser_repare_un_lien_mal_recopie():
    items = [
        {"url": "https://www.liberation.fr/international/trump-plaidant-pour-une-irlande-unifiee-20260912_MWHT/",
         "source": "Libération"},
        {"url": "https://www.bbc.com/news/articles/c0ab12", "source": "BBC News"},
    ]
    brut = {"titre": "Titre", "chapeau": "Chapeau.", "corps": "Corps.", "sources": [
        {"nom": "Libération", "url": "https://liberation.fr/international/trump-plaidant-for-une-irlande-unifiee-20260912_MWHT"},
        {"nom": "Inconnu", "url": "https://exemple.org/tout-autre-chose"},
    ]}
    article = redaction.normaliser(brut, items)
    assert article["liens_inventes"] == ["https://exemple.org/tout-autre-chose"]
    assert article["sources"][0]["nom"] == "Libération"


def test_reponse_tronquee_refusee():
    class Faux:
        def json(self):
            return {"choices": [{"message": {"content": '{"titre": "coup'}, "finish_reason": "length"}]}

    with pytest.raises(llm.ErreurFournisseur):
        llm.Fournisseur._lire(Faux())


def test_quota_du_jour_reconnu_au_bout_du_message(monkeypatch):
    class Reponse429:
        status_code = 429
        headers = {}
        text = ('{"error": {"message": "' + "x" * 600 + '", "details": '
                '[{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}')

    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: Reponse429())
    f = llm.Fournisseur({"nom": "g", "base_url": "http://x", "modele": "m", "cle_env": "CLE_ABSENTE"}, {})
    with pytest.raises(llm.QuotaEpuise):
        f.appeler([{"role": "user", "content": "x"}], False, 10)
