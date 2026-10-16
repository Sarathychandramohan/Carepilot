"""
D:\\CarePilotAI\\backend\\tests\\test_redflag_11_categories.py

Full 11-category red-flag regression suite.

For EACH category this file tests:
  1. positive          — current, non-negated → must be FIRM HIT
  2. negated           — explicit negation     → must be NEGATED (no firm hit)
  3. historical        — past-tense context    → must be SOFT HIT
  4. hypothetical      — conditional framing   → must be SOFT HIT
  5. misspelled        — phonetic variant      → must be FIRM HIT (where regex covers it)
     (categories without meaningful misspelling variants use an additional positive variant)

Categories (11):
  1.  chest_pain
  2.  respiratory_distress
  3.  stroke_indicators
  4.  acute_hemorrhage
  5.  syncope_seizure
  6.  anaphylaxis
  7.  self_harm
  8.  meningitis_sepsis
  9.  acute_abdomen_gi_bleed
  10. sudden_severe_headache   [NEW]
  11. overdose_poisoning        [NEW]
"""
from __future__ import annotations

import pytest

from backend.app.pipeline.redflag import evaluate_red_flags

# ---------------------------------------------------------------------------
# Helper assertions
# ---------------------------------------------------------------------------

def assert_firm(result: dict, cat: str | None = None, label: str = ""):
    """Must produce a FIRM hit, optionally in a specific category."""
    assert result["has_firm_hit"], f"Expected FIRM hit but got none. {label}"
    assert result["hit_type"] == "firm", f"hit_type should be 'firm'. {label}"
    if cat:
        cats = {h["category"] for h in result["firm_hits"]}
        assert cat in cats, (
            f"Expected category '{cat}' in firm_hits {cats}. {label}"
        )


def assert_soft(result: dict, cat: str | None = None, label: str = ""):
    """Must produce a SOFT hit (no firm hit)."""
    assert not result["has_firm_hit"], f"Expected SOFT-only but got FIRM hit. {label}"
    assert result["has_soft_hit"], f"Expected SOFT hit but got none. {label}"
    assert result["hit_type"] == "soft", f"hit_type should be 'soft'. {label}"
    if cat:
        cats = {h["category"] for h in result["soft_hits"]}
        assert cat in cats, (
            f"Expected category '{cat}' in soft_hits {cats}. {label}"
        )


def assert_none(result: dict, label: str = ""):
    """Must produce no hit at all (or only negated)."""
    assert not result["has_firm_hit"], f"Expected NO firm hit. {label}"
    assert not result["has_soft_hit"], f"Expected NO soft hit. {label}"
    assert result["hit_type"] == "none", f"hit_type should be 'none'. {label}"


def assert_negated(result: dict, label: str = ""):
    """Must produce no firm or soft hit (negated)."""
    assert not result["has_firm_hit"], f"Expected NO firm hit (negated). {label}"
    assert not result["has_soft_hit"], f"Expected NO soft hit (negated). {label}"


# ===========================================================================
# 1. chest_pain
# ===========================================================================

class TestChestPain:
    CAT = "chest_pain"

    def test_positive_chest_pain(self):
        r = evaluate_red_flags("I have chest pain and pressure in my chest right now.")
        assert_firm(r, self.CAT, "chest pain positive")

    def test_positive_heart_attack(self):
        r = evaluate_red_flags("I think I'm having a heart attack.")
        assert_firm(r, self.CAT, "heart attack positive")

    def test_positive_pain_radiating(self):
        r = evaluate_red_flags("I have pain radiating to my left arm.")
        assert_firm(r, self.CAT, "pain radiating to left arm")

    def test_negated_chest_pain(self):
        r = evaluate_red_flags("I have no chest pain or pressure.")
        assert_negated(r, "negated chest pain")

    def test_historical_chest_pain(self):
        r = evaluate_red_flags("I had a heart attack 3 years ago and recovered fully.")
        assert_soft(r, self.CAT, "historical chest pain")

    def test_hypothetical_chest_pain(self):
        r = evaluate_red_flags("What should I do if I experience chest pain while exercising?")
        assert_soft(r, self.CAT, "hypothetical chest pain")

    def test_misspelled_angina(self):
        # "angina" is a trigger; alternate spelling variant
        r = evaluate_red_flags("The doctor said I have angina and I'm feeling it now.")
        assert_firm(r, self.CAT, "angina misspell variant")


