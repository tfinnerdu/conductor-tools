"""DOB shift detection engine (PD0002124).

Finds PERSON records whose Date of Birth was silently shifted -1 day by the
Colleague Self-Service Instant Enrollment timezone defect, without touching
records that are already correct.

Core idea
---------
The bug only ever subtracts a day, and only for registrants east of the
server (Doane = Central). So the corrupted value is always EARLIER than the
true value by exactly one day. We look for two records that plausibly
describe the same human whose DOBs are exactly one calendar day apart, then
use the origin marker (Instant Enrollment vs an authoritative source like an
application load) to decide which side is corrupted.

Confidence tiers
----------------
HIGH     - strong identity match + exactly one-day gap + the EARLIER-dated
           record is Instant-Enroll-created and the LATER-dated record is
           authoritative (non-IE). Signature is unambiguous. We propose:
           set the IE record's DOB to the later date (corrupted + 1 day).
MEDIUM   - strong identity match + one-day gap, but origin is unknown or both
           records share the same origin. Later date is a tentative "probably
           true" hint. No auto-correction.
REVIEW   - identity match but the IE record is the LATER one (gap points the
           wrong way for this bug). Likely a plain data-entry typo or two
           different people. Flag; do not propose +1.

Nothing here writes to Colleague. This module only classifies candidates; the
routes layer (app/routes/dob_repair.py) is responsible for persisting human
decisions and exporting an approved-corrections CSV.

Direction assumption: this engine encodes the "-1 day / backward" signature
confirmed against real Instant Enrollment traffic. If that signature is ever
shown to be different, flip SHIFT_DIRECTION below.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, Union, IO


# -1 means the bug subtracts a day (corrupted value is earlier than true value).
SHIFT_DIRECTION = -1

# Origin values that mean "created by Instant Enrollment". Compared uppercased.
IE_ORIGIN_VALUES = {"INSTANT_ENROLL", "INSTANT ENROLLMENT", "IE", "SS_IE"}

# US states predominantly in the Eastern time zone (east of a Central server).
# The -1 shift only hits registrants east of the server, so an unpaired IE
# record with an Eastern-state address is the elevated-risk population. This
# is a PRIORITIZATION proxy only: the real trigger is the browser timezone at
# registration, which the mailing address does not prove. Straddle states
# (FL, IN, KY, MI, TN) are included because their population center is Eastern.
EASTERN_TZ_STATES = {
    "CT", "DE", "DC", "FL", "GA", "IN", "KY", "ME", "MD", "MA", "MI",
    "NH", "NJ", "NY", "NC", "OH", "PA", "RI", "SC", "TN", "VT", "VA", "WV",
}


def is_eastern_state(state: str) -> bool:
    return _clean(state) in EASTERN_TZ_STATES


# Identity scoring weights. A pair is treated as the same person at or above
# IDENTITY_THRESHOLD. Tunable via config without touching logic.
WEIGHTS = {
    "last_exact": 2,
    "first_exact": 2,
    "first_initial": 1,   # only when full first names do not match exactly
    "middle_exact": 1,
    "zip_exact": 2,
    "street_exact": 2,
    "city_state_exact": 1,
    "email_exact": 3,
    "phone_exact": 3,
}
IDENTITY_THRESHOLD = 6

# Date formats accepted on input. First match wins.
DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%Y/%m/%d",
    "%m/%d/%y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
]

# Default column mapping. Override any of these via config so the detector
# matches whatever export you have (ODS, Informer, Ethos-to-CSV, Colleague
# export).
DEFAULT_COLUMNS = {
    "person_id": "person_id",
    "last_name": "last_name",
    "first_name": "first_name",
    "middle_name": "middle_name",
    "birth_date": "birth_date",
    "addr_line1": "addr_line1",
    "city": "city",
    "state": "state",
    "zip": "zip",
    "email": "email",
    "phone": "phone",
    "origin": "origin",
    "created_date": "created_date",
}


# --------------------------------------------------------------------------- #
# Normalization helpers
# --------------------------------------------------------------------------- #

def _clean(value: Optional[str]) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def _digits(value: Optional[str]) -> str:
    if value is None:
        return ""
    return re.sub(r"\D", "", str(value))


def _zip5(value: Optional[str]) -> str:
    d = _digits(value)
    return d[:5]


def parse_date(value: Optional[str]) -> Optional[date]:
    """Parse a DOB string into a date, or None if unparseable/blank."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# Record model
