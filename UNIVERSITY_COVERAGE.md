# University Coverage — Phase 11A (Tier 1)

**Measured: 84 events hosted by 66 distinct universities/colleges** now in the searchable catalog —
all surfaced this phase, via Unstop.

## How Tier 1 was actually reached

The phase prioritised the university ecosystem (IIT/IIIT/NIT/BITS/Manipal/VIT/SRM/DTU/… + on-campus
ACM/IEEE/GDSC/coding/AI clubs). The **measured reality**: Indian university and student-club websites
**publish no machine-readable event feeds** (no ICS/RSS/JSON-LD event data) that a byte-level,
no-JavaScript fetcher can extract. Crawling campus sites directly yielded **0** structured events.

Instead, Tier 1 was reached where those organizers *actually publish* — Unstop, the platform students
and college clubs use to run hackathons and fests. This surfaced **84 real, upcoming, university-hosted
events** with the hosting institution as the organizer.

## Institutions represented (66 total)

**IITs / NITs / IIITs / IIMs:** IIT Kharagpur · SVNIT Surat · NIT Delhi · IIM Bangalore · IIM Indore ·
(plus events tagged to national institutes across runs).

**Major private/deemed universities:** VIT Chennai · Manipal University Jaipur · Sathyabama IST ·
Woxsen University · Vivekananda Institute of Professional Studies (VIPS), Delhi · University of
Engineering & Management, Kolkata · Guru Jambheshwar University of Science & Technology.

**Engineering colleges (sample):** Chennai Institute of Technology (8 events — top host) · Coimbatore
Institute of Technology · JIS College of Engineering · Inderprastha Engineering College · Sri Sairam
Engineering College · Government College of Engineering · Samrat Ashok Technological Institute ·
University School of Automation & Robotics (GGSIPU) · and ~50 more.

## On-campus clubs (ACM/IEEE/GDSC/coding/AI)

Where a hosting body is a student chapter, it appears via the event's festival/organiser name (e.g.
**IEEE HackSynapse 2026** at Madhav Institute of Technology; **Fugacity** at IIT Kharagpur). Standalone
club calendars (ACM/IEEE/GDSC chapter pages) publish no machine-readable feed and contributed **0**
directly — the same measured limitation as campus sites.

## Coverage gap (measured, honest)

- Named target universities **not** yet represented (BITS, DTU, NSUT, RVCE, PES, LNMIIT, DAIICT, IIEST,
  JU, COEP, ICT, Nirma, Thapar): they have **no upcoming event in any machine-readable source** at
  crawl time — not a discovery failure, an availability fact. When these institutions post a hackathon
  on Unstop/Devfolio, the existing pipeline will index it on the next cycle with **zero code change**.
- Direct campus-site / club-calendar ingestion remains impossible for this architecture (no JS, no
  auth); it would require a rendering tier that is explicitly out of scope.

**Bottom line:** the university ecosystem is now represented (84 events / 66 institutions) to the full
extent it is machine-readable today, and grows automatically as more campus events are posted to the
platforms the pipeline already reads.
