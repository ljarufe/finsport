# Finsport — Historical Ingestion + Dixon-Coles Applicability/Readiness Research

**Date:** 2026-09-03
**Status:** REFERENCE ONLY
**Research completion:** COMPLETE
**Authority:** `Finsport_historical_ingestion_dixon_coles_research_prompt.md`
**Prior research authority:** `Finsport_DIXON_COLES_applicability_handoff_2026-09-03.md`
**Audited local baseline:** `master@781674afd26106a0a2d7848252e89bbd92f8d2ff`

> This document is research authority only. It does not implement code, create a ticket, assign a ticket ID, or authorize real betting.

---

## 1. Executive summary

Finsport can coherently define one future package covering:

1. reproducible historical football-result ingestion/backfill;
2. the minimum provider/ingestion organization required by multiple real sources;
3. correction of the current pure `DIXON_COLES` applicability/readiness/execution contract.

The final disposition is:

**COMBINED_TICKET_RECOMMENDED**

No falsification criterion in the research brief was triggered. The pieces have one shared outcome: trustworthy same-league football-result evidence must enter the canonical database with explicit provenance, and Dixon-Coles must consume that evidence honestly, independently from bookmaker-price events, while separating exploratory Prediction production from betting eligibility.

The principal findings are:

- The API-Football Free contract is **100 requests/day**, includes all competitions/endpoints, but limits available seasons. A bounded live probe against the real Finsport account closed the prior ambiguity: `/fixtures` for La Liga 2024 returned all 380 matches, while Ligue 1 2025 and 2026 returned a provider `plan` error saying Free plans did not have access and to try seasons 2022–2024. `/leagues?id=61` nevertheless listed Ligue 1 seasons 2010–2026. Therefore **catalogue visibility is not season entitlement**, and the observed Ligue 1 failure is a provider-plan/season-access restriction for those requests, not a demonstrated mapping/request-shape/application bug. [E1][L2]
- API-Football should remain the primary/canonical current football provider, but it should **not be the bulk historical source of first choice** when a free bulk source exists. Historical results are one-shot reference data; repeated daily full-season calls waste quota.
- `football-data.co.uk` is the preferred historical source for the supported European leagues. Its current site offers computer-ready CSV/Excel historical results for free access; European archive files go back to 1993/94. [E2][E3]
- Finsport's installed `penaltyblog==1.12.0` is current as of 2026-08-21. Its `FootballData` scraper exposes a public `list_competitions()` and `get_fixtures()` contract, including the eight enabled European leagues relevant here. The scraper is an **ingestion helper**, separate from the local Dixon-Coles modelling library. [E4][E5]
- Argentina, Brazil and USA have direct football-data.co.uk CSV download surfaces. A direct simple source adapter is cleaner than extending penaltyblog's scraper or buying another API. [E6][E7][E8]
- Peru now has an acceptable free historical candidate: RSSSF annual Peru pages. Checked pages provide Primera División round dates, home/away teams and full-time results, and the RSSSF pages explicitly permit copying with proper attribution. RSSSF is therefore the recommended Peru historical source, using a source-specific parser and preserving date-only precision where exact kickoff time is absent. Soccerway is fallback/corroboration; Wikipedia is corroborative only; FootyStats historical downloads are not the preferred free route. [E9][E10][E11][E12]
- Real overlap audit replaced the earlier unmeasured overlap claim with measured counts. For La Liga 2022–2024, football-data/penaltyblog produced **1,140 source rows; 1,140 mapped; 1,140 exact; 0 score conflicts; 0 date differences; 0 duplicate source rows; 0 unmatched source rows; 0 unmatched canonical rows; 0 ambiguous teams after the audit mapping**. Premier League 2024 produced **380/380/380** with the same zero-conflict outcome. [L1]
- The audit also found legitimate naming aliases (`Ath Bilbao` → `Athletic Club`, `Man City` → `Manchester City`, etc.). Their audit mapping used schedule signatures only to prove correspondence. **That audit mechanism is not a production fuzzy-matching policy.** Production must use explicit source mappings/aliases or fail closed.
- The La Liga walk-forward study showed material benefit from prior-season history, but it does **not** prove a universal number of seasons. Current-season-only produced 334/380 Predictions with log-loss 1.1224. One completed prior season + current-to-date produced 378/380 with log-loss 0.9939. Two completed prior seasons + current-to-date produced 379/380 with log-loss 0.9718. The latter had the best observed log-loss/coverage, while the one-prior-season configuration had the best 10-bin confidence ECE. Premier did not have enough locally stored seasons for the same depth comparison. The locally selected `xi` was `0.0`, so this run did **not** measure a decayed-history optimum. [L1]
- Therefore research does **not** freeze “3 seasons”, “8 matches” or another universal numeric rule. Historical storage depth and model readiness are separated. The historical bootstrap should import **all completed seasons already represented in Finsport's Season catalogue that the approved free source can reproducibly supply**, bounded by that catalogue and source availability. This is one-shot reference acquisition, not a claim that every stored season should receive equal model weight. Dixon-Coles training/readiness remains versioned/configurable.
- Deterministic local penaltyblog probes showed that zero history is already `UNAVAILABLE`; 1/2/4 connected matches can fit but fail on prediction with negative probabilities; eight connected matches can produce; eight disconnected matches can fail; and unseen target teams return `INSUFFICIENT_TEAM_HISTORY`. This proves that match count alone is not a structural readiness rule. [L1]
- The research therefore adopts **D11 Result B: `NO_GLOBAL_THRESHOLD_JUSTIFIED`**. A valid ProbabilityResult can be stored as exploratory evidence, while `bet_eligible=false` unless the competition/model configuration has an explicitly approved, versioned readiness profile. ROI/profit is not used to define Prediction readiness.
- Current prospective Prediction creation is confirmed to be coupled to `ODDS_CAPTURE`, which is wrong for Dixon-Coles. Relevant canonical football evidence changes—not bookmaker-price changes—must drive its evidence identity/recompute. [L1]
- Current Prediction uniqueness cannot hold two versions for one experiment/match/model/variant. The minimal audit-preserving solution is to make a new relevant football-evidence basis produce a new prospective experiment/evidence identity, preserving prior Predictions rather than overwriting them. [L1]
- The provider threshold is crossed. The recommended architecture is **focused source-specific provider/adapters + a thin normalized historical-result contract feeding the existing reconciliation/canonical path**. No generic plugin framework, no new Django app, no speculative staging system.
- When an admin enables a Competition, historical bootstrap should be requested once, idempotently, outside the admin transaction and owned by the existing execution/scheduling topology. A single `history_imported` boolean is insufficient: the semantic lifecycle needs at least `NOT_ATTEMPTED / COMPLETE / PARTIAL / UNAVAILABLE / FAILED` plus source/strategy/depth/version/provenance. Once `COMPLETE`, the normal daily pipeline should not redownload closed historical seasons.

### Material recommendation — historical acquisition

**EVIDENCE**
→ Bulk free sources cover the enabled European/AR/BR/US leagues; RSSSF covers Peru; API-Football Free denies some current/recent seasons; historical rows do not need daily refresh; Finsport already has Season metadata beyond its Match backfill. [E1][E2][E6][E9][L2]

**CONCLUSION**
→ Historical results should be a one-shot, competition-scoped bootstrap with a source ladder, not a recurrent provider-polling responsibility.

**RECOMMENDATION**
→ On first enablement or explicit controlled retry, ingest all completed Season rows already known locally that the approved source can provide; persist coverage state; never re-fetch completed history in ordinary daily wakes after `COMPLETE`.

**CONFIDENCE**
→ STRONG INFERENCE / RECOMMENDATION.

### Material recommendation — Dixon-Coles readiness

**EVIDENCE**
→ Count-only probes fail structurally; La Liga walk-forward improves strongly with prior history but does not establish a universal numerical threshold; Premier cannot generalize the study yet. [L1]

**CONCLUSION**
→ No defensible universal `N` exists from current evidence.

**RECOMMENDATION**
→ Implement three explicit states: fit-attempt readiness, valid Prediction production, and betting eligibility. Use a versioned readiness profile; default unvalidated profiles to `bet_eligible=false` while preserving valid exploratory Predictions.

**CONFIDENCE**
→ ESTABLISHED for the separation; OBSERVED for local failure modes; RECOMMENDATION for the profile contract.

---

## 2. Decisions enabled

This research enables F008 to define an approved ticket/package without delegating the following semantic decisions to implementation:

- per-enabled-league source strategy;
- API-Football historical role under the current Free account;
- football-data/penaltyblog ingestion contract;
- Peru source strategy;
- initial stored historical depth policy;
- source identity and canonicalization/provenance/conflict semantics;
- canonical vs research-only disposition;
- provider/ingestion architecture boundary;
- Inkabet behavior disposition;
- Dixon-Coles structural attemptability, Prediction validity and bet-eligibility separation;
- `UNAVAILABLE` vs `FAILED` boundary;
- sports-evidence-driven recompute;
- Prediction evidence versioning;
- below-readiness Decision behavior;
- offline test contract;
- combined-ticket coherence and explicit OUT scope.

Low-level filenames, ORM field names, migration names and exact task wiring remain implementation/preflight details, not open research decisions.

---

## 3. Current baseline inspected

Local authority was the clean checkout and PostgreSQL evidence captured before this report:

- branch/SHA: `master@781674afd26106a0a2d7848252e89bbd92f8d2ff`;
- only persisted `Source` identities: `api_football`, `inkabet`;
- API-Football is PRIMARY/read-only/current canonical football authority after reconciliation;
- Inkabet is SECONDARY/read-only/market-only/fail-soft;
- no separate scheduler is authorized;
- local provider/ingestion ownership is currently distributed across root provider modules, sync/reconciliation, capture, maintenance and pipeline code;
- `sync_football_season` and current `SEASON_BOOTSTRAP` both request full-season API-Football fixtures with `{league, season, timezone}`;
- current Dixon-Coles `fit()` only rejects empty history before the library fit;
- current prospective Prediction candidates are derived only from due `ODDS_CAPTURE` items;
- `PredictionExperiment` prospective identity is unique by `(competition, logical_identity)`;
- `Prediction` is unique by `(experiment, match, model_code, variant)`;
- Inkabet is invoked automatically only after due successful primary odds capture and is not a historical-result source.

