# Demo-Ablauf (Video, höchstens 2 Minuten)

Start: `python start.py`, dann öffnet sich der Browser. Oben rechts lassen sich Rolle (Behörde / Antragsteller / Öffentlich), Sprache (DE/EN) und Hell/Dunkel umschalten.

| Zeit | Klick | Sprechtext |
|---|---|---|
| 0:00 | **Eingang** (Behörde) | „AccessDesk 2 ist eine automatisierte Zugangsstelle nach dem Europäischen Gesundheitsdatenraum. Jeder Antrag wird nach den Five Safes geprüft: wer fragt, wozu, welche Daten, wo gerechnet wird und was die Stelle verlässt.“ |
| 0:12 | **R02** öffnen, Tab **Antrag** | „Eine Versicherung will Prämien an Diabetes koppeln. Die Regeln markieren die Stelle, das ist nach Art. 54 verboten. Abgelehnt, ohne dass eine einzige Abfrage läuft.“ |
| 0:24 | Rolle **Antragsteller**, Dr. Sophie Lechner, **R01** | „Eine Forscherin fragt nach Typ-2-Diabetes pro Bundesland. Sie bekommt eine anonymisierte Statistik mit Karte und einen formellen Bescheid auf Deutsch und Englisch, mit Artikeln, Begründung und Auflagen.“ |
| 0:38 | **Bescheid öffnen**, kurz scrollen | „Der Bescheid ist druckfertig. Die Texte haben wir gegen den Originaltext der Verordnung geprüft.“ |
| 0:44 | Prof. Elena Rossi, **R08** | „Kleine Gruppen: Unter 10 Personen steht ‚<10‘ oder ‚unterdrückt‘, schraffiert. Summenzeilen gibt es nicht, damit niemand verborgene Werte zurückrechnen kann.“ |
| 0:54 | Dr. Sophie Lechner, **D05** | „Dieselbe Forscherin fragt noch einmal, diesmal ab 19 Jahren. In Vorarlberg würde die Differenz acht 18-Jährige verraten. Der Differenz-Schutz erkennt das und unterdrückt genau diese Zelle.“ |
| 1:06 | Dr. Amir Hadžić, **R05** → **SPE-Arbeitsbereich** | „Ein KI-Start-up begründet, warum Statistik nicht reicht. Es bekommt Einzeldaten von genau 1.152 Personen, nur Diagnosen, Medikation und HbA1c, in einer abgeschotteten Umgebung.“ |
| 1:16 | SQL ausführen, dann **Rohdaten herunterladen** | „Abfragen laufen nur lesend. Ein Download wird blockiert und protokolliert. Hinaus dürfen nur geprüfte Aggregate, nach Freigabe durch die Behörde.“ |
| 1:28 | **Neuer Antrag**, Zweck „advertising campaign …“ eintippen | „Neue Anträge prüft die App live. Vor dem Absenden sieht man, welcher Begriff auf welchen Code führt, die geschützte Kohortengröße und hier die Warnung nach Art. 54.“ |
| 1:40 | Rolle **Behörde**, **Prüfprotokoll** → **Kette prüfen** | „Jeder Schritt landet in einem manipulationssicheren Protokoll. Jeder Eintrag enthält den Hash des vorigen.“ |
| 1:46 | **Auswertung** → **Auswertung starten** | „Ergebnis: 10 von 10 Entscheidungen, 6 von 6 Zahlen, 0 Lecks, 10 von 10 konsistent, unter 0,1 Sekunden. Dazu stimmen 29 von 29 Anfragen mit einem unabhängigen pandas-Orakel überein.“ |
| 1:54 | **Öffentlich** → Transparenzregister | „Ehrlich gesagt: eID und Register sind simuliert, die Föderation ist nur entworfen, und die KI ist optional. Alle Zahlen kommen aus den Regeln.“ |

## Was funktioniert und was nicht (im Video so sagen)

- **Funktioniert:**
  - alle 10 Testanfragen und die Demo-Fälle, auch neue Anfragen im selben Stil
  - Statistik mit Small-Cell-Regel, Differenz-Schutz und SPE mit Download-Sperre und Ausgabeprüfung
  - Bescheid, Eingangsliste mit Prüfung, Transparenzregister und Hash-Kette
- **Simuliert:** eID (ID Austria, EU-Wallet), Firmenbuch und Ärztekammer. Die Signaturen werden aber echt geprüft.
- **Grenzen:**
  - Der Parser versteht die Satzmuster der Aufgabe und nahe Varianten. Bei anderen Formulierungen gibt er eine Warnung aus und schickt den Fall zur Prüfung.
  - Die Föderation ist nicht gebaut.
  - Die KI braucht einen eigenen API-Key.
