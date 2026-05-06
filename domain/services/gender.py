"""Gender identification using pronouns + bio/name indicators."""
from __future__ import annotations
from typing import Any, Dict
from ._shapes import user_data

_FEMALE_P = {"she/her", "she", "her"}
_MALE_P = {"he/him", "he", "him"}
_NB_P = {"they/them", "they", "them", "ze/zir", "xe/xem", "it/its"}

_FEMALE_IND = [
    "she/her", "she", "her", "woman", "girl", "female", "lady", "mom", "mother",
    "wife", "daughter", "sister", "girlfriend", "actress", "queen", "princess",
    "mama", "mum", "mummy", "mommy", "mrs", "ms", "miss",
]
_MALE_IND = [
    "he/him", "he", "him", "man", "boy", "male", "guy", "dad", "father",
    "husband", "son", "brother", "boyfriend", "actor", "king", "prince",
    "papa", "daddy", "mr",
]
_NB_IND = [
    "they/them", "them", "they", "non-binary", "nonbinary", "nb", "enby",
    "genderfluid", "genderqueer", "agender", "ze/zir", "xe/xem",
]


def identify_gender(user_info: Dict[str, Any]) -> str:
    u = user_data(user_info)
    pronouns = u.get("pronouns") or []
    if isinstance(pronouns, list):
        for p in pronouns:
            text = ""
            if isinstance(p, dict):
                text = (p.get("pronoun") or "").lower().strip()
            elif isinstance(p, str):
                text = p.lower().strip()
            if text in _FEMALE_P:
                return "Female"
            if text in _MALE_P:
                return "Male"
            if text in _NB_P:
                return "Non-binary"

    bio = (u.get("biography") or "").lower()
    fn = (u.get("full_name") or "").lower()
    un = (u.get("username") or "").lower()
    text = f"{bio} {fn} {un}"

    f_score = sum(1 for w in _FEMALE_IND if w in text)
    m_score = sum(1 for w in _MALE_IND if w in text)
    n_score = sum(1 for w in _NB_IND if w in text)
    top = max(f_score, m_score, n_score)
    if top == 0:
        return "Unknown"
    if f_score == top:
        return "Female"
    if m_score == top:
        return "Male"
    return "Non-binary"