Local evidence files used in this report:

- `[L0] research_historical_ingestion_runtime.txt`
- `[L0b] research_historical_ingestion_db.txt`
- `[L0c] research_historical_ingestion_code.txt`
- `[L0d] research_dixon_coles_db.txt`
- `[L1] research_historical_dc_local_closure.txt`
- `[L2] api_football_historical_probe.txt`

---

## 4. Current enabled-league data inventory

The latest local closure supersedes older FT counts where it measured a newer state. In particular, La Liga's depth audit saw 1,151 scored FT rows across 2022, 2023, 2024 and 2026, while the earlier inventory had recorded 1,150 FT.

### Table A — enabled-league historical coverage

| Competition | Current stored seasons/FT | API-Football viable? | football-data/penaltyblog viable? | other source? | recommended source | recommended depth | remaining gap |
|---|---:|---|---|---|---|---|---|
| AR — Liga Profesional Argentina (local 1459) | Earlier inventory: 3 Matches / 0 FT; Season catalogue from ~2015 | Season-specific entitlement not probed; do not use as bulk assumption | Direct football-data.co.uk CSV: YES; penaltyblog scraper not demonstrated | None needed initially | Direct football-data.co.uk adapter | All completed local Season rows intersecting source availability; one-shot | Explicit team/competition aliases during import |
| BR — Serie A (1272) | 1 / 1 FT | Season-specific entitlement not probed | Direct football-data.co.uk CSV: YES | None needed initially | Direct football-data.co.uk adapter | All completed local Season rows intersecting source availability | Mapping/season enumeration preflight |
| DE — Bundesliga (1274) | 7 / 6 FT | Free may expose some seasons; not reliable bulk source | `DEU Bundesliga 1`: YES | — | penaltyblog `FootballData` → football-data.co.uk | All completed local Season rows source can supply | Explicit mappings where names differ |
| EN — Premier League (1273) | 2024: 380 FT; 2026: 5 FT | Existing canonical history; current bulk entitlement not needed | `ENG Premier League`: YES; overlap 380/380 exact for 2024 | — | Preserve API-F provenance; fill historical gaps from football-data | All completed local Season rows; avoid rewriting existing API-F rows | Only explicit alias mapping; no data conflict observed |
| ES — La Liga (1278) | 2022: 380; 2023: 380; 2024: 380; 2026: 11 FT | **YES for 2024 in live control: 380 rows** | `ESP La Liga`: YES; overlap 1,140/1,140 exact across 2022–2024 | — | Preserve API-F provenance; football-data for bulk/fallback | All completed local Season rows; model depth remains versioned | No observed score/date conflict in audited seasons |
| FR — Ligue 1 (1270) | 3 / 0 FT | **2025 & 2026 denied by current Free plan**; provider says try 2022–2024 | `FRA Ligue 1`: YES | — | penaltyblog/football-data for historical bootstrap | All completed local Season rows source can supply | Do not retry denied API-F seasons daily |
| IT — Serie A (1275) | 7 / 6 FT | Season-specific entitlement not probed | `ITA Serie A`: YES | — | penaltyblog/football-data | All completed local Season rows source can supply | Mapping audit |
| NL — Eredivisie (1276) | 1 / 0 FT | Season-specific entitlement not probed | `NLD Eredivisie`: YES | — | penaltyblog/football-data | All completed local Season rows source can supply | Mapping audit |
| PE — Primera División (1524) | 3 / 1 FT; Season catalogue from ~2016 | Exact historical `/fixtures` entitlement not probed | football-data/penaltyblog: NO demonstrated Peru support | **RSSSF annual Peru pages**; Soccerway fallback | RSSSF source-specific parser; API-F current canonical where already present | Completed local Season rows from 2016 onward where RSSSF page is parseable; preserve date-only precision | Source-specific parser, team aliases, awarded/annulled match rules |
| PT — Primeira Liga (1277) | 1 / 0 FT | Season-specific entitlement not probed | `PRT Liga 1`: YES | — | penaltyblog/football-data | All completed local Season rows source can supply | Mapping audit |
| TR — Süper Lig (1325) | 1 / 0 FT | Season-specific entitlement not probed | `TUR Super Lig`: YES | — | penaltyblog/football-data | All completed local Season rows source can supply | Mapping audit |
| US — MLS (1432) | 1 / 0 FT | Season-specific entitlement not probed | Direct football-data.co.uk CSV: YES | None needed initially | Direct football-data.co.uk adapter | All completed local Season rows intersecting source availability | Calendar-year season normalization/mapping |

**Depth policy in Table A is an acquisition policy, not a universal Dixon-Coles training-window parameter.** The database should retain reusable historical evidence once; the model's use/weighting of that evidence is separately versioned.

---

## 5. Why existing historical coverage differs by league

The local facts resolve the apparent inconsistency:

1. `Season` catalogue rows exist for many historical years across enabled competitions.
2. Historical `Match`/FT rows do not.
3. La Liga and Premier historical `MatchSourceRef` evidence identifies API-Football as the source of their already-loaded history.
4. The same full-season API-Football request shape can still return historical data for an entitled season (La Liga 2024), but current Free entitlement is season-dependent and can reject another competition's recent/active season (Ligue 1 2025/2026). [L2]

Therefore:

```text
historical Season catalogue
!=
historical Match backfill
```

and:

```text
API-Football league/season visible in /leagues
!=
fixtures for that season accessible under current plan
```

The existing coverage difference is not evidence that Finsport's mapping is globally broken. It is the result of historical backfill having occurred for some competitions plus current provider entitlement limits for others.

---

## 6. API-Football current historical contract

### Official contract

The current official Pricing page states:

- Free: `$0/month`;
- `100 Requests / day`;
- all plans include all competitions and endpoints;
- Free plans are limited in terms of available seasons. [E1]

The public pricing page does **not** define a universal exact number of historical seasons for Free.

### Account-specific observed contract

The authorized four-call probe used the real Finsport account/client with no retries and no DB writes. [L2]

- `GET /leagues?id=61` → SUCCESS; Ligue 1 seasons 2010 through 2026 listed.
- `GET /fixtures?league=140&season=2024&timezone=America/Lima` → SUCCESS; `380` results.
- `GET /fixtures?league=61&season=2025&timezone=America/Lima` → `provider_access_denied`; provider summary: `Free plans do not have access to this season, try from 2022 to 2024.`
- same for Ligue 1 `season=2026`.

### Exactly what remains viable

Under the observed Free account:

- entitled historical fixture seasons remain viable through the ordinary `/fixtures?league&season` request shape;
- the same request shape is not universally authorized for every visible season;
- the provider's catalog endpoint can expose seasons that the Free fixtures entitlement does not permit;
- a bounded availability check may be used during one-shot bootstrap if API-Football is considered as a source, but the project should prefer quota-free bulk sources for historical backfill when available;
- API-Football remains appropriate for current canonical discovery/results and for existing source-backed canonical matches.

### Material recommendation

**EVIDENCE**
→ La Liga 2024 succeeds with the real current client and request shape; Ligue 1 2025/2026 fail with an explicit provider plan error; Ligue 1 mapping/catalogue exists. [L2]

**CONCLUSION**
→ For the exact Ligue 1 failure, provider-plan/season entitlement is demonstrated. Wrong league mapping, generic request-shape incompatibility, quota exhaustion and generic application failure are not supported as the cause of those exact requests.

**RECOMMENDATION**
→ Treat API-Football historical capability as `season-entitlement-dependent`; do not build recurring retries around denied full-season historical requests; prefer free bulk sources for bootstrap.

**CONFIDENCE**
→ OBSERVED / ESTABLISHED for the probed requests; do not generalize “2022–2024” as a universal all-league Free contract.

---

## 7. API-Football past-success vs current-failure diagnosis

The question “why could Finsport load La Liga/Premier history but newer leagues fail?” is now sufficiently answered for ticket design.

| Cause candidate | Evidence | Disposition |
|---|---|---|
| Provider-plan restriction | Ligue 1 2025/2026 returns explicit `plan` denial | **CONFIRMED for those requests** |
| Season availability | `/leagues` lists 2025/2026, but `/fixtures` denies them | Catalogue availability is **not** entitlement |
| Wrong request shape | Same `{league, season, timezone}` shape returns La Liga 2024 with 380 rows | **Not supported as generic cause** |
| Wrong competition mapping | `/leagues?id=61` resolves Ligue 1 correctly | **Not supported for probed Ligue 1** |
| Quota | Probe starts with sufficient daily/minute quota; no rate-limit error | **Not cause** |
| Application/client bug | Provider returns structured plan error through current client; control succeeds | **Not supported for exact denial** |
| Combination | Provider entitlement is enough to explain exact observed denial | No additional cause required by evidence |

The provider message “try from 2022 to 2024” is an account/competition response observed on 2026-09-03. It must not be rewritten as an official global rule that Free always provides exactly three seasons.

---

## 8. football-data.co.uk current contract

Current official site evidence:

- historical results are offered in computer-ready CSV/Excel files;
- the main data page currently reports `32 seasons results` and `All FREE!!!`;
- European seasonal archives are downloadable back to 1993/94;
- extra-league pages include Argentina, Brazil and USA and provide league-specific CSV/Excel downloads;
- the site says its data is free and identifies source acknowledgements;
- the current data page states that Football-Data data are made available for purposes of league match prediction. [E2][E3][E6][E7][E8]

This report deliberately does **not** convert “free to download” into a broader legal conclusion such as “unrestricted commercial licence”. For Finsport's local research/backfill use, the source is aligned with league match prediction. Raw dataset redistribution is not part of this ticket; a future commercial redistribution decision would need separate legal/permission review.

Update behavior is useful but not a reason to poll it daily for closed seasons. Historical bootstrap is one-shot. Current/active match lifecycle remains with the canonical current provider.

