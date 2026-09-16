from datetime import date, datetime, timedelta

import communs as c
import edition


def test_limite_normale_respectee():
    # Démarrage à l'heure : l'heure limite demandée s'applique telle quelle.
    debut = datetime(2026, 9, 16, 0, 35, tzinfo=c.fuseau())
    limite = edition.limite_redaction(date(2026, 9, 16), "05:45", debut)
    assert limite == edition.heure_locale(date(2026, 9, 16), "05:45")


def test_limite_deja_depassee_au_demarrage():
    # Run du 2026-09-16 : cron prévu à 00:30 UTC, déclenché par GitHub à 05:06 UTC (09:06 locale),
    # après l'heure limite (05:45 locale). Sans la marge minimale, tout sujet est écarté d'emblée.
    debut = datetime(2026, 9, 16, 9, 6, tzinfo=c.fuseau())
    limite = edition.limite_redaction(date(2026, 9, 16), "05:45", debut)
    assert limite == debut + edition.MARGE_MIN_REDACTION
    assert limite > debut


def test_pas_d_heure_limite_sans_argument():
    assert edition.limite_redaction(date(2026, 9, 16), None, c.maintenant()) is None
