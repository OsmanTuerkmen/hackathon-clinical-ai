# EHDS – relevante Artikel und Entscheidungslogik

Quelle: Verordnung (EU) 2025/327 über den Europäischen Gesundheitsdatenraum (EHDS), Kapitel IV
(Sekundärnutzung), https://eur-lex.europa.eu/eli/reg/2025/327/oj/eng – gelesen am 2026-10-29.
Zusammenfassungen in eigenen Worten; maßgeblich ist der Verordnungstext.

## Art. 53 – Zulässige Zwecke der Sekundärnutzung

Eine Zugangsstelle (Health Data Access Body, HDAB) gewährt Zugang nur, wenn die Verarbeitung für einen dieser
Zwecke nötig ist:

| Punkt | Zweck (eigene Worte) | Typische Signale im Antrag |
|---|---|---|
| (a) | Öffentliches Interesse in öffentlicher Gesundheit/Arbeitsmedizin: Gesundheitsüberwachung, Schutz vor Gesundheitsgefahren, Qualität und Sicherheit der Versorgung, von Arzneimitteln und Medizinprodukten | prevention, surveillance, quality programme, patient safety |
| (b) | Politikgestaltung und Regulierung zur Unterstützung öffentlicher Stellen im Gesundheitsbereich | ministry, policy, regulator, health authority |
| (c) | Amtliche Statistik zu Gesundheit und Versorgung | statistics office, official statistics, health report |
| (d) | Aus- und Weiterbildung in Gesundheitsberufen (Berufs-/Hochschulniveau) | teaching, education, training module for GPs |
| (e) | Wissenschaftliche Forschung mit Nutzen für öffentliche Gesundheit oder Versorgungsqualität, inkl. (i) Produkt-/Dienstleistungsentwicklung und (ii) Training, Test und Bewertung von Algorithmen/KI | research, study, train/validate a model |
| (f) | Verbesserung der Versorgung und Optimierung von Behandlungen | improve care, treatment optimisation |

Abs. 2: Zwecke (a)–(c) sind öffentlichen Stellen (und EU-Einrichtungen) vorbehalten. Die App zeigt dies nur als
Staff-Hinweis; die Entscheidungsleiter der Aufgabe hängt nicht davon ab.

## Art. 54 – Verbotene Sekundärnutzung

Daten dürfen nur im Rahmen einer Datenerlaubnis (Art. 68) oder einer genehmigten Datenanfrage (Art. 69) genutzt werden.
Ausdrücklich verboten ist die Nutzung für:

| Punkt | Verbot (eigene Worte) | Beispiele in den Anträgen |
|---|---|---|
| (a) | Entscheidungen mit rechtlicher, sozialer oder wirtschaftlicher Wirkung zum Nachteil einzelner Personen oder Gruppen | Abgleich mit Mitarbeiterliste (R06) |
| (b) | Entscheidungen zu Jobangeboten, schlechteren Konditionen für Waren/Dienstleistungen, Ausschluss aus Versicherungs- oder Kreditverträgen, Änderung von Beiträgen/Prämien/Kreditbedingungen oder sonstige Diskriminierung aufgrund von Gesundheitsdaten | Versicherungsprämien (R02), Vertragsverlängerung von Beschäftigten (R06) |
| (c) | Werbung oder Marketing | Ärzte-Werbekampagne (R04) |
| (d) | Entwicklung von Produkten/Dienstleistungen, die Einzelne, die öffentliche Gesundheit oder die Gesellschaft schädigen können, z. B. illegale Drogen, Alkohol, Tabak- und Nikotinprodukte, Waffen, suchterzeugende Produkte | Nikotinbeutel-Geschmacksrichtungen (R10) |
| (e) | Tätigkeiten, die gegen nationale Ethikvorschriften verstoßen | (nur manuelle Prüfung) |

Abgrenzung: Forschung zur Rauchentwöhnung oder zu Schäden durch Nikotin ist kein Produktentwicklungszweck nach (d).

## Art. 66 – Datenminimierung und Zweckbindung

Bei einem Zugangsantrag nur Daten, die für den Zweck angemessen, relevant und auf das Nötige beschränkt sind (Abs. 1).
Kann der Zweck mit anonymisierten Daten erreicht werden, werden anonymisierte Daten bereitgestellt (Abs. 2).
Pseudonymisierte Daten nur, wenn der Antragsteller ausreichend dargelegt hat, dass anonymisierte Daten nicht genügen
(Abs. 3); die Re-Identifizierungsinformation bleibt bei der Zugangsstelle.