---

## 9. penaltyblog FootballData current contract

Finsport currently pins `penaltyblog==1.12.0`, and PyPI records `1.12.0` uploaded on 2026-08-21. [E4]

The current official scraper documentation exposes:

```python
pb.scrapers.FootballData.list_competitions()
fb = pb.scrapers.FootballData("ENG Premier League", "2021-2022")
df = fb.get_fixtures()
```

and documents normalized fields including:

- `date` / `datetime`;
- `season`;
- `competition`;
- `team_home`;
- `team_away`;
- source `fthg` / `ftag`;
- normalized `goals_home` / `goals_away`. [E5]

The documented competition list includes the enabled European targets:

- `DEU Bundesliga 1`;
- `ENG Premier League`;
- `ESP La Liga`;
- `FRA Ligue 1`;
- `ITA Serie A`;
- `NLD Eredivisie`;
- `PRT Liga 1`;
- `TUR Super Lig`. [E5]

The local overlap probe then verified that installed 1.12.0 actually downloads and parses the required historical data today. [L1]

### Contract decision

```text
penaltyblog FootballData
→ default acquisition/parser helper for supported European football-data.co.uk leagues

penaltyblog DixonColesGoalModel
→ local modelling library

Prediction path
→ DB-only
```

The two responsibilities must remain separate.

---

## 10. AR/BR/US direct CSV assessment

The current football-data.co.uk extra-league surface lists Argentina, Brazil and USA, and dedicated pages expose CSV/Excel downloads. [E6][E7][E8]

Penaltyblog's documented `FootballData.list_competitions()` does not list these three. [E5]

### Material recommendation

**EVIDENCE**
→ Direct free CSV exists; penaltyblog's public FootballData list does not cover these competitions.

**CONCLUSION**
→ Extending penaltyblog only to hide three simple source downloads would create unnecessary dependency coupling.

**RECOMMENDATION**
→ Use a small direct football-data.co.uk adapter for AR/BR/US that emits the same normalized historical-result record as the European helper.

**CONFIDENCE**
→ STRONG INFERENCE / RECOMMENDATION.

No premium-only API is justified while this source remains adequate.

---

## 11. Peru source research

### Candidates

#### RSSSF — recommended

RSSSF has a Peru historical index and year-specific pages. Checked annual pages include 2016, 2018, 2024 and 2025; the 2025 Primera División page includes round dates and explicit home/away score lines. For example, Round 1 contains `[Feb 7] Sport Huancayo 2-1 Alianza Atlético`, and subsequent dates/results continue chronologically. [E9][E10][E13]

The 2025 page states:

- prepared and maintained by Carlos Manuel Nieto Tarazona for RSSSF;
- copyright by author/RSSSF;
- the document may be copied in whole or part provided proper acknowledgement is given. [E10]

This is a materially clearer usage statement than the alternatives inspected.

RSSSF often gives **calendar date rather than exact kickoff clock time**. The ingestion contract therefore must preserve time precision honestly.

Recommended semantic handling:

```text
source event date is known
exact kickoff clock may be unknown
→ preserve DATE_ONLY precision in source provenance
→ reconcile to exact canonical kickoff when an authoritative existing Match provides it
→ if creating a canonical historical Match from date-only evidence, use a deterministic technical day representation only with explicit DATE_ONLY provenance; never claim the technical anchor is the real kickoff time
```

The exact storage field/representation is preflight implementation detail; the non-fabrication semantic is REQUIRED.

#### Soccerway — fallback/corroboration

The current Liga 1 2025 surface exposes Results / Fixtures / Standings / Archive. [E11]

It is useful as a human-verification fallback but is a dynamic HTML surface with higher scraping fragility and no superior usage contract established in this research. It is not the primary importer.

#### Wikipedia — corroboration only

The Liga1 2025 crossed-results table can corroborate scores but does not independently provide the chronological match-date contract needed for time-weighted historical modelling. Do not use it as the primary source.

#### FootyStats — rejected as free primary

FootyStats lists Peru Primera División dataset seasons from 2013 onward and advertises match CSV/API data, but the historical dataset surface promotes Premium access. [E12]

A paid dataset is not justified while RSSSF provides an adequate free historical path.

### D4 decision

**EVIDENCE**
→ RSSSF annual pages satisfy season identity, date, home, away and full-time goals; pages exist across the local catalogue era; explicit attribution/copy language exists. [E9][E10][E13]

**CONCLUSION**
→ Peru no longer needs to be marked unavailable.

**RECOMMENDATION**
→ Use an RSSSF source-specific one-shot parser for Peru historical results, with explicit attribution, date-precision provenance, competition-section scoping and fail-closed parsing. Keep Soccerway as corroborative fallback only.

**CONFIDENCE**
→ RECOMMENDATION supported by current source evidence. Parser variability across years remains a preflight/test concern, not an unresolved source-strategy decision.

---

## 12. Other source candidates considered/rejected

| Candidate | Disposition | Reason |
|---|---|---|
| football-data.org | REJECT as primary historical source for this work | Does not improve on football-data.co.uk for the required free historical bulk path; avoid adding authenticated API dependency where free CSV suffices. |
| FootyStats | REJECT as free primary | Useful Peru catalogue/depth visibility, but historical data-download workflow is premium-oriented. |
| Soccerway | FALLBACK only | Good human-visible archive/results; HTML/dynamic scraping is more fragile than RSSSF/CSV. |
| Wikipedia | CORROBORATION only | Cross-table lacks chronological date contract for primary time-weighted ingestion. |
| SportsMonks / other premium APIs | REJECT | Premium-only improvement not needed while free adequate sources exist. |
| TheSportsDB | NOT REQUIRED | A catalogue/API candidate was researched, but the final Peru choice has clearer reproducibility/attribution and avoids introducing another API/rate-limit dependency. |

---

## 13. Historical source matrix

### Table B — provider/source comparison

| Source | Cost/auth | Coverage | Historical depth | Schema | Provenance | Stability | Terms | Mapping burden | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| API-Football | Free account 100 req/day; API key | Global/current; historical depends on season entitlement | Account/season dependent; probed La Liga 2024 succeeds; Ligue 1 2025/26 denied | JSON fixtures/league API | Strong provider IDs + existing SourceRefs | Strong API, but plan-gated history | Commercial API plan contract | Low where existing mappings exist | PRIMARY current/canonical; historical only when entitled/useful, not bulk default |
| football-data.co.uk Europe | Free download; no key | Major European leagues | Main archive back to 1993/94 | CSV/Excel; FT result fields | Source URL/file + season/competition | Long-lived site; current archive active | Site says free; data made available for league match prediction; no broad relicensing inference | Medium aliases | **RECOMMENDED historical bulk source** |
| penaltyblog `FootballData` 1.12.0 | Package MIT; underlying source free | Eight enabled European leagues directly documented | Follows football-data.co.uk availability | Normalized pandas DataFrame | Must persist underlying source identity, not “penaltyblog” as data authority | Maintained; 1.12.0 current | Library MIT; source data terms remain football-data's | Low/medium | **RECOMMENDED acquisition helper for supported Europe** |
| football-data.co.uk direct extra-league CSV | Free download; no key | Argentina, Brazil, USA among extra leagues | Dedicated historical/current files; source pages current | CSV/Excel | Source URL/file + competition | Current active pages | Same football-data terms caveat | Medium | **RECOMMENDED direct adapter for AR/BR/US** |
| RSSSF Peru | Free web pages; no auth | Peru annual competitions incl. Primera División | Historical index; spot-checked 2016–2025 era | Structured human-readable HTML/text | Author/RSSSF/page/year | Long-lived archive; year-page formatting may vary | Copy allowed with proper acknowledgement on checked pages | Medium/high source-specific parsing | **RECOMMENDED Peru historical source** |
| Soccerway | Public website | Peru and global | Archive visible | Dynamic HTML | Page/competition/year | Consumer-site UI may change | No superior ingestion permission established here | High | Fallback/corroboration only |
| FootyStats | Public catalogue; premium downloads/API | Peru incl. 2013–2026 | Deep catalogue | CSV/API | Provider dataset | Commercial service | Historical data workflow premium | Low technically, high cost policy | Reject for free-first requirement |
| Inkabet | Existing secondary market source | Betting markets | Not historical result source | Market data | Existing source provenance | Existing fail-soft integration | Existing project contract | N/A | Keep market-only; no DC history role |

---

## 14. Historical depth analysis

The research deliberately separates two questions that were previously conflated:

### 14.1 How much historical evidence should Finsport acquire/store?

Historical results are inexpensive one-shot reference data compared with API quota-driven daily data. Re-downloading them later adds no product value.

**Decision:**

```text
initial historical bootstrap depth
=
all COMPLETED Season rows already present in Finsport's local Season catalogue
∩
approved source availability
```

This gives a natural bounded modern window already curated by Finsport:

- most enabled competitions have Season metadata from roughly 2010/11;
- Argentina from roughly 2015;
- Peru from roughly 2016.

It avoids importing pre-catalogue decades merely because a source has them, while preserving enough stored evidence to re-evaluate model weighting without network re-acquisition.

The current active season is **not** a historical bootstrap target. Its fixtures/results belong to current operation and should continue to accumulate normally.

### 14.2 How much of stored history should pure Dixon-Coles effectively use?

No universal hard number is justified.

The La Liga local walk-forward evaluated the actual stored configurations possible without fabricating seasons:

- current 2024 season-to-date only;
- 2023 completed season + 2024-to-date;
- 2022 + 2023 completed seasons + 2024-to-date;
- all available, which was identical to the third configuration.

The local selected `xi=0.0`, so this study did not establish a decay optimum and cannot prove that arbitrarily deeper equal-weight history is beneficial.

### Material recommendation

**EVIDENCE**
→ Prior history materially improved La Liga coverage/log-loss; local evidence does not support a universal exact season count; the local `xi` was zero; bulk source data are cheap to store once. [L1]

**CONCLUSION**
→ Storage depth should not be constrained by an unproven model-training N; model-training depth/decay should not be inferred from storage depth.