# ===========================================================================
# 2. respiratory_distress
# ===========================================================================

class TestRespiratoryDistress:
    CAT = "respiratory_distress"

    def test_positive_shortness_of_breath(self):
        r = evaluate_red_flags("I have severe shortness of breath right now and can barely move.")
        assert_firm(r, self.CAT, "severe SOB positive")

    def test_positive_cant_breathe(self):
        r = evaluate_red_flags("I can't breathe properly, my lips are turning blue.")
        assert_firm(r, self.CAT, "can't breathe positive")

    def test_positive_gasping(self):
        r = evaluate_red_flags("She is gasping for air and cannot speak.")
        assert_firm(r, self.CAT, "gasping for air")

    def test_negated_shortness_of_breath(self):
        r = evaluate_red_flags("I have no shortness of breath and no chest pain.")
        assert_negated(r, "negated SOB")

    def test_historical_dyspnea(self):
        r = evaluate_red_flags("I had severe shortness of breath last winter but it resolved.")
        assert_soft(r, self.CAT, "historical dyspnea")

    def test_hypothetical_respiratory(self):
        r = evaluate_red_flags("What if someone is struggling to breathe during an asthma attack?")
        assert_soft(r, self.CAT, "hypothetical respiratory distress")

    def test_misspelled_breathlessness(self):
        r = evaluate_red_flags("I'm experiencing severe breathlessness since this morning.")
        assert_firm(r, self.CAT, "breathlessness variant")


# ===========================================================================
# 3. stroke_indicators
# ===========================================================================

class TestStrokeIndicators:
    CAT = "stroke_indicators"

    def test_positive_slurred_speech(self):
        r = evaluate_red_flags("My speech is suddenly slurred and my face is drooping.")
        assert_firm(r, self.CAT, "slurred speech + face droop")

    def test_positive_arm_weakness(self):
        r = evaluate_red_flags("I have sudden weakness in my left arm and leg right now.")
        assert_firm(r, self.CAT, "sudden arm weakness")

    def test_positive_stroke_mention(self):
        r = evaluate_red_flags("I think I'm having a stroke.")
        assert_firm(r, self.CAT, "stroke mention")

    def test_negated_face_droop(self):
        r = evaluate_red_flags("My face is not drooping and I have no weakness.")
        assert_negated(r, "negated face droop")

    def test_historical_stroke(self):
        r = evaluate_red_flags("I had a mini stroke 2 years ago.")
        assert_soft(r, self.CAT, "historical stroke")

    def test_hypothetical_stroke(self):
        r = evaluate_red_flags("What should I do if someone has sudden vision loss and weakness?")
        assert_soft(r, self.CAT, "hypothetical stroke")

    def test_misspelled_tia(self):
        r = evaluate_red_flags("Doctor said it might be a TIA occurring right now.")
        assert_firm(r, self.CAT, "TIA abbreviation variant")


# ===========================================================================
# 4. acute_hemorrhage
# ===========================================================================

class TestAcuteHemorrhage:
    CAT = "acute_hemorrhage"

    def test_positive_vomiting_blood(self):
        r = evaluate_red_flags("I've been vomiting blood for the past hour.")
        assert_firm(r, self.CAT, "vomiting blood positive")

    def test_positive_coughing_blood(self):
        r = evaluate_red_flags("I am coughing up blood and feeling very weak.")
        assert_firm(r, self.CAT, "coughing up blood positive")

    def test_positive_bleeding_heavily(self):
        r = evaluate_red_flags("I'm bleeding heavily from a wound and can't stop it.")
        assert_firm(r, self.CAT, "bleeding heavily positive")

    def test_negated_blood_in_stool(self):
        r = evaluate_red_flags("There is no blood in my stool according to the test.")
        assert_negated(r, "negated blood in stool")

    def test_historical_hemorrhage(self):
        r = evaluate_red_flags("I had hematemesis last month which has now resolved.")
        assert_soft(r, self.CAT, "historical hematemesis")

    def test_hypothetical_hemorrhage(self):
        r = evaluate_red_flags("What if someone is bleeding heavily from a cut?")
        assert_soft(r, self.CAT, "hypothetical hemorrhage")

    def test_melena_variant(self):
        r = evaluate_red_flags("I am currently passing black tarry stool and feeling very weak.")
        assert_firm(r, self.CAT, "melena/black tarry stool present tense")

    def test_melena_historical_is_soft(self):
        # 'yesterday' triggers historical classification -> correctly SOFT, not FIRM
        r = evaluate_red_flags("I have been passing black tarry stool since yesterday evening.")
        assert_soft(r, self.CAT, "melena yesterday = historical soft")