## Art. 67 – Datenzugangsantrag (health data access application)

Natürliche oder juristische Personen können für Art.-53-Zwecke einen Zugangsantrag stellen. Pflichtinhalte u. a.:
Identität und Funktion, Zweck, detaillierte Nutzungsbeschreibung, Beschreibung der Daten, **ob pseudonymisiert oder
anonymisiert benötigt wird – bei pseudonymisiert mit Begründung, warum anonymisierte Daten nicht ausreichen**
(Abs. 2 lit. e), Schutzmaßnahmen, Dauer in der SPE, benötigte Werkzeuge.

## Art. 68 – Datenerlaubnis (data permit)

Die Zugangsstelle prüft u. a.: Zweck nach Art. 53, Notwendigkeit/Verhältnismäßigkeit (Art. 66), bei pseudonymisierten
Daten ausreichende Begründung, Qualifikation des Antragstellers, Schutzmaßnahmen (Abs. 1). Sind die Voraussetzungen
erfüllt, wird eine Datenerlaubnis erteilt (Abs. 3). Reichen sie nicht für eine Erlaubnis, wohl aber für eine
anonymisierte statistische Antwort nach Art. 69, kann die Stelle stattdessen Statistik liefern (Abs. 3 UAbs. 2).
Die Erlaubnis legt Datenkategorien, Format (pseudonymisiert in der SPE), Zweck, berechtigte Personen und Dauer fest
(Abs. 10); Nutzer verarbeiten die Daten in einer SPE (Abs. 11).

## Art. 69 – Datenanfrage (health data request)

Für Art.-53-Zwecke kann eine Anfrage gestellt werden, deren Antwort **nur in anonymisiertem statistischem Format**
erfolgt; der Nutzer erhält keinen Zugang zu den zugrunde liegenden Daten (Abs. 1). Die Stelle prüft Vollständigkeit
und Risiken (Abs. 3).

## Art. 71 – Opt-out

Betroffene können jederzeit ohne Begründung der Sekundärnutzung widersprechen (Abs. 1). Ihre Daten werden für nach
dem Widerspruch erteilte Erlaubnisse/Anfragen nicht bereitgestellt oder verarbeitet (Abs. 3). Ausnahmen nur über
nationales Recht für öffentliche Stellen (Abs. 4) – in dieser App nicht umgesetzt: Opt-out-Patienten werden immer
ausgeschlossen.

## Art. 73 – Sichere Verarbeitungsumgebung (SPE)

Zugang unter einer Datenerlaubnis nur über eine SPE (Abs. 1) mit: Zugriff nur für in der Erlaubnis genannte Personen (a),
Schutz vor unbefugtem Lesen, Kopieren, Ändern, Entfernen (b), Nutzer sehen nur die Daten ihrer Erlaubnis (d),
**protokollierte Zugriffe und Aktivitäten, mindestens ein Jahr aufbewahrt** (e). Herunterladen dürfen Nutzer nur
nicht-personenbezogene Daten, etwa anonymisierte Statistik, nach Prüfung durch die Zugangsstelle (Abs. 2).

## Entscheidungslogik der App

Feste Reihenfolge, erste zutreffende Stufe gewinnt:

| Stufe | Bedingung | Entscheidung | Artikel |
|---|---|---|---|
| 1 | Zweck fällt unter Art. 54 (a)–(d) | `REJECT` | 54 |
| 2 | `requested_as` = „health data request“ | `APPROVE_STATISTICAL` | 53, 69 |
| 3 | Zugangsantrag mit Begründung, warum anonymisierte Statistik nicht reicht (Art. 66(3), 67(2)(e), 68(1)(c)) | `APPROVE_SPE` | 53, 66, 68, 73 |
| 4 | jeder andere Zugangsantrag | `APPROVE_STATISTICAL` | 53, 66, 69 |

Bei Genehmigungen nennt die App zusätzlich Art. 71 (Opt-out-Patienten ausgeschlossen); laut Aufgabe zulässig.

Begründungsbausteine:
- Stufe 4 folgt aus Art. 66(2) und 68(3) UAbs. 2: ohne Darlegung, dass Anonymisierung nicht genügt, wird nur
  anonymisierte Statistik geliefert.
- Statistik-Antworten unterliegen der Small-Cell-Regel (Counts < 10 → `<10`; Prozent mit Zähler/Nenner < 10 und
  Mittelwerte aus < 10 Patienten → `suppressed`), damit sie nach Art. 69 tatsächlich anonym sind.