**RECOMMENDATION**
→ Backfill the full approved completed-season intersection with the existing Season catalogue. Keep Dixon-Coles training basis/config versioned and observable. Do not hard-code “3 seasons” as a universal mathematical rule.

**CONFIDENCE**
→ RECOMMENDATION with OBSERVED local support; no universal optimal N claimed.

---

## 15. Overlap/reconciliation study

The local probe downloaded football-data through installed penaltyblog 1.12.0 and compared it read-only to canonical Finsport Matches.

### Table C — overlap audit

| Competition/season | Source rows | Mapped | Exact | Conflicts | Ambiguous | Missing | Duplicate | Disposition |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| La Liga 2022 | 380 | 380 | 380 | 0 | 0 | 0 source / 0 canonical | 0 | PASS — exact after explicit/audit mapping |
| La Liga 2023 | 380 | 380 | 380 | 0 | 0 | 0 / 0 | 0 | PASS |
| La Liga 2024 | 380 | 380 | 380 | 0 | 0 | 0 / 0 | 0 | PASS |
| **La Liga total 2022–2024** | **1,140** | **1,140** | **1,140** | **0** | **0** | **0 / 0** | **0** | Strong source compatibility evidence |
| Premier League 2024 | 380 | 380 | 380 | 0 | 0 | 0 / 0 | 0 | PASS — exact after explicit/audit mapping |

No percentages are inferred; these are measured counts. [L1]

### Alias finding

Audit-only schedule signatures resolved source aliases such as:

- `Ath Bilbao` → `Athletic Club`;
- `Ath Madrid` → `Atletico Madrid`;
- `Betis` → `Real Betis`;
- `Sociedad` → `Real Sociedad`;
- `Vallecano` → `Rayo Vallecano`;
- `Man City` → `Manchester City`;
- `Man United` → `Manchester United`;
- `Nott'm Forest` → `Nottingham Forest`.

**These signatures prove overlap; they are not an authorization for silent fuzzy production mapping.**

---

## 16. Canonical/provenance/conflict contract recommendation

### D6/D7 semantic contract

1. **Source identity**
   - raw/imported record always carries its real source identity;
   - penaltyblog is a parser/helper, not the football-result authority; the source remains football-data.co.uk;
   - RSSSF provenance includes year page and attribution.

2. **Competition mapping**
   - explicit mapping from source competition to Finsport Competition;
   - mapping absent/ambiguous → unresolved/fail closed.

3. **Season mapping**
   - map to an existing Finsport Season when available;
   - never fabricate a season label silently;
   - source-specific calendar-year vs cross-year rules are explicit.

4. **Team mapping**
   - use explicit source IDs where available or explicit alias/mapping tables;
   - audit-derived similarity/schedule signatures may propose a mapping for human/preflight review but may not silently persist it as canonical.

5. **Match identity/reconciliation**
   - competition + season + mapped home/away + date/kickoff evidence;
   - reconcile to an existing canonical Match when uniquely identified;
   - ambiguous candidate set → unresolved.

6. **Date normalization**
   - preserve source timezone/precision;
   - exact source timestamp → normalize normally;
   - date-only source → preserve `DATE_ONLY` semantic precision; no invented exact kickoff claim.

7. **Score/status normalization**
   - only final/valid match outcomes enter Dixon-Coles training;
   - awarded/annulled/postponed source peculiarities must be parsed explicitly and tested;
   - contradictory canonical outcome/score is data-integrity failure, not “small history”.

8. **Duplicates/idempotency**
   - repeated import of same source data produces no duplicate canonical Match/evidence;
   - provenance/source references are idempotent.

9. **Overlap behavior**
   - if an API-Football-backed canonical Match already exists and secondary data agree, preserve canonical Match and add/corroborate secondary provenance as appropriate;
   - do not rewrite source identity.

10. **Conflict behavior**
    - if API-Football-backed canonical result exists and secondary source disagrees: keep canonical value unchanged, record conflict/audit evidence, no silent overwrite;
    - if only secondary sources conflict and no canonical API-F authority exists: do not choose a winner silently; mark unresolved/conflict pending explicit adjudication.

11. **Canonical vs research-only disposition — CLOSED**

```text
A. secondary historical results
→ reconciled into canonical Match history
→ with explicit secondary source provenance
```

A separate research-only historical store is not justified for ordinary results because Dixon-Coles is already DB/canonical-history oriented and the overlap demonstrates compatibility.

### Material recommendation

**EVIDENCE**
→ 1,520 audited source rows across La Liga/Premier reconcile exactly after controlled mappings; source aliases exist but no score/date conflict was observed. [L1]

**CONCLUSION**
→ Canonical ingestion is viable without destructive rewriting of trusted API-Football history.

**RECOMMENDATION**
→ Reuse the existing reconciliation path, add explicit source mappings/provenance/conflict audit semantics, and fail closed on ambiguity.

**CONFIDENCE**
→ OBSERVED for overlap; RECOMMENDATION for production policy.

---

## 17. Inkabet current execution audit

Local audit already closed the behavior:

```text
due ODDS_CAPTURE
→ primary successful/accepted capture result
→ Inkabet attempted for due matches
→ secondary market data may persist
→ secondary failure remains fail-soft/auditable
```

Inkabet is:

```text
SECONDARY
market-only
not a football-result authority
not Dixon-Coles historical training evidence
```

No external Inkabet research was required.

If provider modules are physically reorganized, moving Inkabet code is permitted as a structural refactor only.

```text
Inkabet functional behavior change → OUT unless a new finding appears
Inkabet structural move → MAY/ABSORB if required by provider organization
```

---

## 18. External-provider/ingestion architecture options

### Table F — architecture options

| Option | Ownership | Reuse | Testability | Provenance | Complexity | Migration/scope risk | Recommendation |
|---|---|---|---|---|---|---|---|
| A — keep current root modules + one historical adapter | New source ownership remains scattered | Reuses current paths but encourages source-specific branching | Adequate initially | Harder to keep source parsing boundaries clear | Low immediate | Medium future entropy | **REJECT**: third real source threshold crossed |
| B — focused provider/source organization + thin normalized historical-result contract into existing reconciliation | Clear source-specific fetch/parse ownership | High reuse of existing reconciliation/sync/canonical domain | High: provider parsers isolated; reconciliation tests reused | Explicit and source-specific | Moderate | Controlled | **RECOMMENDED** |
| C — full provider adapters + separate generalized ingestion/staging/reconciliation subsystem | Very explicit layers | Potentially high | High | High | High | High; risks speculative framework/staging | **REJECT for current scope** unless F009 preflight finds unavoidable concrete need |

The recommendation is semantically **Option B with one thin normalization boundary**. It intentionally borrows the useful separation from C without creating a generic framework.

---

## 19. Recommended architecture boundary

Conceptually:

```text
source-specific acquisition/parser
(API-Football | football-data via penaltyblog | direct football-data CSV | RSSSF Peru | Inkabet market adapter)
        ↓
small source-neutral normalized record appropriate to that evidence type
        ↓
existing reconciliation / canonical persistence ownership
        ↓
canonical Finsport entities + explicit Source provenance
```

Rules:

- no network access from Prediction/model code;
- no generic plugin registry/framework;
- no new Django app solely for provider abstraction;
- no universal abstract class hierarchy unless real duplication in F009 proves it necessary;
- no new historical staging database by default;
- source parser fixtures can be tested independently;
- canonical reconciliation remains domain-owned and reusable.

### Historical bootstrap lifecycle

When `Competition.enabled` changes from false to true:

- **do not** perform provider HTTP inside the Admin model-save transaction;
- request/enqueue/mark historical bootstrap work for the existing execution owner;
- process it idempotently outside the request transaction;
- use a source ladder chosen by D1;
- persist semantic coverage status.

A single `history_imported` boolean is insufficient. Required semantic states:

```text
NOT_ATTEMPTED
COMPLETE
PARTIAL
UNAVAILABLE
FAILED
```

and the audit basis must identify at least:

- source/strategy version;
- requested completed-season set/depth;
- successfully covered seasons;
- unresolved/failed seasons;
- source attempt/cost summary;
- timestamp/currentness;
- reason/diagnostics.

After `COMPLETE`, ordinary daily wakes must not re-download historical closed seasons.

---

## 20. Dixon-Coles current readiness problem

Current code effectively treats:

```text
history != empty
→ attempt penaltyblog fit
```

as the fit gate.

Local deterministic evidence disproves that as a sufficient maturity/readiness contract:

- 0 rows → `UNAVAILABLE: INSUFFICIENT_TRAINING_HISTORY`;
- 1, 2, 4 connected rows → fit object exists, but prediction raises `ValueError: goal_matrix contains negative probabilities`;
- 8 connected rows → produced in the synthetic case;
- 8 disconnected rows → negative-probability exception;
- target team absent from training → `UNAVAILABLE: INSUFFICIENT_TEAM_HISTORY`;
- canonical outcome contradicting the FT score → input integrity `ValueError`. [L1]

Therefore:

```text
count alone
!=
structural readiness
```

and N=8 remains explicitly non-universal.

---

## 21. Dixon-Coles empirical readiness study

La Liga evaluation season/year label: 2024. Target count: 380. Selected local `xi=0.0` from existing backtest experiment 11. [L1]

### Table D — Dixon-Coles readiness candidates