# ===========================================================================
# 5. syncope_seizure
# ===========================================================================

class TestSyncopeSeizure:
    CAT = "syncope_seizure"

    def test_positive_passed_out(self):
        r = evaluate_red_flags("My husband passed out in the kitchen and is now unresponsive.")
        assert_firm(r, self.CAT, "passed out + unresponsive")

    def test_positive_seizure(self):
        r = evaluate_red_flags("He is having a seizure and shaking uncontrollably.")
        assert_firm(r, self.CAT, "seizure positive")

    def test_positive_fainted(self):
        r = evaluate_red_flags("I just fainted and hit my head on the floor.")
        assert_firm(r, self.CAT, "fainted positive")

    def test_negated_syncope(self):
        r = evaluate_red_flags("I did not pass out or lose consciousness.")
        assert_negated(r, "negated syncope")

    def test_historical_seizure(self):
        r = evaluate_red_flags("I had a seizure 6 months ago but haven't had one since.")
        assert_soft(r, self.CAT, "historical seizure")

    def test_hypothetical_seizure(self):
        r = evaluate_red_flags("What should I do if someone has a convulsion?")
        assert_soft(r, self.CAT, "hypothetical convulsion")

    def test_blacked_out_variant(self):
        r = evaluate_red_flags("I blacked out for a few seconds at the gym today.")
        assert_firm(r, self.CAT, "blacked out variant")


# ===========================================================================
# 6. anaphylaxis
# ===========================================================================

class TestAnaphylaxis:
    CAT = "anaphylaxis"

    def test_positive_anaphylaxis(self):
        r = evaluate_red_flags("I think I'm going into anaphylaxis after eating peanuts.")
        assert_firm(r, self.CAT, "anaphylaxis positive")

    def test_positive_throat_swelling(self):
        r = evaluate_red_flags("My throat is swelling and closing up after the bee sting.")
        assert_firm(r, self.CAT, "throat swelling positive")

    def test_positive_hives_and_breathing(self):
        r = evaluate_red_flags("I have hives and difficulty breathing after taking the medication.")
        assert_firm(r, self.CAT, "hives and difficulty breathing")

    def test_negated_throat_swelling(self):
        r = evaluate_red_flags("There is no throat swelling or airway closing.")
        assert_negated(r, "negated throat swelling")

    def test_historical_anaphylaxis(self):
        r = evaluate_red_flags("I had anaphylaxis last year after a bee sting but was treated.")
        assert_soft(r, self.CAT, "historical anaphylaxis")

    def test_hypothetical_anaphylaxis(self):
        r = evaluate_red_flags("What if someone experiences tongue swelling after eating shellfish?")
        assert_soft(r, self.CAT, "hypothetical anaphylaxis")

    def test_swelling_shut_variant(self):
        r = evaluate_red_flags("My airway is swelling shut right now.")
        assert_firm(r, self.CAT, "swelling shut variant")


# ===========================================================================
# 7. self_harm
# ===========================================================================

class TestSelfHarm:
    CAT = "self_harm"

    def test_positive_suicidal(self):
        r = evaluate_red_flags("I have been having suicidal thoughts and want to end my life.")
        assert_firm(r, self.CAT, "suicidal positive")

    def test_positive_want_to_die(self):
        r = evaluate_red_flags("I want to die. I have no reason to live anymore.")
        assert_firm(r, self.CAT, "want to die positive")

    def test_positive_kill_myself(self):
        r = evaluate_red_flags("I'm thinking about killing myself tonight.")
        assert_firm(r, self.CAT, "kill myself positive")

    def test_negated_self_harm(self):
        r = evaluate_red_flags("I am not suicidal and do not want to harm myself.")
        assert_negated(r, "negated self harm")

    def test_historical_self_harm(self):
        r = evaluate_red_flags("I had dark thoughts and hurt myself years ago in college but I'm better now.")
        assert_soft(r, self.CAT, "historical self harm")

    def test_hypothetical_self_harm(self):
        r = evaluate_red_flags("What should I do if a patient says they want to kill themselves?")
        assert_soft(r, self.CAT, "hypothetical self harm")

    def test_overdose_self_harm_variant(self):
        # self_harm also covers intentional overdose of a pill bottle
        r = evaluate_red_flags("I think my daughter swallowed her pill bottle intentionally.")
        assert_firm(r, self.CAT, "pill bottle overdose self harm")


