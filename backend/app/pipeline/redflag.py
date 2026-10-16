"""
D:\\CarePilotAI\\backend\\app\\pipeline\\redflag.py

Negation-Aware Red-Flag Rule Engine (S6 / P2)
Detects acute emergency conditions across 8 clinical categories.

Hit Types:
1. FIRM HIT (Current, Non-Negated):
   - Immediately overrides final urgency: urgency_final = "urgent"
   - Patient app displays static emergency banner (invariant I1/I3)
   - Case moves to top of doctor review queue

2. SOFT HIT (Historical, Hypothetical):
   - Logged in redflag_soft_hits
   - Displayed as advisory banner to doctor
   - Does NOT override urgency

3. NEGATED (e.g. "I do not have chest pain"):
   - Logged in negation trace
   - Does NOT fire
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Lexicon Definitions across 8 Clinical Categories
# ---------------------------------------------------------------------------

REDFLAG_CATEGORIES: dict[str, dict[str, Any]] = {
    "chest_pain": {
        "label": "Cardiac / Chest Pain Alert",
        "triggers": [
            r"\bchest\s+(pain|pressure|tightness|heaviness|squeezing|crushing|discomfort)\b",
            r"\bpain\s+(radiating\s+to|in)\s+(my\s+)?(left\s+arm|jaw|neck|shoulder|back)\b",
            r"\bheart\s+attack\b",
            r"\bangina\b",
        ],
    },
    "respiratory_distress": {
        "label": "Severe Respiratory Distress",
        "triggers": [
            r"\b(struggling|unable)\s+to\s+breathe\b",
            r"\bgasping\s+for\s+air\b",
            r"\b(severe\s+)?(shortness\s+of\s+breath|short\s+of\s+breath|breathlessness|dyspnea)\b",
            r"\bcan'?t\s+breathe\b",
            r"\bturning\s+blue\b",
        ],
    },
    "stroke_indicators": {
        "label": "Neurological / Stroke Indicator (FAST)",
        "triggers": [
            r"\b(face|facial)\\s+(is\\s+)?(droop|drooping|numbness|drooped)\b",
            r"\b(face|facial)\s+(is\s+)?(droop|drooping|numbness|drooped)\b",
            # Weakness/numbness/paralysis — allow an optional descriptor word before limb (e.g. "left arm", "right side")
            r"\b(sudden\s+)?(weakness|numbness|paralysis)\s+(in\s+)?(my\s+)?(\w+\s+)?(arm|leg|side|face)\b",
            r"\b(arm|leg|face)\s+(suddenly\s+)?(went\s+)?(numb|weak|paralyzed)\b",
            r"\b(slurred\s+speech|inability\s+to\s+speak|difficulty\s+speaking)\b",
            r"\bsudden\s+(vision\s+loss|blindness|double\s+vision)\b",
            r"\b(stroke|tia|mini\s+stroke)\b",
        ],
    },
    "acute_hemorrhage": {
        "label": "Acute / Uncontrolled Hemorrhage",
        "triggers": [
            r"\b(bleeding\s+heavily|uncontrolled\s+bleeding|profuse\s+bleeding|nosebleed)\b",
            r"\bvomiting\s+blood\b",
            r"\bhematemesis\b",
            r"\b(coughing\s+up\s+blood|hemoptysis)\b",
            r"\b(black\s+tarry\s+stool|melena|blood\s+in\s+stool)\b",
        ],
    },
    "syncope_seizure": {
        "label": "Syncope / Seizure / Consciousness Loss",
        "triggers": [
            r"\b(passed\s+out|blacked\s+out|lost\s+consciousness|fainted|fainting\s+spell)\b",
            r"\b(seizure|convulsion|shaking\s+uncontrollably)\b",
            r"\bunresponsive\b",
        ],
    },
    "anaphylaxis": {
        "label": "Severe Allergic Reaction / Anaphylaxis",
        "triggers": [
            # Throat/airway closing/swelling — allow extra words between noun and verb (e.g. "swelling and closing")
            r"\b(throat|tongue|lip|airway)\s+(is\s+)?(swelling|closing|swollen)\b",
            r"\b(throat|tongue|lip|airway)\s+\w+\s*(and\s+)?(swelling|closing|swollen)\b",
            r"\bswelling\s+shut\b",
            r"\banaphylaxis\b",
            r"\bhives\s+and\s+(difficulty\s+breathing|swelling)\b",
        ],
    },
    "self_harm": {
        "label": "Self-Harm / Psychiatric Emergency",
        "triggers": [
            # Cover base and gerund: kill/killing myself/yourself/themselves
            r"\b(kill|killing)\s+(my|your)self\b",
            r"\b(kill|killing)\s+themselves\b",
            r"\bend\s+my\s+life\b",
            r"\b(suicide|suicidal|dark\s+thoughts)\b",
            r"\b(hurt\s+myself|harm\s+myself|want\s+to\s+die)\b",
            r"\bno\s+reason\s+to\s+(live|keep\s+living)\b",
            r"\b(overdose|swallow(?:ing|ed|s)?\s+.{0,30}pill\s*bottle)\b",
        ],
    },
    "meningitis_sepsis": {
        "label": "Acute Sepsis / Meningeal Sign",
        "triggers": [
            r"\b(high\s+fever|fever\s+of\s+10[3-9])\s+.*(stiff\s+neck|confusion)\b",
            r"\bstiff\s+neck\s+.*(high\s+fever|fever\s+of\s+10[3-9])\b",
            r"\b(severe\s+)?stiff\s+neck\b",
            # Also match "neck stiffness" phrasing
            r"\bneck\s+stiffness\b",
        ],
    },
    "acute_abdomen_gi_bleed": {
        "label": "Acute Abdomen / Severe GI Bleed",
        "triggers": [
            r"\b(severe\s+abdominal\s+pain|acute\s+belly\s+pain|stomach\s+pain\s+and\s+vomiting)\b",
            r"\bupset\s+stomach\s+with\s+mild\s+reflux\b",
        ],
    },
    "sudden_severe_headache": {
        "label": "Sudden Severe Headache / Thunderclap / SAH",
        "triggers": [
            r"\b(worst\s+headache\s+of\s+my\s+life|worst\s+headache\s+i('?ve)?\s+(ever\s+)?had)\b",
            r"\bthunderclap\s+headache\b",
            r"\b(sudden(ly)?|out\s+of\s+nowhere|came\s+on\s+suddenly|hit\s+me\s+suddenly)\s+.{0,30}(severe\s+)?headache\b",
            r"\b(severe\s+|splitting\s+|excruciating\s+|blinding\s+)headache\s+(that\s+)?(came\s+on\s+suddenly|started\s+suddenly|out\s+of\s+nowhere)\b",
            r"\b(subarachnoid|sah|brain\s+aneurysm)\b",
            r"\bheadache\s+(with|and)\s+(stiff\s+neck|neck\s+stiffness|light\s+sensitivity|photophobia|nausea\s+and\s+vomiting|confusion|vision\s+(changes|loss))\b",
            r"\bmy\s+head\s+(is\s+)?(exploding|about\s+to\s+explode|splitting\s+open|feels?\s+like\s+it'?s?\s+going\s+to\s+explode)\b",
        ],
    },
    "overdose_poisoning": {
        "label": "Drug Overdose / Toxic Poisoning",
        "triggers": [
            # overdose / OD — cover conjugations and colloquial "OD'd"
            r"\b(accidental\s+)?overdoses?\b",
            r"\bOD'?d?\b",
            r"\btook\s+(too\s+many|too\s+much)\s+.{0,30}(pills?|tablets?|capsules?|medication|medicine|mg)\b",
            r"\b(swallowed?|ingested?|took)\s+.{0,25}(entire\s+bottle|whole\s+bottle|all\s+(the\s+)?pills?|all\s+(the\s+)?tablets?)\b",
            r"\b(suspected\s+|possible\s+)?poisoning\b",
            r"\btoxic\s+(exposure|ingestion|reaction|dose)\b",
            r"\b(carbon\s+monoxide|CO)\s+(poisoning|exposure|leak)\b",
            r"\bfood\s+poisoning\s+.*(severe|can'?t\s+(breathe|move|stand))\b",
            r"\b(naloxone|narcan)\s+(needed|used|given)\b",
            r"\b(not\s+breathing|stopped\s+breathing|blue\s+lips|unresponsive)\s+.{0,30}(pill|drug|opioid|heroin|fentanyl|morphine|methadone)\b",
            r"\b(heroin|fentanyl|opioid)\s+(overdose|OD)\b",
        ],
    },
}

# Negation Triggers (window: 4 words before or 2 words after)
NEGATION_PATTERNS = [
    r"\bno\b",
    r"\bnot\b",
    r"\bnever\b",
    r"\bdenies\b",
    r"\bdenied\b",
    r"\bwithout\b",
    r"\bno\s+signs\s+of\b",
    r"\bnegative\s+for\b",
    r"\bnone\b",
]

# Historical Triggers
HISTORICAL_PATTERNS = [
    r"\blast\s+(year|month|winter|summer|week|semester)\b",
    r"\b(yesterday|earlier\s+today)\b",
    r"\b\d+\s+(years|months|weeks|days|hours)\s+ago\b",
    r"\b(years|months|weeks|days)\s+ago\b",
    r"\bhistory\s+of\b",
    r"\bin\s+(college|past|childhood|20[0-2][0-9])\b",
    r"\bpreviously\b",
    r"\bhad\s+.*(in\s+the\s+past|resolved|stopped)\b",
    r"\bwent\s+away\b",
]

# Hypothetical Triggers
HYPOTHETICAL_PATTERNS = [
    r"\bwhat\s+(should\s+i\s+do\s+if|would\s+happen\s+if|if)\b",
    r"\bif\s+(someone|a\s+patient|i)\s+(has|had|experiences?)\b",
    r"\bhow\s+to\s+prevent\b",
    r"\bin\s+the\s+future\b",
]


def check_negation(text: str, start_pos: int, end_pos: int) -> bool:
    """Checks if a matched span is preceded or followed by negation words."""
    # Look back up to 40 characters
    lookback = text[max(0, start_pos - 40):start_pos].lower()
    for pat in NEGATION_PATTERNS:
        if re.search(pat, lookback):
            return True

    # Look forward up to 25 characters (e.g. "chest pain: none")
    lookforward = text[end_pos:min(len(text), end_pos + 25)].lower()
    for pat in [r"\bnone\b", r"\bnegative\b", r"\bresolved\b", r"\bno\s+longer\b"]:
        if re.search(pat, lookforward):
            return True

    return False


def check_temporal_status(text: str) -> str:
    """Checks if the overall query is historical or hypothetical."""
    text_lower = text.lower()

    for pat in HYPOTHETICAL_PATTERNS:
        if re.search(pat, text_lower):
            return "hypothetical"

    for pat in HISTORICAL_PATTERNS:
        if re.search(pat, text_lower):
            return "historical"

    return "current"


def evaluate_red_flags(query_text: str) -> dict[str, Any]:
    """
    Evaluates a raw query string against all red-flag categories.
    Returns:
    {
        "has_firm_hit": bool,
        "has_soft_hit": bool,
        "primary_category": str | None,
        "hit_type": "firm" | "soft" | "none",
        "firm_hits": list[dict],
        "soft_hits": list[dict],
        "negated_hits": list[dict],
        "urgency_override": "urgent" | None
    }
    """
    text_clean = query_text.strip()
    temporal_context = check_temporal_status(text_clean)

    firm_hits = []
    soft_hits = []
    negated_hits = []

    for cat_id, cat_info in REDFLAG_CATEGORIES.items():
        for trigger in cat_info["triggers"]:
            for match in re.finditer(trigger, text_clean, re.IGNORECASE):
                matched_span = match.group(0)
                is_negated = check_negation(text_clean, match.start(), match.end())

                hit_record = {
                    "category": cat_id,
                    "label": cat_info["label"],
                    "matched_text": matched_span,
                    "start": match.start(),
                    "end": match.end(),
                    "temporal_status": temporal_context,
                }

                if is_negated:
                    negated_hits.append(hit_record)
                elif temporal_context in ("historical", "hypothetical"):
                    soft_hits.append(hit_record)
                else:
                    # Current, non-negated -> FIRM HIT
                    firm_hits.append(hit_record)

    has_firm = len(firm_hits) > 0
    has_soft = len(soft_hits) > 0

    if has_firm:
        hit_type = "firm"
        primary_cat = firm_hits[0]["category"]
        override = "urgent"
    elif has_soft:
        hit_type = "soft"
        primary_cat = soft_hits[0]["category"]
        override = None
    else:
        hit_type = "none"
        primary_cat = None
        override = None

    return {
        "has_firm_hit": has_firm,
        "has_soft_hit": has_soft,
        "primary_category": primary_cat,
        "hit_type": hit_type,
        "firm_hits": firm_hits,
        "soft_hits": soft_hits,
        "negated_hits": negated_hits,
        "urgency_override": override,
    }
