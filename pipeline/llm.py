"""Cascade de modèles de langage gratuits (config/llm.yaml).

Tous les fournisseurs retenus exposent une API compatible OpenAI (/chat/completions) :
un seul client suffit. On essaie le premier fournisseur de la liste ; s'il n'a plus de
quota, s'il refuse la clé ou s'il échoue deux fois, on passe au suivant. Les appels
sont espacés pour respecter les limites par minute (requêtes et jetons).
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass

import requests

import communs as c

log = logging.getLogger("llm")

USAGE = c.ETAT / "llm_usage.json"


class ErreurLLM(Exception):
    pass


class QuotaEpuise(ErreurLLM):
    """Quota du jour atteint ou clé refusée : fournisseur écarté jusqu'à la fin du run."""


class ErreurTemporaire(ErreurLLM):
    """Limite par minute, panne passagère : on réessaie après une pause."""

    def __init__(self, message: str, attente: float | None = None):
        super().__init__(message)
        self.attente = attente


class ErreurFournisseur(ErreurLLM):
    """Réponse inexploitable : on passe au fournisseur suivant."""


class AucunFournisseur(ErreurLLM):
    """Toute la cascade a échoué."""


@dataclass
class Reponse:
    texte: str
    fournisseur: str
    modele: str
    jetons: int = 0


_QUOTA_JOUR = re.compile(r"per[ _-]?day|perday|daily|\bRPD\b|\bTPD\b|quota.{0,40}(day|jour)", re.IGNORECASE)


def attente_conseillee(reponse: requests.Response) -> float | None:
    entete = reponse.headers.get("retry-after")
    if entete:
        try:
            return float(entete)
        except ValueError:
            pass
    corps = reponse.text
    trouve = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', corps)  # Gemini
    if trouve:
        return float(trouve.group(1))
    trouve = re.search(r"try again in (?:(\d+)m)?(\d+(?:\.\d+)?)s", corps)  # Groq
    if trouve:
        return int(trouve.group(1) or 0) * 60 + float(trouve.group(2))
    return None


