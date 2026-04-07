"""
Known rivalry pairs indexed by API-Football external team IDs.
Derbies / historic rivalries are flagged as high-variance fixtures that suppress
model confidence regardless of other signal strength.

IDs are API-Football external team IDs (teams.external_provider_id).
Verify against the teams table after import if uncertain.
"""
from __future__ import annotations

KNOWN_RIVALRIES: set[frozenset[int]] = {
    # ── Turkish Süper Lig ────────────────────────────────────────────────────
    frozenset({611, 645}),    # Galatasaray vs Fenerbahçe  (Kıtalararası Derbi)
    frozenset({611, 614}),    # Galatasaray vs Beşiktaş   (İstanbul Derbisi)
    frozenset({645, 614}),    # Fenerbahçe  vs Beşiktaş   (İstanbul Derbisi)
    frozenset({611, 618}),    # Galatasaray vs Trabzonspor
    frozenset({645, 618}),    # Fenerbahçe  vs Trabzonspor
    frozenset({614, 618}),    # Beşiktaş    vs Trabzonspor
    frozenset({611, 611}),    # placeholder sentinel — never matches

    # ── Premier League ───────────────────────────────────────────────────────
    frozenset({33, 34}),      # Manchester United vs Liverpool
    frozenset({40, 49}),      # Liverpool vs Chelsea
    frozenset({50, 47}),      # Manchester City vs Arsenal
    frozenset({33, 50}),      # Manchester United vs Manchester City
    frozenset({42, 48}),      # Arsenal vs Tottenham  (North London Derby)
    frozenset({49, 48}),      # Chelsea vs Tottenham
    frozenset({66, 65}),      # Leeds vs Sheffield United (Yorkshire Derby)
    frozenset({55, 51}),      # West Ham vs Crystal Palace

    # ── La Liga ─────────────────────────────────────────────────────────────
    frozenset({529, 530}),    # Real Madrid vs Barcelona   (El Clásico)
    frozenset({530, 532}),    # Barcelona vs Atlético Madrid
    frozenset({529, 532}),    # Real Madrid vs Atlético Madrid (Madrid Derby)
    frozenset({536, 540}),    # Sevilla vs Real Betis       (Seville Derby)
    frozenset({533, 537}),    # Villarreal vs Valencia      (Derbi de la Comunitat)

    # ── Bundesliga ───────────────────────────────────────────────────────────
    frozenset({157, 165}),    # Borussia Dortmund vs Bayern München (Der Klassiker)
    frozenset({163, 173}),    # Borussia M'gladbach vs FC Köln      (Rhein Derby)
    frozenset({161, 162}),    # VfB Stuttgart vs TSG Hoffenheim
    frozenset({169, 170}),    # Werder Bremen vs Hamburger SV       (Nordderby)

    # ── Serie A ──────────────────────────────────────────────────────────────
    frozenset({489, 487}),    # Inter Milan vs AC Milan     (Derby della Madonnina)
    frozenset({496, 487}),    # Juventus vs AC Milan
    frozenset({489, 496}),    # Inter vs Juventus           (Derby d'Italia)
    frozenset({497, 494}),    # AS Roma vs Lazio            (Derby della Capitale)
    frozenset({492, 488}),    # Napoli vs Atalanta

    # ── Ligue 1 ──────────────────────────────────────────────────────────────
    frozenset({85, 80}),      # Paris Saint-Germain vs Marseille (Le Classique)
    frozenset({80, 81}),      # Marseille vs Lyon
    frozenset({81, 83}),      # Lyon vs Saint-Étienne       (Derby du Rhône)
}

# Remove the placeholder sentinel
KNOWN_RIVALRIES.discard(frozenset({611, 611}))


def is_derby(home_team_external_id: int, away_team_external_id: int) -> bool:
    """Return True if the match is a known rivalry/derby."""
    return frozenset({home_team_external_id, away_team_external_id}) in KNOWN_RIVALRIES