# --------------------------------------------------------------------------- #

@dataclass
class Record:
    person_id: str
    last_name: str
    first_name: str
    middle_name: str
    birth_date: Optional[date]
    addr_line1: str
    city: str
    state: str
    zip: str
    email: str
    phone: str
    origin: str
    created_date: str
    raw_birth_date: str = ""

    @property
    def is_ie(self) -> bool:
        return _clean(self.origin) in IE_ORIGIN_VALUES

    def block_key(self) -> str:
        """Blocking key keeps comparison O(n) instead of O(n^2). Records only
        get compared inside the same block. Key = normalized last name +
        first initial + zip5 (falls back to city when zip is missing)."""
        last = _clean(self.last_name)
        first_init = _clean(self.first_name)[:1]
        geo = _zip5(self.zip) or _clean(self.city)
        return f"{last}|{first_init}|{geo}"


def record_from_row(row: dict, columns: dict) -> Record:
    def g(field_name: str) -> str:
        col = columns.get(field_name, field_name)
        return row.get(col, "") or ""

    raw_dob = g("birth_date")
    return Record(
        person_id=g("person_id").strip(),
        last_name=g("last_name"),
        first_name=g("first_name"),
        middle_name=g("middle_name"),
        birth_date=parse_date(raw_dob),
        addr_line1=g("addr_line1"),
        city=g("city"),
        state=g("state"),
        zip=g("zip"),
        email=g("email"),
        phone=g("phone"),
        origin=g("origin"),
        created_date=g("created_date"),
        raw_birth_date=raw_dob,
    )


# --------------------------------------------------------------------------- #
# Identity scoring
# --------------------------------------------------------------------------- #

def identity_score(a: Record, b: Record) -> int:
    """Points for how strongly two records look like the same person."""
    score = 0
    la, lb = _clean(a.last_name), _clean(b.last_name)
    fa, fb = _clean(a.first_name), _clean(b.first_name)

    if la and la == lb:
        score += WEIGHTS["last_exact"]
    if fa and fa == fb:
        score += WEIGHTS["first_exact"]
    elif fa and fb and fa[:1] == fb[:1]:
        score += WEIGHTS["first_initial"]

    ma, mb = _clean(a.middle_name), _clean(b.middle_name)
    if ma and ma == mb:
        score += WEIGHTS["middle_exact"]

    za, zb = _zip5(a.zip), _zip5(b.zip)
    if za and za == zb:
        score += WEIGHTS["zip_exact"]

    sa, sb = _clean(a.addr_line1), _clean(b.addr_line1)
    if sa and sa == sb:
        score += WEIGHTS["street_exact"]

    ca, cb = _clean(a.city), _clean(b.city)
    sta, stb = _clean(a.state), _clean(b.state)
    if ca and ca == cb and sta and sta == stb:
        score += WEIGHTS["city_state_exact"]

    ea, eb = _clean(a.email), _clean(b.email)
    if ea and ea == eb:
        score += WEIGHTS["email_exact"]

    pa, pb = _digits(a.phone), _digits(b.phone)
    if pa and pa == pb and len(pa) >= 10:
        score += WEIGHTS["phone_exact"]

    return score


# --------------------------------------------------------------------------- #
# Candidate model + classification
# --------------------------------------------------------------------------- #

