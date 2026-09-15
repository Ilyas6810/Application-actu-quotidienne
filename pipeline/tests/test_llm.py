import json
from types import SimpleNamespace

import pytest

import llm


class Faux(llm.Fournisseur):
    def __init__(self, nom, comportement):
        super().__init__({"nom": nom, "base_url": "http://faux", "modele": nom}, {})
        self.cle = "cle"
        self.comportement = comportement

    def attendre_creneau(self, jetons_estimes):
        pass

    def appeler(self, messages, json_mode, max_tokens):
        if self.comportement == "quota":
            raise llm.QuotaEpuise("quota du jour atteint")
        if self.comportement == "panne":
            raise llm.ErreurFournisseur("HTTP 400")
        return '{"titre": "ok"}', 10


@pytest.fixture(autouse=True)
def usage_temporaire(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "USAGE", tmp_path / "llm_usage.json")


def test_cascade_passe_au_suivant():
    premier, second = Faux("premier", "quota"), Faux("second", "ok")
    reponse = llm.Cascade([premier, second]).completer("système", "consigne")
    assert reponse.fournisseur == "second"
    assert premier.epuise and not premier.disponible()


def test_cascade_epuisee():
    with pytest.raises(llm.AucunFournisseur):
        llm.Cascade([Faux("a", "panne"), Faux("b", "quota")]).completer("s", "u")


def test_fournisseur_sans_cle_ignore(monkeypatch):
    monkeypatch.delenv("CLE_ABSENTE", raising=False)
    fournisseur = llm.Fournisseur({"nom": "x", "base_url": "http://x", "modele": "m", "cle_env": "CLE_ABSENTE"}, {})
    assert not fournisseur.disponible()


def test_attente_conseillee():
    assert llm.attente_conseillee(SimpleNamespace(headers={"retry-after": "7"}, text="")) == 7.0
    assert llm.attente_conseillee(SimpleNamespace(headers={}, text='{"retryDelay": "33s"}')) == 33.0
    assert llm.attente_conseillee(SimpleNamespace(headers={}, text="Please try again in 1m23.5s.")) == 83.5


def test_quota_journalier_reconnu():
    assert llm._QUOTA_JOUR.search("Rate limit reached on tokens per day (TPD)")
    assert llm._QUOTA_JOUR.search("GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    assert not llm._QUOTA_JOUR.search("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")


def test_modele_factice():
    consignes = "Rubrique : monde\nFormat : breve, de 150 à 250 mots\nLien : https://a.fr/1\nLien : https://b.fr/2"
    donnees = json.loads(llm.rediger_factice(consignes))
    assert donnees["rubrique"] == "monde"
    assert len(donnees["sources"]) == 2