| Rule/tier | Fit coverage | Prediction coverage | Log-loss | Calibration | Accuracy | Stability | Complexity | Recommendation |
|---|---:|---:|---:|---|---:|---|---|---|
| Current-season-to-date only (`[2024]`) | 142 fit batches; 1 empty-history fit unavailable; 36 target failures | 334/380 = **87.89%** | **1.1224** | confidence ECE **0.0728**; class bins noisy | 48.20% | mean TV vs all **0.0970**, max 0.9623 | Low | **Reject as mature default**; useful exploratory evidence only |
| 1 completed prior season + current-to-date (`[2023,2024]`) | 142 batches; no fit failure | 378/380 = **99.47%** | **0.9939** | ECE **0.0302** (best observed ECE) | 50.53% | mean TV **0.0449** | Low | Stronger observed maturity; not universal threshold |
| 2 completed prior seasons + current-to-date (`[2022,2023,2024]`) | 142 batches; no fit failure | 379/380 = **99.74%** | **0.9718** (best observed log-loss) | ECE **0.0650** | 53.56% | identical to ALL_AVAILABLE locally | Low | Best observed log-loss/coverage, but no proof of global optimality |
| >2 completed prior seasons | **NOT LOCALLY AVAILABLE** | **PENDING FUTURE EVIDENCE** | — | — | — | — | — | Do not fabricate a result |
| Premier multi-season comparison | **INSUFFICIENT_STORED_SEASONS_FOR_DEPTH_COMPARISON** | — | — | — | — | — | — | Does not support cross-league generalization yet |
| Global numeric match threshold | Synthetic/count evidence conflicts with structure | — | No stable evidence | No stable evidence | Secondary | Connectivity and history source matter | Superficially simple but false | **NO_GLOBAL_THRESHOLD_JUSTIFIED** |

### Descriptive team-history evidence — not thresholds

For the current-season-only La Liga arm:

- min team history `0`: 0/10 produced;
- `1–4`: 16/40 produced, mean log-loss 3.359, mean TV 0.333;
- `5–9`: 39/50, log-loss 1.024, TV 0.161;
- `10–19`: 99/100, log-loss 1.104, TV 0.083;
- `20+`: 180/180, log-loss 0.955, TV 0.070. [L1]

These buckets are **descriptive evidence, not a readiness rule**. The 2-season configuration also shows that sparse team-history buckets can produce once league-level prior history is richer, reinforcing that one scalar count is insufficient.

Metrics priority remains:

1. multinomial log-loss;
2. calibration;
3. coverage;
4. probability stability;
5. accuracy secondary;
6. ROI/profit/post-selection hit rate **not a Prediction-readiness criterion**.

---

## 22. Recommended fit-attempt readiness

`FIT_ATTEMPTABLE` is intentionally not the same as “safe for betting”. Its goal is to avoid nonsensical library calls while still permitting exploratory evidence.

### Required structural gate

Before attempting the pure Dixon-Coles arm:

1. training rows are canonical eligible FT matches with known scores;
2. score/outcome consistency passes data-integrity validation;
3. target home and away teams both occur in same-league training evidence;
4. the training relationship graph required by the fit is not structurally disconnected in a way known to make the target/model unidentified; graph diagnostics are recorded;
5. model inputs and time-weight configuration are valid;
6. fit/predict execution is wrapped so a known invalid/unstable probability result cannot escape unclassified;
7. produced vector must be finite, each probability in `[0,1]`, and sum to approximately 1.

No universal numeric minimum is frozen by research.

A competition/model readiness profile MAY later add a numeric evidence floor, but that floor is versioned evidence—not a hard-coded mathematical truth.

### Fit result semantics

```text
structural precondition fails
→ UNAVAILABLE + stable reason

structural preconditions pass
→ fit/predict may be attempted

fit/predict yields valid probability vector
→ PRODUCED Prediction
```

A produced Prediction can still have `bet_eligible=false`.

---

## 23. Recommended bet-readiness contract

### Result B — NO_GLOBAL_THRESHOLD_JUSTIFIED

Research does not justify one universal match/season threshold across competitions.

The ticket must therefore implement a versioned readiness contract that can represent:

- model code/version/config;
- competition;
- training evidence identity/hash;
- training depth/basis;
- league history count;
- home-team same-league history;
- away-team same-league history;
- unique teams/connectivity diagnostics;
- effective decayed evidence when `xi > 0`;
- fit/output validity;
- readiness profile/version;
- `bet_eligible`;
- reason.

### Default policy

```text
valid ProbabilityResult
+
no approved readiness profile for this competition/config
→ persist exploratory Prediction
→ bet_eligible = false
```

A profile becomes betting-approved only through explicit evidence/decision, not because the model happened to stop throwing exceptions.

The previously closed promoted-team rule is preserved:

```text
truly promoted/new-to-league team
→ not bet-eligible until the approved same-league evidence requirement is met
→ no lower-division transfer into pure DIXON_COLES
```

This rule itself is not open. Only future profile calibration can refine what “sufficient same-league evidence” means.

---

## 24. `UNAVAILABLE` vs `FAILED` contract

### Table E — failure/status semantics

| Condition | Current behavior | Desired status | Reason | Operational incident? |
|---|---|---|---|---|
| No eligible history | Already returns unavailable | `UNAVAILABLE` | `INSUFFICIENT_TRAINING_HISTORY` | No |
| Target team absent from same-league history | Already returns unavailable at predict | `UNAVAILABLE` | `INSUFFICIENT_TEAM_HISTORY` | No |
| Known structural disconnect / readiness precondition failure | Can reach penaltyblog and fail | `UNAVAILABLE` | stable structural-readiness reason | No |
| Sparse/unvalidated exploratory basis causes known invalid goal matrix / invalid probabilities | Currently may raise exception | `UNAVAILABLE` while evidence profile is below approved readiness; diagnostic retained | expected evidence instability, not an incident | No |
| Same library/runtime failure after evidence satisfies an approved readiness profile | Currently may bubble to pipeline error | `FAILED` | unexpected penaltyblog/runtime defect with diagnostics | **Yes** |
| Probability vector non-finite/out-of-range/not summing correctly after approved readiness | not fully classified | `FAILED` | invalid model output | Yes |
| Canonical FT score contradicts canonical outcome/input | raises `ValueError` | `FAILED` data-integrity/input contract; do not mislabel as small history | corrupt/contradictory canonical evidence | Yes/data-quality |
| Historical source unavailable/denied for a required season | maintenance/provider degraded today | historical coverage `UNAVAILABLE` or `PARTIAL`, source reason preserved | source/plan limitation | Usually no model incident; operationally auditable |
| Ambiguous team/match mapping | current generalized behavior varies | unresolved/fail closed; no canonical overwrite | identity ambiguity | No unless unexpected volume/spike |
| Trusted source score conflict | policy previously incomplete | preserve canonical authority, record conflict; no silent overwrite | source conflict | Audit/review event |

The key boundary is not the Python exception class alone; it is **whether the evidence had already passed the approved readiness contract**.

---

## 25. Continuous Prediction/recompute trigger

Current `_prediction_candidates` is tied to due `ODDS_CAPTURE` items. [L1]

That is conceptually wrong for pure Dixon-Coles because odds are not model inputs.

### Desired trigger

```text
known target Match
+
relevant canonical football evidence basis changed
+
arm structurally attemptable
→ create/recompute versioned DIXON_COLES Prediction
```

Relevant change includes:

- target Match discovered or material target football identity changed;
- new canonical FT Match in same competition enters training history;
- canonical score/status/kickoff correction changes eligible training evidence;
- historical backfill/reconciliation changes the training basis;
- model/version/config/readiness profile changes.

Not relevant:

```text
new bookmaker price only
→ no Dixon-Coles model recompute
```

### Evidence identity

The semantic identity must incorporate or derive a deterministic football-evidence basis sufficient to detect unchanged work, including:

- target Match identity;
- model version/config;
- cutoff/basis time;
- deterministic training evidence identity/high-water/hash over relevant canonical evidence;
- readiness profile/version where it changes semantics.

Exact hashing/storage implementation is preflight work.

The existing wake/scheduler ownership remains. No second scheduler.

---

## 26. Prediction versioning/audit contract

Current uniqueness:

```text
PredictionExperiment prospective:
(competition, logical_identity)

Prediction:
(experiment, match, model_code, variant)
```

Therefore the minimum audit-preserving semantic is:

```text
same football evidence basis
→ same prospective experiment identity / no duplicate work

relevant football evidence changes
→ new prospective experiment/evidence identity
→ new Prediction rows
→ prior experiment/Predictions preserved
```

Do not silently update the previous Prediction into a new probability state.

Each predictive evidence version MUST preserve semantically:

- cutoff;
- target Match;
- training evidence identity/hash;
- training counts/readiness diagnostics;
- model version/config;
- time-weight/depth configuration;
- readiness profile/tier/version;
- `bet_eligible`;
- unavailable/failed reason when no Prediction is produced;
- created-at/provenance sufficient for audit.

Exact ORM fields belong to F009 preflight/implementation.

---

## 27. Decision integration for below-readiness Predictions

Current policy functions act directly on a valid probability result; `modal_all` emits the modal outcome. [L1]

That behavior needs a readiness boundary.

Desired semantics:

```text
valid ProbabilityResult
→ persist Prediction

Prediction.bet_eligible = false
→ Decision layer produces NO_BET with readiness reason
→ Prediction remains queryable/reportable
→ do not enter betting-eligible/economic evaluation cohort
```

This preserves the established distinction:

```text
Prediction != Decision
NO_BET is a Decision state
```

A below-readiness Prediction is not “no prediction”; it is useful exploratory model evidence that is intentionally barred from betting decisions.

---

## 28. Offline test contract

Required test boundary:

### Provider/ingestion

- parser tests use frozen HTTP/file fixtures; no live provider dependency in normal test suite;
- Europe penaltyblog FootballData adapter contract mocked/frozen at network edge;
- AR/BR/US direct CSV parser fixtures;
- RSSSF Peru parser fixtures from multiple format eras/years;
- source identity/provenance preserved;
- idempotent re-import;
- explicit alias mapping;
- ambiguous mapping fail closed;
- conflict does not overwrite canonical API-F result;
- date-only precision preserved;
- awarded/annulled/postponed cases explicit.

### Dixon-Coles

Tests must use real local `penaltyblog.models.DixonColesGoalModel` with zero external HTTP and include:

- zero history;
- sparse connected history;
- disconnected history;
- unseen target team;
- contradictory canonical result input;
- valid connected history;
- valid probability vector checks;
- known low-evidence negative-goal-matrix behavior normalized correctly;
- approved-readiness unexpected failure → FAILED;
- below-readiness valid Prediction → `bet_eligible=false` → Decision `NO_BET`;
- bookmaker-price-only change does not create a new Dixon-Coles evidence version;
- new FT/backfill evidence does create a new version;
- unchanged evidence is idempotent/no duplicate work;
- prior Predictions remain auditable.

No live API-Football calls are required in the regression suite.

---

## 29. Observability/audit contract

Historical bootstrap must make the following diagnosable without reading raw secrets/payloads:

- Competition;
- source/adapter;
- strategy/version;
- requested seasons;
- accepted/mapped/unresolved/conflicting counts;
- created/updated/unchanged counts;
- coverage result (`COMPLETE/PARTIAL/UNAVAILABLE/FAILED`);
- provider call/download count where applicable;
- plan/quota/source failure classification;
- ambiguous mappings/conflicts by stable non-secret identifiers;
- provenance identifiers/URLs as appropriate.

Dixon-Coles predictive audit must expose:

- evidence basis identity;
- training counts/teams/connectivity/effective weight diagnostics;
- fit readiness reason;
- Prediction production status;
- bet readiness profile/version;
- `bet_eligible` reason;
- `FAILED` diagnostics only when failure is operationally unexpected after readiness.

This extends existing observability principles; it does not create a second observability stack.

---

## 30. Combined-ticket coherence assessment

### Falsification review

The brief required split/reconsideration if research found a material independent boundary. It did not:

1. API-Football is **not** the only acceptable source → falsifier not triggered.
2. football-data overlap is not too ambiguous → 1,520/1,520 audited rows exact after controlled mapping → not triggered.
3. penaltyblog FootballData is currently reproducible with installed 1.12.0 → not triggered.
4. source coverage exists for the majority/all current enabled leagues using Europe + direct extra CSV + RSSSF Peru → not triggered.
5. provider refactor can remain focused/minimal → no independent framework rewrite required.
6. readiness can be explicit via Result B without a separate model project → not triggered.
7. Prediction versions can be preserved through experiment/evidence identity without a separate architecture program → not triggered.
8. pipeline does **not** already have the correct sports-data trigger → orchestration finding confirmed.
9. historical data materially improves observed La Liga coverage/log-loss → not triggered.
10. provenance contract does not require destructive canonical rewrite → not triggered.
11. regression testing can be offline/controlled → not triggered.
12. season-aware challenger is not required for pure arm correction → not triggered.

### Decision

**COMBINED_TICKET_RECOMMENDED**

The shared acceptance story is coherent:

```text
approved historical result sources
→ one-shot idempotent canonical backfill with provenance
→ explicit Dixon-Coles structural/readiness state
→ sports-evidence-driven versioned Predictions
→ below-readiness Predictions preserved but NO_BET
```

A split is not justified solely because the implementation touches acquisition, persistence and prediction layers.

---

## 31. REQUIRED / MAY / OUT for the future ticket

### Table G — final ticket scope

| Area | REQUIRED | MAY | OUT | Preflight-only |
|---|:---:|:---:|:---:|:---:|
| Historical one-shot bootstrap lifecycle per enabled Competition | ✓ |  |  |  |
| Historical coverage state richer than boolean | ✓ |  |  | exact model/field names |
| Source ladder per D1 | ✓ |  |  | exact source URL templates/current mappings |
| football-data Europe via installed penaltyblog helper | ✓ |  |  | confirm current method signatures at implementation start |
| Direct football-data AR/BR/US adapter | ✓ |  |  | exact file/season enumeration |
| RSSSF Peru parser with attribution/date precision | ✓ |  |  | exact parser variants for each local Season year |
| Canonical reconciliation/provenance/idempotency | ✓ |  |  | exact ORM wiring |
| Explicit aliases; ambiguity fail closed | ✓ |  |  | enumerate aliases from import dry run |
| Conflict audit/no silent overwrite | ✓ |  |  | exact persistence structure |
| Refactor to focused provider/source organization | ✓ |  |  | physical filenames/package layout |
| Generic provider plugin framework |  |  | ✓ |  |
| New Django app solely for provider abstraction |  |  | ✓ |  |
| Generalized staging subsystem |  |  | ✓ |  |
| Inkabet structural move if provider organization benefits |  | ✓ |  | decide physical move from diff/preflight |
| Inkabet functional behavior change |  |  | ✓ unless finding |  |
| Disable recurrent historical full-season calls after COMPLETE | ✓ |  |  | exact ownership/wake wiring |
| Absorb/supersede historical role of existing `SEASON_BOOTSTRAP` |  | ✓ / **POTENTIAL_SUPERSEDE** |  | confirm old/current discovery responsibilities separately |
| `PIPELINE_OVERDUE` backlog work |  |  | ✓ |  |
| Pure DC structural readiness gate | ✓ |  |  | exact helper names |
| Result B configurable/versioned betting-readiness contract | ✓ |  |  | exact schema |
| Preserve exploratory Predictions with `bet_eligible=false` | ✓ |  |  | exact persistence fields |
| `UNAVAILABLE` vs `FAILED` semantics | ✓ |  |  | exception mapping details |
| Sports-evidence-driven recompute | ✓ |  |  | exact evidence hash algorithm |
| Versioned/intermediate Prediction evidence | ✓ |  |  | exact identity storage |
| Decision NO_BET boundary for below-readiness Predictions | ✓ |  |  | exact policy hook |
| Existing scheduler ownership | ✓ |  |  | inspect current task wiring at preflight |
| New scheduler |  |  | ✓ |  |
| Season-aware/dynamic/feature-enriched Dixon-Coles challenger |  |  | ✓ |  |
| Odds/xG/players/lineups as pure DC inputs |  |  | ✓ |  |
| Historical odds backfill |  |  | ✓ |  |
| Real betting |  |  | ✓ |  |
| Cross-model frontend applicability redesign |  |  | ✓ |  |

---

## 32. Preflight-only facts

F008 should not re-run research. It should audit readiness and define the approved package/ticket. Before that definition, it may verify only mutable implementation facts such as:

- exact current checkout SHA and cleanliness;
- current `penaltyblog` installed version/signatures;
- current provider/reconciliation module locations;
- current `Source`/SourceRef/Season/Match schema;
- current task/wake hooks;
- current Prediction/Experiment constraints;
- current Admin Competition enablement path;
- exact available source mappings/aliases after a dry-run inventory;
- exact old `SEASON_BOOTSTRAP` responsibilities that remain necessary for current-season discovery;
- exact storage representation required for historical coverage status and date-only precision.

Do not ask F008 to decide source strategy, readiness philosophy, provider architecture class, or canonicalization policy; those are closed here.

Correct lifecycle:

```text
F008
→ audit research
→ readiness
→ define approved ticket/package

F009
→ preflight
→ implementation
→ evidence/UAT/PR/closure
```

---

## 33. Falsification results

Research recommendations would be falsified if later authoritative evidence shows, for example:

- football-data current access/terms no longer permit the intended prediction research use;
- RSSSF year pages for the required local Season set cannot be parsed/reproduced with acceptable completeness;
- overlap on additional leagues reveals material score/date conflicts not visible in La Liga/Premier;
- additional multi-league empirical evidence shows the recommended Result B contract cannot be made stable without an independent readiness model;
- the actual implementation cannot preserve prediction evidence versions without an independently large persistence redesign;
- a preflight reveals that current pipeline already contains a separate sports-evidence trigger not visible at the audited SHA;
- historical bootstrap cannot be separated cleanly from current daily discovery without introducing unsafe lifecycle ambiguity.

None is currently demonstrated.

---

## 34. Remaining OPEN questions

There are **no material research questions blocking F008**.

The following are deliberately non-blocking implementation/preflight or future-calibration questions:

- exact physical package/file organization;
- exact ORM fields for coverage status, date precision, readiness profile and evidence identity;
- exact source alias rows required beyond the measured La Liga/Premier set;
- exact RSSSF parser variants required per Peru year;
- future per-competition numerical readiness thresholds, if/when enough multi-league evidence exists;
- future re-selection of Dixon-Coles weighting/hyperparameters after deeper backfill;
- whether Inkabet files physically move under focused provider organization;
- exact mechanism by which Admin enablement requests the one-shot bootstrap.

These must not be mistaken for permission to let implementation choose the semantic policy.

---

## 35. Separate backlog: season-aware/dynamic Dixon-Coles challenger

Preserve as:

**ORDERED RESEARCH CANDIDATE / BACKLOG — OUT OF NEXT TICKET**

Future question:

```text
pure multi-season Dixon-Coles with versioned history/weight configuration
vs
explicit season-boundary/dynamic/feature-enriched challenger
```

Do not implement its parameters in the current pure-arm correction.

The local finding that prior history helps while `xi=0.0` was selected makes this future comparison interesting; it does not authorize absorbing it now.

---

## 36. New Work Discovered

### NW-1 — one-shot historical coverage lifecycle

**evidence**
→ current maintenance can repeatedly attempt full-season current empty Seasons; historical closed data does not need recurrent download; user workflow enables leagues incrementally; API quota is finite. [L2]

**impact**
→ without explicit coverage state, denied/complete history can consume quota repeatedly and cannot distinguish completion from unavailability.

**recommendation**
→ include competition-scoped historical coverage lifecycle in the combined package; request bootstrap on first enablement or explicit retry, process outside Admin transaction, stop ordinary historical calls after COMPLETE.

### NW-2 — `SEASON_BOOTSTRAP` potential supersession

**evidence**
→ existing `SEASON_BOOTSTRAP` current+empty path sends a full-season API-Football request; Ligue 1 current-season request is plan-denied, while historical bootstrap now has a source ladder and separate lifecycle. [L0c][L2]

**impact**
→ part of the old maintenance behavior overlaps the new historical responsibility and can waste quota.

**recommendation**
→ **POTENTIAL_SUPERSEDE / ABSORB DECISION REQUIRED** in F008: replace only the historical-bootstrap responsibility coherently; preserve current fixture/result discovery responsibilities that are distinct.

### NW-3 — explicit source alias ownership

