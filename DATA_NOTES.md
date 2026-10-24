# DATA_NOTES

Summary of PLAN.md Section 3 (data sources), facts checked 2026-10-23, and reference-table downloads confirmed 2026-10-24. Anything not in those checked/confirmed sets is marked **UNVERIFIED**.

---

## Reference tables downloaded (2026-10-24, pre-event, per Decision 1)

These are the small reference tables Decision 1 explicitly allows into `data/manual/` before the event — not bulk case data (no `.parquet`/`.vital` whole-case files were fetched).

| File | Source | Saved as | Size |
|---|---|---|---|
| Clinical case table | `https://api.vitaldb.net/cases` (gzip-encoded CSV, decompressed on save) | `data/manual/cases.csv` | 2,199,564 bytes; 6,389 lines (header + 6,388 cases — matches the documented case count) |
| Track name dictionary | `https://physionet.org/files/vitaldb/1.0.0/track_names.csv` | `data/manual/track_names.csv` | 10,440 bytes; 197 lines |
| Clinical column dictionary | `https://physionet.org/files/vitaldb/1.0.0/clinical_parameters.csv` | `data/manual/clinical_parameters.csv` | 3,258 bytes; 82 lines |

**Confirmed against these downloads (no longer "expected" — now verified):**
- Exact track names for all four tracks PLAN.md expected: `Solar8000/HR` ("Heart rate", N, /min), `Solar8000/ART_SBP`, `Solar8000/ART_DBP`, `Solar8000/ART_MBP` (all "N" = numeric, mmHg) all present in `track_names.csv` exactly as named.
- All clinical fields PLAN.md expected are present in `cases.csv`'s header exactly as named: `caseid`, `age`, `sex`, `weight`, `asa`, `emop`, `opstart`, `opend`, `anestart`, `aneend`, `aline1`, `aline2`, plus the previously-confirmed `intraop_ebl`, `intraop_rbc`, `intraop_ffp`, `intraop_crystalloid`, `intraop_colloid`, `intraop_uo`.
- `cases.csv` additionally has: `subjectid`, `casestart`, `caseend`, `adm`, `dis`, `icu_days`, `death_inhosp`, `height`, `bmi`, `department`, `optype`, `dx`, `opname`, `approach`, `position`, `ane_type`, a block of `preop_*` labs, `cormack`, `airway`, `tubesize`, `dltubesize`, `lmasize`, `iv1`, `iv2`, `cline1`, `cline2`, and several more `intraop_*` drug/fluid fields (`intraop_ppf`, `intraop_mdz`, `intraop_ftn`, `intraop_rocu`, `intraop_vecu`, `intraop_eph`, `intraop_phe`, `intraop_epi`, `intraop_ca`).
- `clinical_parameters.csv` is the column dictionary for `cases.csv` (Parameter, Data Source, Description, Unit) — e.g. confirms `casestart`/`caseend` are set to 0 for anonymization and other fields are offsets from `casestart` in seconds.
- `track_names.csv` columns are `Parameter, Description, Type/Hz, Unit` — `Type` is `W` (waveform, with its Hz) or `N` (numeric). This is the table Phase 1 should read programmatically instead of guessing track names.

---

## Primary dataset: VitalDB (South Korea)

- 6,388 non-cardiac surgical cases, Seoul National University Hospital, 2016–2017.
- Waveforms at 500 Hz and numerics at 1–7 s intervals.
- Listed on PhysioNet as open access.
- Pages: https://vitaldb.net/dataset and https://physionet.org/content/vitaldb/1.0.0/

### Checked on 2026-10-23
- VitalDB is **public**, **CC BY 4.0**, **no login required**.
- `https://api.vitaldb.net/cases` returns the clinical table as CSV.
- `https://api.vitaldb.net/{caseid}.parquet` (IDs 1 to 6388) and `.vital` return whole cases, readable with `pip install vitaldb` 1.7+.
- PhysioNet hosts `clinical_data.csv`, `clinical_parameters.csv` (the column dictionary), and `track_names.csv` under `https://physionet.org/files/vitaldb/1.0.0/`.
- The full dataset is **95.4 GB** — it must never be downloaded in full.
- Track names look like `Solar8000/HR` (Device/Channel format), but the **exact names must be read from `track_names.csv`**, not guessed.

### UNVERIFIED (from PLAN.md Section 3, not independently checked on 2026-10-23 — several items below were since confirmed 2026-10-24, see the downloads section above)
- ~~Exact clinical field list~~ — **confirmed 2026-10-24**, see above.
- ~~Exact track names~~ — **confirmed 2026-10-24** for `Solar8000/HR`, `Solar8000/ART_SBP`, `Solar8000/ART_DBP`, `Solar8000/ART_MBP`. `SNUADC/ART` (the 500 Hz arterial waveform) is also present in `track_names.csv` as `W/500` but is not needed for v2 (stretch only, per PLAN.md Section 3.1).
- Whole-case file size average (~15 MB) — PLAN.md's own estimate, not measured (needs the Phase 1 5-case test; whole-case files were not downloaded here — only the small reference tables).
- `/trks` and other per-track endpoints — not verified; plan says use `track_names.csv` or the `vitaldb` library instead.
- HackPSU Fall 2026 rules and judging criteria.
- VitalDB license wording beyond "CC BY 4.0" as stated on the dataset page.
- ATLS numeric ranges used by the simulator (standard teaching; double-check before quoting).
- Any integration path to real ER or ambulance equipment.

---

## Other datasets considered (not usable by Saturday)

| Dataset | Country | Access | Usable by Saturday? |
|---|---|---|---|
| VitalDB | South Korea | Open | **Yes (primary)** |
| INSPIRE (130k surgeries; vitals coarse, up to 5 min) | South Korea | Credentialed via PhysioNet (verify) | No |
| HiRID (~34k ICU admissions) | Switzerland | PhysioNet credentialing + DUA | No |
| SICdb | Austria | PhysioNet credentialing + DUA | No |
| AmsterdamUMCdb | Netherlands | CITI course + license form countersigned by an intensivist | No |
| MOVER (perioperative, 83k cases) | USA | Access terms not verified | Check, optional |
| Porcine exsanguination (6 pigs) | (IEEE DataPort) | Open, free login | Optional figure only |
| LBNP human volunteer studies | Norway, USA | Papers only; no open download found | No |

Conclusion: only VitalDB is both open and large enough. The credentialed sets are named as candidates for future external validation, not for this event.

### Optional secondary
IEEE DataPort porcine exsanguination: 6 animals, blood loss at 7/14/21/28%. One illustrative figure only if used; verify file format first.

---

## Required citations

- Lee H, Jung C. VitalDB, a high-fidelity multi-parameter vital signs database for critical care research. PhysioNet v1.0.0. https://doi.org/10.13026/czw8-9p62
- Lee HC, Park Y, Yoon SB, Yang SM, Park D, Jung CW. VitalDB, a high-fidelity multi-parameter vital signs database in surgical patients. Scientific Data 2022. https://doi.org/10.1038/s41597-022-01411-5