@dataclass
class Candidate:
    candidate_id: str
    bucket: str                       # HIGH | MEDIUM | REVIEW
    identity_score: int
    gap_days: int                     # signed: (later - earlier), always 1 here
    record_a: Record                  # earlier DOB
    record_b: Record                  # later DOB
    suggested_true_dob: Optional[date]
    proposed_person_id: Optional[str]  # only set for HIGH (safe auto-proposal)
    proposed_from: Optional[date]
    proposed_to: Optional[date]
    rationale: str = ""

    def as_row(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "bucket": self.bucket,
            "identity_score": self.identity_score,
            "gap_days": self.gap_days,
            "earlier_person_id": self.record_a.person_id,
            "earlier_dob": _fmt(self.record_a.birth_date),
            "earlier_origin": self.record_a.origin,
            "later_person_id": self.record_b.person_id,
            "later_dob": _fmt(self.record_b.birth_date),
            "later_origin": self.record_b.origin,
            "name": f"{self.record_b.first_name} {self.record_b.last_name}".strip(),
            "suggested_true_dob": _fmt(self.suggested_true_dob),
            "proposed_person_id": self.proposed_person_id or "",
            "proposed_from": _fmt(self.proposed_from),
            "proposed_to": _fmt(self.proposed_to),
            "rationale": self.rationale,
        }


def _fmt(d: Optional[date]) -> str:
    return d.isoformat() if d else ""


def _classify_pair(a: Record, b: Record, score: int) -> Optional[Candidate]:
    """a and b are same-block; identity strength is `score`. Returns a
    Candidate if the DOB gap is exactly one day, else None."""
    if a.birth_date is None or b.birth_date is None:
        return None

    delta = (b.birth_date - a.birth_date).days
    if abs(delta) != 1:
        return None

    # Order so record_a is the earlier DOB, record_b the later DOB.
    earlier, later = (a, b) if a.birth_date < b.birth_date else (b, a)
    cid = _candidate_id(earlier.person_id, later.person_id)

    ie_earlier = earlier.is_ie
    ie_later = later.is_ie

    # HIGH: backward-shift signature. Earlier record is IE (corrupted), later
    # record is authoritative (not IE). True DOB = later date.
    if SHIFT_DIRECTION == -1 and ie_earlier and not ie_later:
        return Candidate(
            candidate_id=cid,
            bucket="HIGH",
            identity_score=score,
            gap_days=1,
            record_a=earlier,
            record_b=later,
            suggested_true_dob=later.birth_date,
            proposed_person_id=earlier.person_id,
            proposed_from=earlier.birth_date,
            proposed_to=later.birth_date,
            rationale=(
                "Instant-Enroll record is exactly one day BEFORE an "
                "authoritative record for the same person. Matches the "
                "-1 day timezone signature. Proposed: set IE DOB to the "
                "authoritative (later) date."
            ),
        )

    # REVIEW: IE record is the LATER one. Wrong direction for this bug, so it
    # is more likely a typo or two different people. No +1 proposal.
    if ie_later and not ie_earlier:
        return Candidate(
            candidate_id=cid,
            bucket="REVIEW",
            identity_score=score,
            gap_days=1,
            record_a=earlier,
            record_b=later,
            suggested_true_dob=None,
            proposed_person_id=None,
            proposed_from=None,
            proposed_to=None,
            rationale=(
                "One-day gap but the Instant-Enroll record is the LATER "
                "date, which does not fit the -1 day shift. Likely a "
                "data-entry typo or two distinct people. Human decision "
                "required."
            ),
        )

    # MEDIUM: origin unknown or both same origin. Surface both; tentatively
    # the later date is more likely true (bug only subtracts) but do not
    # auto-apply.
    return Candidate(
        candidate_id=cid,
        bucket="MEDIUM",
        identity_score=score,
        gap_days=1,
        record_a=earlier,
        record_b=later,
        suggested_true_dob=later.birth_date,
        proposed_person_id=None,
        proposed_from=None,
        proposed_to=None,
        rationale=(
            "Same person, DOBs exactly one day apart, but origin does not "
            "cleanly separate corrupted from authoritative. Later date is "
            "a tentative guess for the true DOB. Confirm before any change."
        ),
    )