# ===========================================================================
# 8. meningitis_sepsis
# ===========================================================================

class TestMeningitisSepsis:
    CAT = "meningitis_sepsis"

    def test_positive_stiff_neck(self):
        r = evaluate_red_flags("I have a severe stiff neck and a high fever of 104.")
        assert_firm(r, self.CAT, "stiff neck + high fever")

    def test_positive_fever_and_stiff_neck(self):
        r = evaluate_red_flags("My child has a high fever of 103 and a stiff neck.")
        assert_firm(r, self.CAT, "fever 103 + stiff neck")

    def test_positive_stiff_neck_alone(self):
        r = evaluate_red_flags("I woke up with a severe stiff neck I cannot turn my head.")
        assert_firm(r, self.CAT, "severe stiff neck alone")

    def test_negated_stiff_neck(self):
        r = evaluate_red_flags("I do not have a stiff neck or fever.")
        assert_negated(r, "negated stiff neck")

    def test_historical_meningitis(self):
        r = evaluate_red_flags("I had a stiff neck and high fever years ago and was hospitalized.")
        assert_soft(r, self.CAT, "historical meningitis")

    def test_hypothetical_meningitis(self):
        r = evaluate_red_flags("What if someone has a stiff neck and a very high fever?")
        assert_soft(r, self.CAT, "hypothetical meningitis")

    def test_neck_stiffness_variant(self):
        r = evaluate_red_flags("I have neck stiffness and fever of 103, is this serious?")
        assert_firm(r, self.CAT, "neck stiffness + high fever variant")


# ===========================================================================
# 9. acute_abdomen_gi_bleed
# ===========================================================================

class TestAcuteAbdomenGIBleed:
    CAT = "acute_abdomen_gi_bleed"

    def test_positive_severe_abdominal_pain(self):
        r = evaluate_red_flags("I have severe abdominal pain that started suddenly.")
        assert_firm(r, self.CAT, "severe abdominal pain positive")

    def test_positive_stomach_pain_vomiting(self):
        r = evaluate_red_flags("I have stomach pain and vomiting that won't stop.")
        assert_firm(r, self.CAT, "stomach pain and vomiting")

    def test_positive_acute_belly_pain(self):
        r = evaluate_red_flags("I have acute belly pain radiating to my back.")
        assert_firm(r, self.CAT, "acute belly pain positive")

    def test_negated_abdominal_pain(self):
        r = evaluate_red_flags("I have no severe abdominal pain or vomiting.")
        assert_negated(r, "negated abdominal pain")

    def test_historical_gi_bleed(self):
        r = evaluate_red_flags("I had severe abdominal pain last month and was hospitalised.")
        assert_soft(r, self.CAT, "historical GI bleed")

    def test_hypothetical_abdominal(self):
        r = evaluate_red_flags("What should I do if I develop severe abdominal pain?")
        assert_soft(r, self.CAT, "hypothetical abdominal pain")

    def test_mild_does_not_trigger(self):
        r = evaluate_red_flags("I have mild stomach discomfort and gas after a heavy meal.")
        assert_none(r, "mild stomach discomfort — no trigger expected")


# ===========================================================================
# 10. sudden_severe_headache  [NEW]
# ===========================================================================