**evidence**
→ measured overlap required aliases such as `Ath Bilbao`, `Sociedad`, `Man City`, `Nott'm Forest`. [L1]

**impact**
→ source integration needs explicit mappings; production fuzzy matching would violate fail-closed policy.

**recommendation**
→ make source-specific explicit aliases/mappings auditable and testable; ambiguous new aliases remain unresolved.

### NW-4 — date-only historical precision

**evidence**
→ RSSSF provides calendar dates but may not provide exact kickoff clock time. [E9][E10]

**impact**
→ current canonical match model/time weighting may expect a timestamp; pretending a fabricated clock time is exact would corrupt provenance.

**recommendation**
→ preserve date-only precision explicitly and ensure model weighting/reconciliation does not misrepresent technical normalization as observed kickoff time.

### NW-5 — future competition-specific readiness calibration

**evidence**
→ La Liga supports Result B but Premier lacks enough local historical seasons for cross-league threshold validation. [L1]

**impact**
→ a universal numerical threshold is not currently defensible.

**recommendation**
→ implement versioned configurable profiles now; future calibration can promote profiles without redesigning Prediction semantics.

---

## 37. Exact handoff to F008

### DECISIONS CLOSED

1. Historical results are one-shot reference evidence, not daily polling work.
2. Preferred historical sources:
   - enabled Europe: football-data.co.uk through penaltyblog `FootballData` where documented;
   - AR/BR/US: direct football-data.co.uk CSV adapter;
   - PE: RSSSF annual Peru parser with attribution/date precision;
   - API-Football: retain as primary current/canonical provider and optional entitled historical source, not bulk default.
3. Initial storage depth: all completed Season rows already represented locally and supported by the approved source; do not repeatedly fetch them.
4. Secondary historical results reconcile into canonical `Match` history with explicit source provenance.
5. Existing API-Football-backed canonical result remains authoritative when secondary source disagrees; conflict is auditable and never silently overwrites.
6. Ambiguous identity fails closed.
7. Third-provider threshold is crossed; use focused source-specific provider organization plus a thin normalization contract into existing reconciliation.
8. No generic plugin framework/new Django app/general staging architecture.
9. Inkabet behavior remains market-only/fail-soft; structural move MAY be absorbed, functional change OUT unless finding.
10. `fit-attempt readiness != valid ProbabilityResult != bet eligibility`.
11. `N=8` is not universal; no global numeric threshold is justified.
12. Result B: versioned/configurable readiness profile; unvalidated competition/config Predictions may be preserved but are `bet_eligible=false`.
13. Promoted/new-to-league rule remains closed: no lower-division transfer; not bet-eligible until sufficient approved same-league evidence.
14. Known evidence insufficiency/structural instability → `UNAVAILABLE`; unexpected failure after approved readiness → `FAILED`.
15. Pure DC recompute is driven by football evidence changes, not price changes.
16. Relevant new evidence creates a new Prediction experiment/evidence version; prior predictive evidence is preserved.
17. Below-readiness produced Prediction → Decision `NO_BET`, not deletion/no-prediction.
18. Pure arm remains multi-season/no hard reset; season-aware/dynamic challenger remains separate OUT.
19. Tests are offline and use real local penaltyblog model; provider network is mocked/frozen.
20. Existing scheduler ownership remains; no second scheduler.
21. Real betting remains forbidden.

### OPEN QUESTIONS

No research-blocking questions. Only preflight/implementation details listed in section 34.

### PRE-FLIGHT ONLY FACTS

Use section 32. Do not repeat broad provider/statistical research.

### COMBINED-TICKET COHERENCE

**COMBINED_TICKET_RECOMMENDED.**

The package is coherent because historical evidence ingestion is the prerequisite for honest Dixon-Coles applicability, the provider refactor is the minimum boundary required to ingest that evidence, and the Prediction/readiness correction is the consumer-side semantic completion of the same evidence lifecycle.

### REQUIRED

Use Table G REQUIRED column as package authority.

### MAY

- Inkabet structural relocation only;
- coherent absorption/supersession of the historical part of old `SEASON_BOOTSTRAP` if preflight proves ownership overlap;
- small reusable normalization helpers where concrete duplication exists.

### OUT

- season-aware/dynamic/feature-enriched Dixon-Coles challenger;
- generic provider framework/new Django app/staging platform;
- historical odds backfill;
- feature enrichment (xG/shots/players/coaches/lineups) of pure DC;
- `PIPELINE_OVERDUE` backlog;
- cross-model frontend redesign;
- real betting.

### NEW WORK DISCOVERED

Use section 36. Do not assign automatic ticket IDs.

### EXACT HANDOFF TO F008

F008 should:

1. audit that this report and referenced local evidence are present/current enough;
2. run only mutable preflight checks from section 32;
3. decide whether old `SEASON_BOOTSTRAP` historical ownership is absorbed without swallowing unrelated maintenance backlog;
4. translate Table G + D1–D17 contracts into one approved ticket/package if no new material contradiction is found;
5. not implement;
6. hand the approved package to the F009 execution lifecycle.

F008 is **audit/readiness/ticket-definition**, not implementation.

---

## D1–D17 integrity gate

### D1 — Historical source strategy per current enabled league

**STATUS:** ANSWERED

**EVIDENCE:** Table A; football-data current source surfaces; penaltyblog competition list; RSSSF Peru; API-F live probe. [E2][E5][E6][E9][L2]

**DECISION:** Per-competition source ladder is fixed by Table A. Bulk historical default is football-data for supported Europe/AR/BR/US; RSSSF for Peru; API-F remains canonical/current and optional entitled history.

**REMAINING INPUT:** Preflight-only exact source mappings/URLs and alias rows; no research decision remains.

### D2 — API-Football historical viability

**STATUS:** ANSWERED

**EVIDENCE:** Official Free contract + four-call account probe. La Liga 2024 returned 380; Ligue 1 2025/26 explicitly denied by plan; `/leagues` still listed them. [E1][L2]

**DECISION:** Historical use is season-entitlement-dependent; same request shape works for entitled season; denied seasons must not be retried daily. Provider-plan restriction explains the exact observed Ligue 1 failures.

**REMAINING INPUT:** None for ticket definition. Do not generalize 2022–2024 to every league without evidence.

### D3 — football-data.co.uk ingestion contract

**STATUS:** ANSWERED

**EVIDENCE:** Current football-data archive pages, penaltyblog 1.12.0 docs, real overlap downloads. [E2][E3][E4][E5][L1]

**DECISION:** penaltyblog FootballData is default acquisition helper for documented Europe; direct adapter for AR/BR/US. Persist underlying source identity.

**REMAINING INPUT:** Preflight-only parser signature/file enumeration.

### D4 — Peru historical source

**STATUS:** ANSWERED

**EVIDENCE:** RSSSF Peru history/year pages include chronological Primera División results and explicit attribution/copy statement; checked 2016/2018/2024/2025-era pages. [E9][E10][E13]

**DECISION:** RSSSF primary historical source-specific parser; Soccerway corroborative fallback; Wikipedia not primary; premium FootyStats rejected.

**REMAINING INPUT:** Preflight parser-variation tests and explicit date-only storage representation.

### D5 — Historical depth

**STATUS:** ANSWERED — evidence-limited/no universal training N

**EVIDENCE:** La Liga walk-forward; Premier insufficient multi-season local history; selected xi=0.0; source/bootstrap economics. [L1]

**DECISION:** Acquisition depth = all completed local Season catalogue rows supported by approved source, one-shot. Do not hard-code a universal model N; training/readiness depth remains versioned. Current-only evidence is empirically weaker in La Liga; deeper-than-two-prior-season global superiority is not claimed.

**REMAINING INPUT:** Future calibration can refine per-competition model profiles; not a blocker because Result B/configurable contract is explicit.

### D6 — Canonicalization/provenance contract

**STATUS:** ANSWERED

**EVIDENCE:** 1,520-row exact overlap after controlled mappings; aliases identified; no conflicts in audited samples. [L1]

**DECISION:** explicit source/competition/season/team mapping; fail closed ambiguity; date/score/status normalization; idempotency; API-F canonical preservation; auditable conflicts; no silent fuzzy reconciliation.

**REMAINING INPUT:** Exact ORM representation only.

### D7 — Canonical vs research-only disposition

**STATUS:** ANSWERED

**EVIDENCE:** Strong overlap and current DB-only model architecture. [L1]

**DECISION:** **A — secondary historical results reconcile into canonical Match history with explicit source provenance.**

**REMAINING INPUT:** None.

### D8 — Provider/ingestion architecture refactor

**STATUS:** ANSWERED

**EVIDENCE:** Current root-level provider inventory + real additional football-data/RSSSF sources. [L1]

**DECISION:** Option B + thin normalized historical-result contract into existing reconciliation. No generic framework/new app/general staging.

**REMAINING INPUT:** Physical filenames/package moves are preflight implementation detail.

### D9 — Inkabet execution audit

**STATUS:** ANSWERED

**EVIDENCE:** Local checkout execution path already closed.

**DECISION:** Current functional behavior remains; market-only secondary; no historical role. Structural relocation MAY be absorbed.

**REMAINING INPUT:** None unless preflight reveals a new functional finding.

### D10 — Dixon-Coles mathematical/structural readiness

**STATUS:** ANSWERED — non-numeric structural contract

**EVIDENCE:** deterministic penaltyblog probes show zero/sparse/disconnected/unseen/data-integrity classes; count alone fails. [L1]

**DECISION:** structural fit-attempt gate + valid output validation + separate betting profile. No universal N.

**REMAINING INPUT:** Exact helper/diagnostic field names only.

### D11 — Dixon-Coles betting-readiness threshold

**STATUS:** ANSWERED — Result B

**EVIDENCE:** La Liga walk-forward metrics improve with prior history but do not yield a stable universal scalar threshold; Premier cannot generalize; descriptive team-history buckets vary. [L1]