def _candidate_id(id1: str, id2: str) -> str:
    """Stable id for a pair regardless of argument order."""
    a, b = sorted([id1, id2])
    return f"{a}__{b}"


# --------------------------------------------------------------------------- #
# Top-level analysis
# --------------------------------------------------------------------------- #

@dataclass
class AnalysisResult:
    candidates: list = field(default_factory=list)      # list[Candidate]
    elevated_risk: list = field(default_factory=list)   # list[Record] unpaired IE
    unparseable_dob: list = field(default_factory=list)  # list[Record]
    summary: dict = field(default_factory=dict)


def analyze(records: list, identity_threshold: int = IDENTITY_THRESHOLD) -> AnalysisResult:
    result = AnalysisResult()

    # Group into blocks so we only compare plausibly related records.
    blocks: dict = {}
    for r in records:
        if r.raw_birth_date and r.birth_date is None:
            result.unparseable_dob.append(r)
        blocks.setdefault(r.block_key(), []).append(r)

    paired_person_ids: set = set()

    for _key, group in blocks.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if a.person_id == b.person_id:
                    continue
                score = identity_score(a, b)
                if score < identity_threshold:
                    continue
                cand = _classify_pair(a, b, score)
                if cand is not None:
                    result.candidates.append(cand)
                    paired_person_ids.add(a.person_id)
                    paired_person_ids.add(b.person_id)

    # Elevated-risk lone records: Instant-Enroll-created, has a DOB, never
    # paired, AND the address is in an Eastern-time state. Cannot be
    # confirmed from data alone, but this is the population most likely
    # silently shifted. Central/Western/unknown-state unpaired IE records are
    # low prior and deliberately omitted to keep the worklist signal-heavy
    # rather than the whole IE cohort.
    for r in records:
        if (
            r.is_ie
            and r.birth_date is not None
            and r.person_id not in paired_person_ids
            and is_eastern_state(r.state)
        ):
            result.elevated_risk.append(r)

    # De-duplicate candidates (a pair can surface once per block key at most,
    # but guard anyway) and sort worst-first for review.
    seen: set = set()
    unique = []
    for c in result.candidates:
        if c.candidate_id in seen:
            continue
        seen.add(c.candidate_id)
        unique.append(c)
    order = {"HIGH": 0, "MEDIUM": 1, "REVIEW": 2}
    unique.sort(key=lambda c: (order.get(c.bucket, 9), -c.identity_score))
    result.candidates = unique

    result.summary = {
        "total_records": len(records),
        "candidates_total": len(unique),
        "high": sum(1 for c in unique if c.bucket == "HIGH"),
        "medium": sum(1 for c in unique if c.bucket == "MEDIUM"),
        "review": sum(1 for c in unique if c.bucket == "REVIEW"),
        "elevated_risk": len(result.elevated_risk),
        "unparseable_dob": len(result.unparseable_dob),
    }
    return result


# --------------------------------------------------------------------------- #
# CSV loading
# --------------------------------------------------------------------------- #

def load_records(source: Union[str, IO[str]], columns: Optional[dict] = None) -> list:
    """Load Records from a PERSON export CSV.

    `source` is either a path (str) or an already-open text-mode file-like
    object (e.g. an uploaded file decoded to text) — callers in the routes
    layer hand this either a server-side path or an in-memory upload.
    """
    cols = dict(DEFAULT_COLUMNS)
    if columns:
        cols.update(columns)

    if isinstance(source, str):
        with open(source, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            return [record_from_row(row, cols) for row in reader]

    reader = csv.DictReader(source)
    return [record_from_row(row, cols) for row in reader]