class TestSuddenSevereHeadache:
    CAT = "sudden_severe_headache"

    def test_positive_worst_headache_of_life(self):
        r = evaluate_red_flags("This is the worst headache of my life, it hit suddenly.")
        assert_firm(r, self.CAT, "worst headache of my life")

    def test_positive_thunderclap_headache(self):
        r = evaluate_red_flags("I have a thunderclap headache that started 10 minutes ago.")
        assert_firm(r, self.CAT, "thunderclap headache")

    def test_positive_sudden_severe_headache(self):
        r = evaluate_red_flags("I suddenly have a severe headache that came on suddenly and won't stop.")
        assert_firm(r, self.CAT, "sudden severe headache")

    def test_positive_headache_with_stiff_neck(self):
        r = evaluate_red_flags("I have a headache with stiff neck and sensitivity to light.")
        assert_firm(r, self.CAT, "headache with stiff neck + light sensitivity")

    def test_positive_subarachnoid(self):
        r = evaluate_red_flags("The doctor suspects subarachnoid hemorrhage from my symptoms.")
        assert_firm(r, self.CAT, "subarachnoid mention")

    def test_positive_head_exploding(self):
        r = evaluate_red_flags("My head is exploding right now, the pain is unbearable.")
        assert_firm(r, self.CAT, "head exploding colloquial")

    def test_negated_severe_headache(self):
        r = evaluate_red_flags("I do not have a sudden or severe headache at all.")
        assert_negated(r, "negated severe headache")

    def test_historical_worst_headache(self):
        r = evaluate_red_flags("I had the worst headache of my life last year after a trauma.")
        assert_soft(r, self.CAT, "historical worst headache")

    def test_hypothetical_thunderclap(self):
        r = evaluate_red_flags("What if someone suddenly has a thunderclap headache?")
        assert_soft(r, self.CAT, "hypothetical thunderclap headache")

    def test_mild_headache_does_not_trigger(self):
        r = evaluate_red_flags("I have a mild headache after staring at my screen all day.")
        assert_none(r, "mild everyday headache — no trigger expected")

    def test_misspelled_worst_headache(self):
        # Alternate natural phrasing
        r = evaluate_red_flags("This is the worst headache I've ever had in my entire life.")
        assert_firm(r, self.CAT, "worst headache I've ever had variant")


# ===========================================================================
# 11. overdose_poisoning  [NEW]
# ===========================================================================

class TestOverdosePoisoning:
    CAT = "overdose_poisoning"

    def test_positive_overdose_bare(self):
        r = evaluate_red_flags("I think my child had an overdose of their medication.")
        assert_firm(r, self.CAT, "overdose bare positive")

    def test_positive_accidental_overdose(self):
        r = evaluate_red_flags("My toddler had an accidental overdose of children's Tylenol.")
        assert_firm(r, self.CAT, "accidental overdose positive")

    def test_positive_too_many_pills(self):
        r = evaluate_red_flags("I accidentally took too many pills of my blood pressure medication.")
        assert_firm(r, self.CAT, "too many pills positive")

    def test_positive_took_whole_bottle(self):
        r = evaluate_red_flags("My son swallowed an entire bottle of his medication.")
        assert_firm(r, self.CAT, "swallowed entire bottle positive")

    def test_positive_poisoning(self):
        r = evaluate_red_flags("We suspect poisoning from some household chemical she drank.")
        assert_firm(r, self.CAT, "poisoning positive")

    def test_positive_carbon_monoxide(self):
        r = evaluate_red_flags("There is a carbon monoxide leak in the house and everyone feels sick.")
        assert_firm(r, self.CAT, "carbon monoxide poisoning")

    def test_positive_opioid_overdose(self):
        r = evaluate_red_flags("My partner is not breathing and may have had a fentanyl overdose.")
        assert_firm(r, self.CAT, "fentanyl overdose positive")

    def test_positive_heroin_od(self):
        r = evaluate_red_flags("I found someone unresponsive with blue lips after a heroin OD.")
        assert_firm(r, self.CAT, "heroin OD positive")

    def test_negated_overdose(self):
        r = evaluate_red_flags("There was no overdose — she only took the prescribed dose.")
        assert_negated(r, "negated overdose")

    def test_historical_overdose(self):
        r = evaluate_red_flags("He had an overdose last year and was treated at the hospital.")
        assert_soft(r, self.CAT, "historical overdose")

    def test_hypothetical_overdose(self):
        r = evaluate_red_flags("What should I do if someone accidentally overdoses on medication?")
        assert_soft(r, self.CAT, "hypothetical overdose")

    def test_misspelled_overdose_phonetic(self):
        # Natural colloquial form "OD'd"
        r = evaluate_red_flags("I think he OD'd on heroin and is unresponsive right now.")
        assert_firm(r, self.CAT, "OD'd on heroin phonetic variant")

    def test_normal_dose_does_not_trigger(self):
        r = evaluate_red_flags("I took my medication as prescribed and feel fine.")
        assert_none(r, "normal medication dose — no trigger expected")