**DECISION:** `NO_GLOBAL_THRESHOLD_JUSTIFIED`; implement versioned configurable/tiered readiness profiles, default unapproved profile to `bet_eligible=false`; optimize readiness on log-loss/calibration/coverage/stability, not ROI.

**REMAINING INPUT:** Future per-competition numeric calibration is allowed but does not block the semantic ticket.

### D12 — Penaltyblog failure semantics

**STATUS:** ANSWERED

**EVIDENCE:** deterministic probes across xi 0/.001/.002. [L1]

**DECISION:** expected evidence insufficiency/structural instability → UNAVAILABLE; evidence passes approved readiness + unexpected runtime/library invalidity → FAILED; canonical input contradiction → FAILED/data-integrity diagnostic.

**REMAINING INPUT:** Exact exception-to-reason mapping in preflight/tests.

### D13 — Continuous Prediction trigger

**STATUS:** ANSWERED

**EVIDENCE:** checkout shows only `ODDS_CAPTURE` items generate current prediction candidates. [L1]

**DECISION:** relevant football evidence basis drives DC version/recompute; price change alone does not; existing scheduler remains owner.

**REMAINING INPUT:** Exact hash/high-water implementation.

### D14 — Prediction versioning / intermediate evidence

**STATUS:** ANSWERED

**EVIDENCE:** current prospective Experiment and Prediction uniqueness constraints. [L1]

**DECISION:** evidence-basis change creates a new prospective experiment/evidence identity; preserve old Predictions; retain cutoff/evidence/model/readiness/bet-eligibility audit fields semantically.

**REMAINING INPUT:** Exact schema/migration names.

### D15 — Decision integration boundary

**STATUS:** ANSWERED

**EVIDENCE:** current policy path acts directly on ProbabilityResult; established Prediction != Decision product contract. [L1]

**DECISION:** valid produced but below-readiness Prediction persists; Decision is `NO_BET` with readiness reason and excluded from betting/economic cohort.

**REMAINING INPUT:** Exact policy hook.

### D16 — Season transitions

**STATUS:** ANSWERED

**EVIDENCE:** current dataset is multi-season; prior research/product direction closed.

**DECISION:** pure DC has no hard season reset; multi-season evidence remains available with versioned weighting/depth. Dynamic/season-aware challenger remains separate OUT.

**REMAINING INPUT:** None for this ticket.

### D17 — Test contract

**STATUS:** ANSWERED

**EVIDENCE:** local deterministic probes and current model/provider architecture show all required seams can be exercised offline. [L1]

**DECISION:** offline regression suite, real local penaltyblog model, mocked/frozen source IO, importer/reconciliation/readiness/versioning/Decision semantics covered; no live provider calls in tests.

**REMAINING INPUT:** Exact test filenames/fixtures are implementation detail.

### Integrity conclusion

All D1–D17 are **ANSWERED at the semantic/research level required for F008 ticket definition**. Where a universal numeric parameter is not supported, the answer is explicitly an evidence-limited Result B/configurable contract rather than an invented threshold. No material `UNANSWERED` decision is hidden in OPEN questions.

---

## 38. Durable bibliography / references

### Finsport / local evidence

- **Finsport repository**, baseline audited `master@781674afd26106a0a2d7848252e89bbd92f8d2ff`.
  Publisher/source: Finsport / GitHub.
  URL: https://github.com/ljarufe/finsport
  Baseline date: 2026-09-03.
- **Local historical/DC closure evidence** — `research_historical_dc_local_closure.txt`.
  Source: read-only Finsport checkout/DB + bounded football-data downloads through installed penaltyblog 1.12.0.
  Generated: 2026-09-03.
- **API-Football bounded historical probe** — `api_football_historical_probe.txt`.
  Source: real Finsport API-Football account/client, max 4 attempts, no DB writes.
  Generated: 2026-09-03.

### API-Football

- **API-Football — Pricing**.
  Publisher: API-Sports / API-Football.
  URL: https://www.api-football.com/pricing
  Accessed: 2026-09-03.
  Material claim: Free = 100 requests/day; all plans include competitions/endpoints; Free limited in available seasons. [E1]

### football-data.co.uk

- **Historical Football Results and Betting Odds Data**.
  Publisher: Football-Data.co.uk.
  URL: https://www.football-data.co.uk/data.php
  Accessed: 2026-09-03. [E2]
- **European Football Results and Betting Odds — seasonal download archive**.
  Publisher: Football-Data.co.uk.
  URL: https://www.football-data.co.uk/downloadm.php
  Accessed: 2026-09-03. [E3]
- **Football Results and Betting Odds for 16 Worldwide leagues**.
  Publisher: Football-Data.co.uk.
  URL: https://www.football-data.co.uk/all_new_data.php
  Accessed: 2026-09-03. [E6]
- **Argentina Football Results and Betting Odds**.
  Publisher: Football-Data.co.uk.
  URL: https://www.football-data.co.uk/argentina.php
  Accessed: 2026-09-03. [E7]
- **Brazil Football Results and Betting Odds**.
  Publisher: Football-Data.co.uk.
  URL: https://www.football-data.co.uk/brazil.php
  Accessed: 2026-09-03. [E7]
- **USA Football Results and Betting Odds**.
  Publisher: Football-Data.co.uk.
  URL: https://www.football-data.co.uk/usa.php
  Accessed: 2026-09-03. [E8]
- **Latest fixtures for extra leagues**.
  Publisher: Football-Data.co.uk.
  URL: https://www.football-data.co.uk/matches_new_leagues.php
  Accessed: 2026-09-03.

### penaltyblog

- **penaltyblog 1.12.0**.
  Publisher: PyPI / Martin Eastwood.
  URL: https://pypi.org/project/penaltyblog/1.12.0/
  Release uploaded: 2026-08-21.
  Accessed: 2026-09-03. [E4]
- **football-data.co.uk scraper — penaltyblog documentation**.
  Publisher: penaltyblog documentation / Martin Eastwood.
  URL: https://penaltyblog.readthedocs.io/en/master/scrapers/footballdata.html
  Accessed: 2026-09-03. [E5]
- **penaltyblog repository**.
  Publisher: Martin Eastwood / GitHub.
  URL: https://github.com/martineastwood/penaltyblog
  Accessed: 2026-09-03.
  Material claim: maintained Python project, MIT license.

### Peru historical sources

- **Peru — List of Final Tables / historical index**.
  Publisher: Rec.Sport.Soccer Statistics Foundation (RSSSF).
  URL: https://www.rsssf.org/tablesp/peruhist.html
  Accessed: 2026-09-03. [E9]
- **Peru 2025**.
  Author: Carlos Manuel Nieto Tarazona. Publisher: RSSSF.
  URL: https://www.rsssf.org/tablesp/peru2025.html
  Last updated on page: 2026-01-16. Accessed: 2026-09-03.
  Material claim: chronological Primera División results; copy permitted with proper acknowledgement. [E10]
- **Peru 2016**.
  Author: Carlos Manuel Nieto Tarazona. Publisher: RSSSF.
  URL: https://www.rsssf.org/tablesp/peru2016.html
  Last updated on page: 2022-07-29. Accessed: 2026-09-03. [E13]
- **Peru 2018**.
  Publisher: RSSSF.
  URL: https://www.rsssf.org/tablesp/peru2018.html
  Accessed: 2026-09-03. [E13]
- **Peru 2024**.
  Publisher: RSSSF.
  URL: https://www.rsssf.org/tablesp/peru2024.html
  Accessed: 2026-09-03. [E13]
- **Liga 1 Peru 2025 — Results/Archive**.
  Publisher: Soccerway.
  URL: https://www.soccerway.com/peru/liga-1-2025/results/
  Accessed: 2026-09-03. [E11]
- **Primera División Datasets & Excel Downloads — Peru**.
  Publisher: FootyStats.
  URL: https://footystats.org/peru/primera-division/datasets
  Accessed: 2026-09-03. [E12]

### Dixon-Coles / statistical literature

- Dixon, M. J. & Coles, S. G. (1997), **Modelling Association Football Scores and Inefficiencies in the Football Betting Market**.
  Publisher: Journal of the Royal Statistical Society: Series C (Applied Statistics).
  DOI/URL: https://doi.org/10.1111/1467-9876.00065
- Rue, H. & Salvesen, O. (2000), **Prediction and retrospective analysis of soccer matches in a league**.
  Publisher: Journal of the Royal Statistical Society: Series D / The Statistician.
  DOI/URL: https://doi.org/10.1111/1467-9884.00243
- Ridall et al. (2025), dynamic football modelling work cited by prior Finsport research.
  Publisher: Journal of the Royal Statistical Society Series C.
  DOI/URL: https://doi.org/10.1093/jrsssc/qlae075

### Evidence-key legend

- `[E1]` API-Football Pricing.
- `[E2]` football-data.co.uk main historical data page.
- `[E3]` football-data.co.uk European seasonal archive.
- `[E4]` penaltyblog 1.12.0 PyPI release.
- `[E5]` penaltyblog FootballData scraper docs.
- `[E6]` football-data.co.uk extra-league data page.
- `[E7]` football-data Argentina/Brazil dedicated pages.
- `[E8]` football-data USA dedicated page.
- `[E9]` RSSSF Peru history index.
- `[E10]` RSSSF Peru 2025.
- `[E11]` Soccerway Peru Liga 1 2025 results/archive.
- `[E12]` FootyStats Peru dataset catalogue.
- `[E13]` RSSSF Peru annual pages 2016/2018/2024 spot-checks.
- `[L1]` `research_historical_dc_local_closure.txt`.
- `[L2]` `api_football_historical_probe.txt`.

---

# Final research disposition

**Status:** REFERENCE ONLY
**Research completion:** COMPLETE
**D1–D17 integrity gate:** PASS — all original decisions are ANSWERED at the research/semantic level; no blocking unanswered decision is hidden behind implementation detail.
**Combined-ticket disposition:** COMBINED_TICKET_RECOMMENDED
**Next lifecycle stage:** F008 audit/readiness/ticket definition only.
**Implementation lifecycle:** F009 after an approved package exists.
**Ticket ID:** NOT ASSIGNED.