class Fournisseur:
    def __init__(self, conf: dict, commun: dict):
        self.nom = conf["nom"]
        self.base_url = conf["base_url"].rstrip("/")
        self.modele = conf["modele"]
        self.cle = os.environ.get(conf.get("cle_env", ""), "")
        self.rpm = conf.get("rpm")
        self.rpj = conf.get("rpj")
        self.tpm = conf.get("tpm")
        self.json = conf.get("json", False)
        self.reasoning_effort = conf.get("reasoning_effort")
        self.max_tokens = conf.get("max_tokens")
        self.entetes = conf.get("entetes") or {}
        self.temperature = conf.get("temperature", commun.get("temperature", 0.3))
        self.delai = commun.get("delai_secondes", 150)
        self.epuise = False
        self.raison = ""
        self.appels_jour = 0
        self.appels = 0
        self.echecs = 0
        self.jetons_total = 0
        self._dernier_appel = 0.0
        self._jetons_recents: list[tuple[float, int]] = []

    def disponible(self) -> bool:
        return bool(self.cle) and not self.epuise and (not self.rpj or self.appels_jour < self.rpj)

    def attendre_creneau(self, jetons_estimes: int) -> None:
        if self.rpm:
            attente = self._dernier_appel + 60.0 / self.rpm - time.monotonic()
            if attente > 0:
                time.sleep(attente)
        if self.tpm:
            while True:
                instant = time.monotonic()
                self._jetons_recents = [(t, n) for t, n in self._jetons_recents if instant - t < 60]
                utilises = sum(n for _, n in self._jetons_recents)
                if not self._jetons_recents or utilises + jetons_estimes <= self.tpm:
                    break
                time.sleep(max(1.0, 60 - (instant - self._jetons_recents[0][0])))
        self._dernier_appel = time.monotonic()

    def noter_jetons(self, jetons: int) -> None:
        self._jetons_recents.append((time.monotonic(), jetons))
        self.jetons_total += jetons

    def appeler(self, messages: list[dict], json_mode: bool, max_tokens: int) -> tuple[str, int]:
        charge = {
            "model": self.modele,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": min(max_tokens, self.max_tokens) if self.max_tokens else max_tokens,
        }
        if json_mode and self.json:
            charge["response_format"] = {"type": "json_object"}
        if self.reasoning_effort:
            charge["reasoning_effort"] = self.reasoning_effort
        entetes = {"Authorization": f"Bearer {self.cle}", "Content-Type": "application/json", **self.entetes}
        try:
            reponse = requests.post(f"{self.base_url}/chat/completions", json=charge, headers=entetes,
                                    timeout=self.delai)
        except requests.RequestException as e:
            raise ErreurTemporaire(type(e).__name__) from e
        if reponse.status_code == 200:
            return self._lire(reponse)
        extrait = reponse.text[:400]
        if reponse.status_code == 429:
            if _QUOTA_JOUR.search(reponse.text):  # tout le message : chez Gemini, quotaId arrive après 400 caractères
                raise QuotaEpuise(f"quota du jour atteint : {extrait}")
            raise ErreurTemporaire("limite par minute", attente_conseillee(reponse))
        if reponse.status_code in (401, 402, 403):
            raise QuotaEpuise(f"accès refusé (HTTP {reponse.status_code}) : {extrait}")
        if reponse.status_code == 404:
            raise QuotaEpuise(f"modèle indisponible pour ce compte (HTTP 404) : {extrait}")
        if reponse.status_code == 400 and "response_format" in charge and re.search(r"response_format|json", extrait, re.I):
            self.json = False  # mode JSON non pris en charge : on s'en passe
            raise ErreurTemporaire("mode JSON refusé, nouvel essai sans", 0)
        if reponse.status_code == 400 and "reasoning_effort" in charge and "reasoning" in extrait.lower():
            self.reasoning_effort = None
            raise ErreurTemporaire("paramètre reasoning_effort refusé, nouvel essai sans", 0)
        if reponse.status_code >= 500:
            raise ErreurTemporaire(f"HTTP {reponse.status_code}")
        raise ErreurFournisseur(f"HTTP {reponse.status_code} : {extrait}")

    @staticmethod
    def _lire(reponse: requests.Response) -> tuple[str, int]:
        try:
            donnees = reponse.json()
            message = donnees["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ErreurFournisseur(f"réponse illisible : {e}") from e
        contenu = message.get("content") or ""
        if isinstance(contenu, list):
            contenu = "".join(p.get("text", "") for p in contenu if isinstance(p, dict))
        if not contenu.strip():
            raise ErreurFournisseur("réponse vide (plafond de jetons épuisé par le raisonnement ?)")
        if donnees["choices"][0].get("finish_reason") == "length":
            raise ErreurFournisseur("réponse tronquée : plafond de jetons atteint")
        return contenu, int((donnees.get("usage") or {}).get("total_tokens") or 0)


class FournisseurFactice(Fournisseur):
    """Faux modèle, pour tester la mécanique sans clé ni réseau. Jamais en production."""

    def __init__(self):
        super().__init__({"nom": "factice", "base_url": "http://factice", "modele": "factice"}, {})
        self.cle = "factice"

    def attendre_creneau(self, jetons_estimes: int) -> None:
        pass

    def appeler(self, messages: list[dict], json_mode: bool, max_tokens: int) -> tuple[str, int]:
        consignes = messages[-1]["content"]
        if consignes.startswith("ARTICLES À TRADUIRE"):
            return traduire_factice(consignes), 0
        return rediger_factice(consignes), 0


_PHRASES_FACTICES = (
    "Les sources consultées décrivent les faits de façon concordante.",
    "Les autorités concernées ont communiqué sur la situation.",
    "Plusieurs médias rapportent les mêmes éléments principaux.",
    "Les détails supplémentaires restent à confirmer.",
    "Les responsables interrogés n'ont pas donné d'autre précision.",
    "La chronologie exacte des événements reste à établir.",
    "Les versions des différentes parties se rejoignent sur l'essentiel.",
    "Aucune source ne mentionne de réaction officielle à ce stade.",
)


def rediger_factice(consignes: str) -> str:
    import json
    rubrique = re.search(r"Rubrique : (\w+)", consignes)
    format_ = re.search(r"Format : (\w+), de (\d+) à (\d+) mots", consignes)
    liens = re.findall(r"^Lien : (\S+)", consignes, re.MULTILINE)
    cible = (int(format_.group(2)) + int(format_.group(3))) // 2 if format_ else 60
    paragraphes, mots, i = [], 0, 0
    chapeau = "Ceci est un article factice rédigé pour tester le pipeline. Il ne contient aucune information."
    mots = len(chapeau.split())
    while mots < cible:
        phrases = [_PHRASES_FACTICES[(i + k) % len(_PHRASES_FACTICES)] for k in range(3)]
        paragraphes.append(" ".join(phrases))
        mots += sum(len(p.split()) for p in phrases)
        i += 3
    return json.dumps({
        "titre": "Article factice de test rédigé à partir des sources du jour",
        "chapeau": chapeau,
        "corps": "\n\n".join(paragraphes),
        "rubrique": rubrique.group(1) if rubrique else "monde",
        "format": format_.group(1) if format_ else "breve",
        "niveau_de_confiance": "partiel",
        "sources": [{"nom": "source", "url": u} for u in liens[:3]],
    }, ensure_ascii=False)


def traduire_factice(consignes: str) -> str:
    """Fausse traduction : textes d'origine précédés de [EN], nombres conservés."""
    import json
    donnees = json.loads(consignes.split("\n", 1)[1])
    return json.dumps({"articles": [
        {"id": a["id"], "titre": f"[EN] {a['titre']}", "chapeau": f"[EN] {a['chapeau']}",
         "corps": a["corps"].replace("## Ce que disent les sources", "## What the sources say")}
        for a in donnees["articles"]]}, ensure_ascii=False)


class Cascade:
    def __init__(self, fournisseurs: list[Fournisseur]):
        self.fournisseurs = fournisseurs
        self._usage = c.lire_json(USAGE, {}) or {}
        jour = self._jour()
        for f in self.fournisseurs:
            f.appels_jour = self._usage.get(jour, {}).get(f.nom, 0)

    @classmethod
    def depuis_config(cls, factice: bool = False) -> "Cascade":
        if factice:
            log.warning("Modèle FACTICE : les articles produits ne contiennent aucune information")
            return cls([FournisseurFactice()])
        conf = c.charger_yaml("llm.yaml")
        fournisseurs = [Fournisseur(f, conf) for f in conf.get("fournisseurs", [])]
        avec_cle = [f.nom for f in fournisseurs if f.cle]
        if avec_cle:
            log.info("Cascade : %s", " -> ".join(avec_cle))
        else:
            variables = sorted({f.get("cle_env") for f in conf.get("fournisseurs", [])})
            log.error("Aucune clé d'API trouvée (%s). Voir pipeline/.env.exemple.", ", ".join(variables))
        return cls(fournisseurs)

    @staticmethod
    def _jour() -> str:
        return c.maintenant().strftime("%Y-%m-%d")

    def disponible(self) -> bool:
        return any(f.disponible() for f in self.fournisseurs)

    def completer(self, systeme: str, utilisateur: str, json_mode: bool = True,
                  max_tokens: int = 4000, essais: int = 2, preferes: tuple[str, ...] = ()) -> Reponse:
        """preferes : fournisseurs essayés en premier (les modèles légers, pour traduire)."""
        messages = [{"role": "system", "content": systeme}, {"role": "user", "content": utilisateur}]
        estimation = (len(systeme) + len(utilisateur)) // 3 + max_tokens // 2
        ordre = [f for f in self.fournisseurs if f.nom in preferes] + [f for f in self.fournisseurs if f.nom not in preferes]
        for f in ordre:
            echecs = 0
            while echecs < essais and f.disponible():
                f.attendre_creneau(estimation)
                try:
                    texte, jetons = f.appeler(messages, json_mode, max_tokens)
                except QuotaEpuise as e:
                    f.epuise, f.raison = True, str(e)[:200]
                    log.warning("%s écarté : %s", f.nom, f.raison)
                    break
                except ErreurTemporaire as e:
                    if e.attente == 0:
                        continue  # paramètre retiré, on relance aussitôt
                    echecs += 1
                    f.echecs += 1
                    pause = min(e.attente if e.attente is not None else 10.0 * echecs, 90.0)
                    log.info("%s : %s, nouvel essai dans %.0f s", f.nom, e, pause)
                    time.sleep(pause)
                    continue
                except ErreurFournisseur as e:
                    f.echecs += 1
                    log.warning("%s : %s", f.nom, e)
                    break
                self._compter(f, jetons or estimation)
                return Reponse(texte, f.nom, f.modele, jetons)
        raise AucunFournisseur("aucun fournisseur de la cascade n'a répondu")

    def _compter(self, f: Fournisseur, jetons: int) -> None:
        f.appels += 1
        f.appels_jour += 1
        f.noter_jetons(jetons)
        if isinstance(f, FournisseurFactice):
            return
        jour = self._jour()
        self._usage = {jour: self._usage.get(jour, {})}  # seul le jour courant compte
        self._usage[jour][f.nom] = f.appels_jour
        c.ecrire_json(USAGE, self._usage)

    def bilan(self) -> list[dict]:
        return [{"nom": f.nom, "modele": f.modele, "cle": bool(f.cle), "appels": f.appels,
                 "echecs": f.echecs, "jetons": f.jetons_total, "ecarte": f.raison}
                for f in self.fournisseurs]
