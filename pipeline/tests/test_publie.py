import communs as c
import publie


def article(rubrique, score, une=False):
    return {"rubrique": rubrique, "format": "breve", "titre": f"Titre {rubrique} {score}", "chapeau": "C.",
            "corps": "Corps.", "niveau_de_confiance": "partiel", "sources": [],
            "premiere_parution": "2026-09-10T08:00:00Z", "suite_de": None, "mots": 180, "modele": "factice",
            "a_la_une": une, "score": score, "cluster": "x", "avertissements": []}


def test_construire_edition():
    articles = [article("monde", 1.0), article("monde", 3.0, une=True), article("sport", 5.0, une=True)]
    edition = publie.construire_edition(articles, "2026-09-11", "2026-09-11T01:40:00Z")
    assert [a["id"] for a in edition["articles"]] == ["2026-09-11-monde-001", "2026-09-11-monde-002",
                                                      "2026-09-11-sport-001"]
    assert edition["une"] == ["2026-09-11-sport-001", "2026-09-11-monde-001"]
    assert "score" not in edition["articles"][0] and "avertissements" not in edition["articles"][0]
    assert edition["rubriques"][0] == {"id": "une", "nom": "À la une"}


def test_publier_ecrit_edition_et_index(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "DOCS", tmp_path)
    monkeypatch.setattr(c, "EDITIONS", tmp_path / "editions")
    publie.publier([article("monde", 2.0, une=True)], "2026-09-11")
    assert (tmp_path / "editions" / "2026-09-11.json").exists()
    index = c.lire_json(tmp_path / "index.json")
    assert index["derniere"] == "2026-09-11"
    assert index["editions"][0]["une"] == ["Titre monde 2.0"]
    assert (tmp_path / "robots.txt").exists() and (tmp_path / ".nojekyll").exists()
