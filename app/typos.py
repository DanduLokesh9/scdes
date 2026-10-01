"""Notice a misspelling in something they typed, and offer the correction.

The client's ticket, on question 11.1: "Noting to test this. I intentionally
mis-spelled 'the' to 'teh' to see if the system notices and correct."

It did not. Now it does.

Why a list and not a spellchecker
--------------------------------

The obvious build is a dictionary and a distance metric. That is the wrong
tool for this document. Module One's free-text answers are full of words no
dictionary holds — the agency's own name, a role title somebody invented, a
local ordinance, a county, a vendor, a statute, the name of a treatment
plant. A spellchecker flags every one of them, and a warning that is wrong
four times out of five trains the reader to dismiss it, including the time it
is right.

So this holds only misspellings that are *not words at all*, each mapped to
one correction. "Teh" is never anything. "Recieve" is never anything. Neither
is a name, a place or a term of art, so there is no false positive to train
anybody out of reading it. The list is shorter than a dictionary and it is
right every time it speaks, which is the trade worth making here.

Deliberately absent: British spellings. "Organisation", "licence",
"programme" and "judgement" are real words correctly spelled, and flagging an
American agency's British-spelled word as an error would be this application
having a view about somebody's prose. `app/polish.py` asks for US spelling
when it is rewriting a clause of its own accord; that is a different act from
telling somebody their typing is wrong.

Why it suggests rather than corrects
------------------------------------

The framework this module builds has one rule at the centre of it:

    No AI tool finalises an action affecting a person's rights, money,
    standing or employment. AI may draft, sort, flag and recommend; a person
    decides.

An application that quietly rewrites what somebody typed into a policy they
are going to adopt is not holding to the thing it is asking them to adopt.
And the risk is real rather than theoretical: `prose.py` carries these
answers into the document word for word, so a silent substitution is a silent
change to an adopted instrument.

So this notices, says what it thinks, and applies nothing. One click accepts
it. That is "notices and corrects" with the person still deciding, which is
the same shape as every other judgement this application makes.
"""

from __future__ import annotations

import re
from typing import Any

#: Misspellings that are not words in any variety of English, each with the
#: one thing it was meant to be. Anything with a legitimate reading — a
#: British spelling, a surname, an abbreviation — is not in here and must not
#: be added.
CORRECTIONS: dict[str, str] = {
    # The ones people actually type, including his.
    "teh": "the", "hte": "the", "tth": "the", "thge": "the",
    "adn": "and", "nad": "and", "andd": "and",
    "taht": "that", "thta": "that", "htat": "that",
    "thier": "their", "theri": "their",
    "thsi": "this", "tihs": "this",
    "wtih": "with", "witht": "with", "wiht": "with",
    "whcih": "which", "wich": "which", "whihc": "which",
    "becuase": "because", "becasue": "because", "beacuse": "because",
    "woudl": "would", "coudl": "could", "shoudl": "should",
    "shoud": "should", "shold": "should",
    "tehn": "then", "waht": "what", "youre": "you're",
    "alot": "a lot", "aswell": "as well",

    # Words a governance document is full of.
    "goverment": "government", "governmnet": "government",
    "govenment": "government", "goverance": "governance",
    "govenance": "governance", "governence": "governance",
    "enviroment": "environment", "enviromental": "environmental",
    "envirnoment": "environment",
    "commitee": "committee", "comittee": "committee",
    "commitie": "committee",
    "responsibilty": "responsibility", "responsiblity": "responsibility",
    "responsibilites": "responsibilities",
    "accountabilty": "accountability", "accountablity": "accountability",
    "authorithy": "authority", "authorty": "authority",
    "aproval": "approval", "approvel": "approval", "aprove": "approve",
    "aproved": "approved",
    "complience": "compliance", "complaince": "compliance",
    "complient": "compliant",
    "proceedure": "procedure", "proceedures": "procedures",
    "procedual": "procedural",
    "personel": "personnel", "personnell": "personnel",
    "retension": "retention",
    "critera": "criteria", "critieria": "criteria",
    "threshhold": "threshold", "threshholds": "thresholds",
    "accessability": "accessibility", "accesibility": "accessibility",
    "confidentialty": "confidentiality",
    "transparancy": "transparency", "transparancey": "transparency",
    "jurisdiciton": "jurisdiction", "jurisdication": "jurisdiction",
    "statuatory": "statutory", "statutary": "statutory",
    "ordinace": "ordinance", "ordinanace": "ordinance",
    "safegaurd": "safeguard", "safegaurds": "safeguards",
    "stakholder": "stakeholder", "stakeholer": "stakeholder",
    "oversite": "oversight",
    "proceedual": "procedural",
    "reccomend": "recommend", "recomend": "recommend",
    "recomended": "recommended", "reccomended": "recommended",
    "recomendation": "recommendation",
    "aquire": "acquire", "aquired": "acquired",
    "proceedes": "proceeds",
    "inteligence": "intelligence", "intellegence": "intelligence",
    "intelligance": "intelligence",
    "artifical": "artificial", "artificail": "artificial",
    "artifcial": "artificial",

    # General, and all of them non-words.
    "recieve": "receive", "recieved": "received",
    "seperate": "separate", "seperately": "separately",
    "seperation": "separation",
    "definately": "definitely", "definatly": "definitely",
    "occured": "occurred", "occurence": "occurrence",
    "occurrance": "occurrence",
    "accomodate": "accommodate", "acommodate": "accommodate",
    "acknowlege": "acknowledge", "acknowlegement": "acknowledgement",
    "publically": "publicly",
    "neccessary": "necessary", "necesary": "necessary",
    "refered": "referred", "transfered": "transferred",
    "begining": "beginning", "writting": "writing", "writen": "written",
    "adress": "address", "adresses": "addresses",
    "arguement": "argument",
    "assesment": "assessment", "assesments": "assessments",
    "calender": "calendar", "catagory": "category",
    "catagories": "categories",
    "existance": "existence", "familar": "familiar",
    "finaly": "finally", "foriegn": "foreign", "fourty": "forty",
    "garantee": "guarantee", "gaurantee": "guarantee",
    "harrass": "harass", "hieght": "height",
    "immediatly": "immediately", "independant": "independent",
    "knowlege": "knowledge", "liason": "liaison",
    "maintainance": "maintenance", "maintenence": "maintenance",
    "managment": "management", "mantain": "maintain",
    "noticable": "noticeable", "occassion": "occasion",
    "paralel": "parallel", "particulary": "particularly",
    "perminent": "permanent", "posession": "possession",
    "preceed": "precede", "prefered": "preferred",
    "questionaire": "questionnaire", "relevent": "relevant",
    "resistence": "resistance", "responsable": "responsible",
    "similiar": "similar", "succesful": "successful",
    "successfull": "successful", "supercede": "supersede",
    "suprise": "surprise", "thourough": "thorough",
    "tommorow": "tomorrow", "truely": "truly",
    "unfortunatly": "unfortunately", "untill": "until",
    "usefull": "useful", "vehical": "vehicle",
    "wether": "whether", "wheather": "whether", "whther": "whether",
    "wierd": "weird", "yeild": "yield",
    "priviledge": "privilege", "dissapear": "disappear",
    "embarass": "embarrass", "agressive": "aggressive",
    "deliberatly": "deliberately", "delibrately": "deliberately",
    "intentionaly": "intentionally", "inentionally": "intentionally",
    "seperatly": "separately", "consistant": "consistent",
    "consistantly": "consistently", "significent": "significant",
    "apparant": "apparent", "arbitary": "arbitrary",
    "specificaly": "specifically", "specificly": "specifically",
    "approriate": "appropriate", "appropiate": "appropriate",
    "appropriatly": "appropriately", "enviornment": "environment",
    "goverend": "governed", "reponsible": "responsible",
    "resonsible": "responsible", "reponsibility": "responsibility",
}

#: Words, apostrophes included so "you're" is one token rather than two.
_WORD = re.compile(r"[A-Za-z][A-Za-z']*")

#: How many to mention. Past a handful it stops being a note and becomes a
#: proofreading report, which is not what was asked for.
MOST = 6


def _cased(original: str, correction: str) -> str:
    """The correction, wearing the original's capitalisation.

    "Teh" at the start of a sentence should be offered as "The", not "the" —
    a suggestion that introduces a second error is worse than none.
    """
    if original.isupper() and len(original) > 1:
        return correction.upper()
    if original[:1].isupper():
        return correction[:1].upper() + correction[1:]
    return correction


def found(text: str) -> list[dict[str, Any]]:
    """Every misspelling in `text`, with what it was meant to be.

    One entry per distinct word rather than per occurrence: somebody who
    typed "teh" four times wants to be told once and have all four fixed.
    """
    seen: dict[str, dict[str, Any]] = {}
    for match in _WORD.finditer(text or ""):
        word = match.group(0)
        correction = CORRECTIONS.get(word.lower())
        if not correction:
            continue
        entry = seen.setdefault(word, {
            "word": word,
            "suggest": _cased(word, correction),
            "times": 0,
        })
        entry["times"] += 1
    return list(seen.values())[:MOST]


def corrected(text: str) -> str:
    """`text` with every known misspelling replaced.

    Whole words only, and the case carried across. Never called without
    somebody having accepted it first — see the note at the top of this file
    about why that matters.
    """
    def swap(match: re.Match) -> str:
        word = match.group(0)
        correction = CORRECTIONS.get(word.lower())
        return _cased(word, correction) if correction else word

    return _WORD.sub(swap, text or "")


def note(spellings: list[dict[str, Any]]) -> str:
    """One line for the screen, in their words rather than in ours."""
    if not spellings:
        return ""
    pairs = ", ".join(f"“{s['word']}” → “{s['suggest']}”"
                      for s in spellings)
    if len(spellings) == 1:
        return f"Possible typo: {pairs}. Nothing has been changed."
    return f"Possible typos: {pairs}. Nothing has been changed."
