"""Tidy the wording of a framework without changing what it requires.

The client asked for this as one of two questions at the download: "How would
you like the language to appear: As written or Polished. As written is just
the raw output as you created, but polished uses an LLM to run through, clean
up, and do some of the editorial work to closer match that north star we
have."

And the reason, which is the real brief: "I'm guessing they're going to
default to polished because they don't have the time to run through it again
and do a full rework. If it is going to take more than an hour to rewrite it,
they're not going to recommend to others to use it."

He is right about that. Assembled prose reads like assembled prose, and
nobody is going to hand-edit ninety-six answers' worth of clauses.

Why this module is mostly refusals
----------------------------------

`app/prose.py` makes one promise: every sentence is built from something the
organization actually chose, and nothing is invented. That promise is the
product. A language model let loose on a governance document will, sooner or
later, turn "may" into "shall", merge two clauses and lose a condition, add a
review cycle nobody agreed to, or quietly improve a sentence into a different
obligation. In a policy, those are not typos — they are changes to what the
organization is bound to.

So polishing is deliberately small and deliberately suspicious of itself:

**One clause at a time.** Never the document, never a section. The model sees
a single clause and is asked to rewrite that clause. It cannot merge, reorder
or drop anything, because it is never holding more than one.

**Their own words are never sent.** A clause the organization typed —
free text, their own paragraph, a role title they named — is skipped
entirely. `prose.py` already refuses to re-case those; this refuses to
rewrite them.

**Every rewrite is checked before it is kept.** Modal verbs must match,
numbers must match, names must survive, the length must be in a sane band.
A clause that fails any check is kept exactly as it was assembled, and the
failure is counted and reported.

**It says what it did.** The document records that the language was polished,
how many clauses were changed, how many were rejected, and which model did
it. The as-written text stays in the version history, so anybody can compare.

**It fails to the safe side.** No provider, no key, an error, a timeout, a
refusal — every one of those returns the assembled text unchanged rather
than a half-polished document.
"""

from __future__ import annotations

import concurrent.futures
import re
from dataclasses import dataclass, field
from typing import Any

#: How many clauses are polished at once.
#:
#: Measured, not guessed: one clause takes about 2.7 seconds, and a framework
#: is roughly ninety clauses. Serially that is four minutes of a download
#: button doing nothing, which is its own kind of unusable — the client's
#: whole point about this feature is that nobody will wait. Eight at a time
#: brings it to well under a minute while staying far short of any rate
#: limit, and the SDK retries a 429 on its own if one is hit.
AT_ONCE = 8

#: The three strengths a clause can carry, in descending order of force.
#:
#: Direction is what matters, not the individual word. Measured on a real
#: framework, the single most common edit was turning the present indicative
#: into "shall" — "The register is checked twice a year" becoming "The
#: register shall be checked twice a year". An earlier version of this module
#: compared modal counts exactly and threw away half of every pass for that
#: reason, which was a mistake: in drafting convention the present indicative
#: already states a rule in force, so rendering it as "shall" changes the
#: register of the sentence and not the duty. That is precisely the editorial
#: move toward an adopted instrument that the client asked for.
#:
#: What is refused is any *weakening* — a duty becoming a recommendation or a
#: permission — and any *strengthening* of something that was optional. So:
#: mandatory may rise but never fall; advisory and permissive must be
#: preserved exactly, because a "should" that becomes "shall", or a "may"
#: that becomes "must", binds the organization to something it did not agree
#: to.
MANDATORY = ("shall", "must", "will", "cannot")
ADVISORY = ("should", "encouraged", "expected", "recommended")
#: "May" and not "can". Every "can" the assembled prose produces is a
#: capability — "a person can always be reached", "whether a tool already
#: held can address the problem" — and not a permission, so counting it as
#: one refused "is capable of addressing the problem", which is a fair edit.
PERMISSIVE = ("may", "permitted", "optional", "discretion")

#: Negations and prohibitions, which must survive. Dropping one inverts the
#: rule, and no amount of improved flow is worth that.
NEGATIONS = ("not", "no", "never", "nor", "neither", "cannot", "without",
             "nobody", "none", "nothing")

#: A negation can be carried by a prefix instead of a word: "do not agree"
#: becoming "disagree" says the same thing with one word fewer, and is one of
#: the few edits that genuinely improves an assembled clause. So a missing
#: negation is forgiven — but only when the rewrite contains a new word that
#: is a negated form of a word the original itself used. That is narrow
#: enough to admit "disagree" for "not agree" and to refuse "under", which
#: merely begins with the same two letters.
NEGATING_PREFIXES = ("dis", "un", "non", "im", "in", "ir", "il")

#: Words that set the scope or the timing of a duty, counted exactly.
#:
#: "Unless" and "except" carve out exceptions, and dropping one broadens the
#: rule. "Only" narrows it. "Where", "if" and "when" make a rule conditional,
#: and adding one turns a statement of fact into a hypothesis — measured, a
#: rewrite did exactly that: "This organization runs programs delegated by
#: another level of government" came back as "Where the organization delivers
#: programs delegated…", which is no longer a statement that it does.
CONDITIONS = ("unless", "except", "only", "where", "if", "when", "until",
              "before", "after")

#: "Within" is two different words. In "within 3 days" it is a deadline and
#: load-bearing; in "someone within the program" it is a preposition and
#: means nothing to the rule. Counting both refused "someone in the program"
#: becoming "a person within the program", so it is counted only when a time
#: word follows it closely.
TIME_WORDS = ("day", "days", "week", "weeks", "month", "months", "year",
              "years", "hour", "hours", "minute", "minutes", "time",
              "deadline", "period", "quarter")

#: Words that turn a closed list into an illustrative one. "Restricted
#: information: names, addresses, personnel files" is exhaustive; the same
#: sentence with "includes:" in it is not, and which one it is decides
#: whether something absent from the list is permitted.
OPEN_ENDED = ("include", "includes", "including", "such as", "among others",
              "for example", "and the like", "without limitation")

#: How often something must happen is a requirement, and it is one that
#: carries no digits, so the number check above cannot see it. A rewrite that
#: appends "and shall be reviewed annually" to a clause that never mentioned
#: a review cycle has committed the organization to an annual review. Counted
#: as a group total rather than word by word, so "every year" may become
#: "annually" but nothing may appear from nowhere.
RECURRENCE = ("annual", "annually", "yearly", "quarterly", "quarter",
              "monthly", "weekly", "daily", "biennially", "biannually",
              "semiannually", "periodically", "regularly", "routinely",
              "ongoing", "continuous", "continuously", "every year",
              "each year", "once a year", "twice a year", "each month",
              "every month", "each quarter", "every quarter")

#: Phrases that mean the same thing as a word already being counted, folded
#: together before anything is tallied.
#:
#: Two reasons this is needed. The obvious one is that "prior to" for
#: "before" is a fair edit and an exact count refuses it. The subtle one is
#: "no later than", which contains the word "no" and is not a negation at
#: all — without this fold, a rewrite that tightened a deadline into "no
#: later than three days" was refused for inventing a negation.
#: Order matters. "The following are told:" introduces a list and is not a
#: temporal at all, so it has to be taken out of the way before "following"
#: is folded into "after" — otherwise a clause reading "the following are
#: told" counts an "after" that was never there, and the rewrite is refused
#: for dropping a deadline it never had. Measured: that is exactly what
#: happened to the incident-notification clause.
SAME_THING = (
    ("the following", "these"),
    # Before "without" is counted as a negation. "Regardless of whether an AI
    # tool was involved" came back as "without regard to whether an AI tool
    # was involved", which is the same sentence and was refused for inventing
    # a negation.
    ("without regard to", "regardless of"),
    ("prior to", "before"),
    ("in advance of", "before"),
    ("no later than", "within"),
    ("not later than", "within"),
    ("subsequent to", "after"),
    ("following", "after"),
    # "Upon" is temporal in "upon termination" and part of the verb in
    # "relied upon". The phrasal forms are settled to "on" first, so that the
    # general fold below cannot read "the answer was relied upon" as a
    # condition that appeared out of nowhere.
    ("relied upon", "relied on"),
    ("rely upon", "rely on"),
    ("based upon", "based on"),
    ("agreed upon", "agreed on"),
    ("acted upon", "acted on"),
    ("decided upon", "decided on"),
    ("called upon", "called on"),
    # "Our data is returned and deleted when we leave" and "…upon our
    # departure" say the same thing, and counting only the first spelling
    # refused the rewrite for dropping a condition it had kept.
    ("upon", "when"),
    ("no one", "nobody"),
)

#: A rewrite shorter than this fraction of the original has almost certainly
#: dropped something; longer than the upper bound has almost certainly added
#: something. Both are refused rather than inspected word by word.
#:
#: The upper bound is the main defence against an appended requirement, so it
#: is set from the measured spread rather than picked: raising a clause into
#: a formal register ran 1.0 to 1.4 times the length of the original across a
#: whole framework, and 1.65 leaves room above that without leaving room for
#: another sentence.
SHORTEST = 0.55
LONGEST = 1.65

#: What the job is. Narrow on purpose: the part that matters most is the list
#: of things it may not do. Written in three shared pieces because there are
#: two jobs — a clause and the meaning of a defined term — and prohibitions
#: kept in two places drift apart.
#: The two term rules, and both were learned from a measured document.
#:
#: The document defines "AI tool" in its definitions section, so that is the
#: term and expanding it is not a formalisation — it is a second name for a
#: defined thing. Asked to expand 'AI', the tool produced a framework using
#: "AI tool" fourteen times, "artificial intelligence tool" seven and
#: "artificial intelligence system" three, all meaning the same thing, which
#: is exactly the ambiguity a definitions section exists to prevent.
_HOUSE_STYLE = (
    "Two rules about terms:\n"
    "- Call the document 'this framework'. Never call it 'this policy', "
    "'these rules' or anything else — one clause calling it a policy while "
    "the rest call it a framework reads as two documents stitched "
    "together.\n"
    "- This framework defines the term 'AI tool'. Write 'AI tool' and leave "
    "it exactly so. Never expand it to 'artificial intelligence tool', never "
    "write 'artificial intelligence system', and never spell out 'AI'. One "
    "defined term, used the same way everywhere.\n\n"
    "Prefer 'used' to 'utilized', and plain verbs to bureaucratic ones.\n\n"
)

_NEVER = (
    "You must not:\n"
    "- add any requirement, condition, date, number, frequency, role or "
    "exception, or remove any of them\n"
    "- change an existing 'shall', 'must', 'may' or 'should' into a "
    "different one, or change any negation\n"
    "- make a closed list open: never add 'including', 'such as' or 'for "
    "example'\n"
    "- name any body, office or organization that the text does not already "
    "name, and never invent a name for the organization itself\n"
    "- change who does something, or to whom\n"
    "- add a preamble, a heading, a comment, or quotation marks\n"
    "- explain what you changed, or write about the edit at all\n\n"
)

_CLOSE = (
    "Return only the rewritten text, as one or more plain sentences. If it is "
    "already well written, return it unchanged. If you judge that it cannot "
    "be improved without breaking one of the rules above, return it "
    "unchanged rather than saying so."
)

INSTRUCTION = (
    "You are copy-editing one clause of an adopted United States "
    "public-sector policy document. Improve only the wording: grammar, flow, "
    "and consistency of terms. Write in the register of an adopted "
    "instrument, in United States spelling.\n\n"
    "You may:\n"
    "- render a rule stated in the present indicative as 'shall', so 'The "
    "register is checked twice a year' may become 'The register shall be "
    "checked twice a year'\n"
    "- replace a plain word with its formal equivalent\n"
    "- fix a sentence that does not parse\n"
    "- correct a plain misspelling\n\n"
    + _HOUSE_STYLE + _NEVER + _CLOSE
)

#: Definitions are a different job, and treating them as clauses did visible
#: damage. "The Council. The body in which responsibility for decisions under
#: this framework is vested" came back as "Responsibility for decisions under
#: this framework shall be vested in an existing body", which is no longer a
#: definition of anything — it is a restatement of the clause that vests it,
#: sitting under a headword it no longer defines.
DEFINING = (
    "You are copy-editing the meaning of a defined term in an adopted United "
    "States public-sector policy document. Improve only the wording: "
    "grammar, flow, and consistency of terms. Write in the register of an "
    "adopted instrument, in United States spelling.\n\n"
    "It must remain a definition. A definition says what a term means; it "
    "requires nothing of anybody, because the requirements live in the "
    "clauses elsewhere in the document. So do not introduce 'shall' or "
    "'must', and do not turn the meaning into a rule: 'The body in which "
    "responsibility for decisions is vested' must not become 'Responsibility "
    "for decisions shall be vested in a body'.\n\n"
    "You may replace a plain word with its formal equivalent and fix a "
    "sentence that does not parse.\n\n"
    + _HOUSE_STYLE + _NEVER + _CLOSE
)


@dataclass
class Outcome:
    """What a polish pass did, for the document to report honestly."""

    asked: int = 0
    changed: int = 0
    kept: int = 0
    refused: int = 0
    skipped_their_words: int = 0
    #: Misspellings corrected, and which. Counted apart from everything else
    #: because it happens to text the writing tool never sees — see
    #: `_fix_spelling` — and because it is the one change made to somebody's
    #: own sentences, which is worth naming rather than folding into a total.
    spelled: int = 0
    spelled_words: list[str] = field(default_factory=list)
    provider: str = ""
    note: str = ""
    #: Every clause a check rejected, with the reason, so a rejection can be
    #: looked at rather than merely counted.
    rejections: list[dict[str, str]] = field(default_factory=list)

    @property
    def ran(self) -> bool:
        return self.asked > 0 or self.spelled > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "asked": self.asked, "changed": self.changed, "kept": self.kept,
            "refused": self.refused,
            "their_words_untouched": self.skipped_their_words,
            "provider": self.provider, "note": self.note,
            "rejections": self.rejections[:20],
        }

    def summary(self) -> str:
        """One sentence for the document's provenance page."""
        if not self.ran:
            return self.note or "The language was not polished."
        if not self.asked:
            return (f"{self.spelled} misspelling"
                    f"{'' if self.spelled == 1 else 's'} were corrected "
                    f"({', '.join(self.spelled_words[:8])}). "
                    + (self.note or ""))
        parts = [f"{self.changed} of {self.asked} clauses were reworded"]
        if self.spelled:
            parts.append(f"{self.spelled} misspelling"
                         f"{'' if self.spelled == 1 else 's'} were corrected "
                         f"({', '.join(self.spelled_words[:8])})")
        if self.refused:
            parts.append(f"{self.refused} rewrite"
                         f"{'' if self.refused == 1 else 's'} were rejected "
                         f"by the checks and the original kept")
        if self.skipped_their_words:
            parts.append(f"{self.skipped_their_words} clause"
                         f"{'' if self.skipped_their_words == 1 else 's'} in "
                         f"your own words were left untouched")
        return ", ".join(parts) + "."


def available() -> tuple[bool, str]:
    """Whether polishing can happen at all, and why not if not."""
    try:
        from app.provider import AnthropicProvider
    except Exception as exc:                              # noqa: BLE001
        return False, f"The language provider could not be loaded: {exc}"
    if not AnthropicProvider.available():
        return False, ("Polishing needs an AI writing tool configured on "
                       "this server. Without one the document is produced "
                       "exactly as your answers assemble it, which is the "
                       "other option on that question.")
    return True, ""


# --------------------------------------------------------------- the checking

def _words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", (text or "").lower())


def _one_name(text: str) -> str:
    """The defined term in one form, so a comparison cannot notice which.

    Two checks have to know about it, and both were getting it wrong.

    The length band, because the two spellings differ by twenty-one
    characters. An earlier version expanded rather than contracted, which
    was right while the instruction asked for expansion and wrong the moment
    it asked for the defined term instead: "Staff and the public are given
    30 days before a tool is turned off" became "Staff and the public shall
    be given 30 days' notice before an AI tool is withdrawn from service",
    a 42% rewrite that was measured as 73% growth and thrown away, because
    the words "AI tool" were counted as though they read "artificial
    intelligence tool".

    And the name check, because "AI" is capitalized, so a clause that
    changed spelling looked like one that had dropped a named thing.
    """
    return re.sub(r"artificial intelligence", "AI", text or "",
                  flags=re.IGNORECASE)


def _length(text: str) -> int:
    return len(_one_name(text))


#: Straight and curly double quotes. Single quotes are left out: the
#: assembled prose uses them for a quoted role title — "commonly called a
#: ‘product owner’" — so counting them would refuse every rewrite of that
#: clause.
QUOTE_MARKS = "\"“”"


def _quotes(text: str) -> int:
    return sum((text or "").count(mark) for mark in QUOTE_MARKS)


def _numbers(text: str) -> list[str]:
    """Every number and date-like token. A policy's numbers are load-bearing —
    "within three days" is not "within five days"."""
    return sorted(re.findall(r"\d[\d,.:/-]*", text or ""))


def _plain(text: str) -> str:
    """Lowercased, punctuation gone, equivalent phrases folded to one form.

    Punctuation has to go before the folding: "30 days' notice, prior to" and
    "prior to" should fold the same way, and a phrase followed by a comma
    would otherwise not match.
    """
    low = re.sub(r"[^a-z0-9']+", " ", (text or "").lower())
    low = f" {low.strip()} "
    for phrase, instead in SAME_THING:
        low = low.replace(f" {phrase} ", f" {instead} ")
    return low


def _tally(text: str, words: tuple[str, ...]) -> dict[str, int]:
    """How many times each of `words` appears, as a whole word or phrase."""
    low = _plain(text)
    return {word: low.count(f" {word} ") if " " in word
            else _words(low).count(word) for word in words}


def _deadlines(text: str) -> int:
    """How many times "within" sets a time limit rather than a place."""
    # Split rather than _words, which drops digits — and a digit after
    # "within" is the clearest sign of all that a deadline follows.
    words = _plain(text).split()
    found = 0
    for i, word in enumerate(words):
        if word != "within":
            continue
        ahead = words[i + 1:i + 5]
        if any(other in TIME_WORDS or other.isdigit() for other in ahead):
            found += 1
    return found


def _absorbed(before: str, after: str) -> int:
    """How many negations the rewrite folded into a word.

    Only counts a new word whose negated stem is a word the original used, so
    "disagree" for "not agree" counts and nothing else does.
    """
    had = set(_words(before))
    found = 0
    for word in set(_words(after)) - had:
        for prefix in NEGATING_PREFIXES:
            if not word.startswith(prefix):
                continue
            stem = word[len(prefix):].lstrip("-")
            if len(stem) >= 4 and any(_much_the_same(stem, other)
                                      for other in had):
                found += 1
                break
    return found


def _much_the_same(one: str, other: str) -> bool:
    """Two words that differ only by an inflection.

    The bound matters. Allowing any shared prefix read "intelligence" as a
    negated form of "tell" — "in" plus a stem beginning "tell" — and so a
    rewrite that expanded AI to artificial intelligence was refused for
    inventing a negation. Four characters minimum, three of difference at
    most, admits "approved" for "approve" and refuses that.
    """
    if len(other) < 4:
        return False
    if one == other:
        return True
    # Spelled out rather than max/min on len, which both return their first
    # argument when the lengths tie — so every original word of exactly the
    # stem's length matched itself and passed. That read "intelligence" as a
    # negated "government", and refused every rewrite that expanded AI.
    longer, shorter = (one, other) if len(one) >= len(other) else (other, one)
    return longer.startswith(shorter) and len(longer) - len(shorter) <= 3


def _proper_nouns(text: str) -> set[str]:
    """Capitalized words that are not simply sentence openers.

    Role titles and named bodies — "the Permitting Manager", "the AI
    Governance Council" — must survive a rewrite. Words at the start of a
    sentence are excluded because capitalization there says nothing.
    """
    found = set()
    for sentence in re.split(r"(?<=[.!?])\s+", _one_name(text)):
        for i, word in enumerate(sentence.split()):
            bare = word.strip(".,;:()\"'")
            if i and bare[:1].isupper() and len(bare) > 2:
                found.add(bare.lower())
    return found


def check(before: str, after: str, *, defining: bool = False
          ) -> tuple[bool, str]:
    """Is this rewrite of the same text, requiring the same things?

    `defining` for the meaning of a defined term, which is held to a stricter
    rule on obligations: a clause may have its present indicative raised to
    "shall", because that is a change of register and not of duty, but a
    definition that acquires a "shall" has stopped being a definition.

    Every one of these is a thing a tool has actually been observed to do to
    a sentence while "improving" it. The test is deliberately blunt: a
    rejection costs nothing but an unpolished clause, and a false accept
    costs a policy that says something nobody agreed to.
    """
    before = (before or "").strip()
    after = (after or "").strip()

    if not after:
        return False, "the tool returned nothing"
    if after == before:
        return True, "unchanged"

    # Something that is not a clause at all — a preamble, an apology, a list.
    if after.lower().startswith(("here is", "here's", "sure", "certainly",
                                "i have", "i've", "rewritten", "revised",
                                "note:", "clause:")):
        return False, "the tool answered rather than rewriting"
    if "\n-" in after or after.startswith("- "):
        return False, "the tool turned a clause into a list"

    # An unmatched quotation mark. A definition of the levels of scrutiny
    # came back as 'Impact tiers" means the categories by which…', which is a
    # defined-term construction with the front of it missing and a stray
    # quote left sitting in the document. Nothing else caught it — the
    # invented term was at the start of a sentence, where capitalisation says
    # nothing.
    #
    # Unmatched, not merely new: refusing any new quotation mark also refused
    # '"AI tool" means a tool that generates text…', which is how a
    # definitions section is properly written. An odd count is the actual
    # defect and a pair is not.
    if _quotes(after) % 2:
        return False, "the tool left an unmatched quotation mark in the text"

    ratio = _length(after) / max(1, _length(before))
    if ratio < SHORTEST:
        return False, f"lost {round((1 - ratio) * 100)}% of its length"
    if ratio > LONGEST:
        return False, f"grew by {round((ratio - 1) * 100)}%"

    if _numbers(before) != _numbers(after):
        return False, (f"the numbers changed: {_numbers(before)} became "
                       f"{_numbers(after)}")

    # A negation that does not survive inverts the rule, unless it survived
    # inside a word — see NEGATING_PREFIXES.
    was, now = _tally(before, NEGATIONS), _tally(after, NEGATIONS)
    standing = sum(now.values()) + _absorbed(before, after)
    if sum(was.values()) != standing:
        gone = sorted(word for word in NEGATIONS if was[word] > now[word])
        if gone and sum(was.values()) > standing:
            return False, f"a negation was dropped: {', '.join(gone)}"
        return False, (f"the negations changed: {sum(was.values())} in the "
                       f"original, {standing} in the rewrite")

    # Obligations may be raised in register but never lowered in force. See
    # the note on MANDATORY for why this is a direction and not an equality —
    # except in a definition, which is not allowed to acquire a duty at all.
    was, now = _tally(before, MANDATORY), _tally(after, MANDATORY)
    if sum(was.values()) > sum(now.values()):
        lost = sorted(word for word in MANDATORY if was[word] > now[word])
        return False, (f"a duty was weakened: "
                       f"'{', '.join(lost)}' no longer appears")
    if defining and sum(was.values()) < sum(now.values()):
        gained = sorted(word for word in MANDATORY if was[word] < now[word])
        return False, (f"a definition gained a duty: "
                       f"'{', '.join(gained)}' is not in the original")
    for label, group in (("recommendation", ADVISORY),
                         ("permission", PERMISSIVE)):
        was, now = _tally(before, group), _tally(after, group)
        if sum(was.values()) != sum(now.values()):
            moved = sorted(word for word in group if was[word] != now[word])
            return False, (f"a {label} changed: '{', '.join(moved)}' does not "
                           f"appear the same number of times")

    # Scope and timing.
    was, now = _tally(before, CONDITIONS), _tally(after, CONDITIONS)
    for word in CONDITIONS:
        if was[word] != now[word]:
            return False, (f"'{word}' appears {was[word]} time(s) in the "
                           f"original and {now[word]} in the rewrite")
    if _deadlines(before) != _deadlines(after):
        return False, (f"a time limit changed: {_deadlines(before)} deadline"
                       f"(s) in the original, {_deadlines(after)} in the "
                       f"rewrite")

    # How often, which is a requirement with no digits in it.
    was, now = _tally(before, RECURRENCE), _tally(after, RECURRENCE)
    if sum(was.values()) != sum(now.values()):
        return False, (f"how often something happens changed: "
                       f"{sum(was.values())} in the original, "
                       f"{sum(now.values())} in the rewrite")

    # Whether a list is exhaustive.
    was, now = _tally(before, OPEN_ENDED), _tally(after, OPEN_ENDED)
    if sum(was.values()) != sum(now.values()):
        return False, ("a closed list was made open"
                       if sum(now.values()) > sum(was.values())
                       else "an open list was made closed")

    missing = _proper_nouns(before) - _proper_nouns(after)
    if missing:
        return False, f"dropped a name: {', '.join(sorted(missing))}"

    # And a name that was not there before. This is the worst thing observed
    # in a measured pass: a clause about "our information" came back as "the
    # Council's information", naming a body this organization does not have
    # and never mentioned. An invented party in a document somebody signs is
    # not a wording problem.
    # Words the original used are excluded, so that merely capitalising one
    # does not count as inventing it: "a state agency" becoming "a State
    # agency" is a house-style choice, while "our information" becoming "the
    # Council's information" is a body this organization does not have.
    invented = (_proper_nouns(after) - _proper_nouns(before)
                - set(_words(before)))
    if invented:
        return False, f"invented a name: {', '.join(sorted(invented))}"

    # The backstop, and deliberately last: a rewrite sharing almost none of
    # the original's vocabulary is a new sentence rather than an edit of this
    # one. It earns its place by catching a subject substitution nothing else
    # sees — "It comes back for review every year", meaning the framework,
    # came back as "The clause shall be reviewed annually".
    #
    # The threshold is low because raising a clause into a formal register
    # legitimately replaces most of its words: "checked before purchase,
    # before it goes live, and once a year" becoming "verified prior to
    # procurement, prior to deployment, and annually thereafter" keeps three
    # words in twelve and is entirely faithful. Everything load-bearing is
    # checked above by name, so this only has to catch wholesale replacement.
    had = set(_words(_plain(before)))
    kept_words = had & set(_words(_plain(after)))
    if len(had) > 6 and len(kept_words) < 0.25 * len(had):
        return False, "shares too little wording with the original to be an edit"

    return True, ""


# ---------------------------------------------------------------- the pass

def one(provider: Any, clause: str, *, defining: bool = False
        ) -> tuple[str, str, str]:
    """Polish a single clause, or the meaning of a defined term.

    Returns the text to use, why it was not changed if it was not, and what
    the tool actually proposed. The third of those is the interesting one: a
    rejection that cannot be looked at is a rejection nobody can check, and
    both the audit log and my own tuning of the rules above depend on being
    able to read what was refused and decide whether refusing it was right.
    """
    try:
        response = provider.client.messages.create(
            model=getattr(provider, "model", "claude-opus-5"),
            max_tokens=700,
            # Copy-editing one sentence is a simple task, and this runs
            # roughly ninety times per download. Low effort keeps the
            # thinking tokens — which dominate the cost here — proportionate
            # to the job.
            #
            # Effort rather than turning thinking off: with thinking
            # disabled the tool can leak internal tags into the visible
            # answer, and a leaked tag inside a policy clause is exactly the
            # kind of thing that would get past a reader and into a signed
            # document.
            output_config={"effort": "low"},
            # The instruction is stable across every clause, so it is marked
            # cacheable. It was below the 512-token minimum when this was
            # written and the marking did nothing; telling the clause job and
            # the definition job apart pushed both instructions past it, and
            # a measured pass now reads 25,660 cached tokens against 2,180
            # uncached. Cache reads bill at a tenth of the input rate, so
            # that is most of the input cost of a document gone.
            system=[{"type": "text",
                     "text": DEFINING if defining else INSTRUCTION,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": clause}],
        )
    except Exception as exc:                              # noqa: BLE001
        return clause, f"{type(exc).__name__}", ""

    if getattr(response, "stop_reason", None) == "refusal":
        return clause, "the provider declined", ""

    text = "".join(b.text for b in response.content
                   if getattr(b, "type", "") == "text").strip()
    # Tools like to wrap a single returned sentence in quotes.
    text = text.strip('"').strip("'").strip()

    ok, why = check(clause, text, defining=defining)
    if not ok:
        return clause, why, text
    return text, "", text


def _their_sentences(answers: dict[str, Any]) -> list[str]:
    """Text the organization typed, long enough to recognize in a sentence.

    The provenance check below asks whether a question was a typing question.
    This asks whether the words in front of us are words somebody wrote,
    which is the thing actually being protected, and it holds for text that
    reaches the page by a route nobody thought about.
    """
    from app import module_one as m1

    out: list[str] = []
    for step in m1.STEPS:
        for question in step.questions:
            if question.kind not in ("short", "long", "rows"):
                continue
            held = answers.get(question.key) or {}
            value = held.get("value") if isinstance(held, dict) else held
            _collect(value, out)
    return out


def _collect(value: Any, into: list[str]) -> None:
    """Every string in an answer, however it is nested. Grid answers are
    lists of lists, and a cell somebody typed is still their writing."""
    if isinstance(value, (list, tuple)):
        for item in value:
            _collect(item, into)
    elif isinstance(value, dict):
        for item in value.values():
            _collect(item, into)
    else:
        text = str(value or "").strip()
        # Short enough to be a label they clicked rather than prose they
        # wrote, and short strings match by accident.
        if len(text) >= 12:
            into.append(text)


def _fix_spelling(built: list[Any]) -> tuple[int, list[str]]:
    """Correct known misspellings everywhere, including their own sentences.

    The client: "If they use the Polished version, it needs to catch things
    like spelling errors (I inentionally included a spelling error that
    translated over even after the polished version was selected)."

    It did, and the reason is the protection immediately below this function.
    A clause carrying text somebody typed is never sent to the writing tool,
    so the tool never saw the typo and could not have fixed it — twenty-one
    clauses were skipped on that rule in the run that reproduced his report.
    Instructing the tool harder would have changed nothing.

    So this is deterministic and separate. It replaces only the strings in
    `typos.CORRECTIONS`, every one of which is a non-word in every variety of
    English, so it cannot turn one word into a different one. It runs over
    the clauses, the definitions and their own paragraphs alike, and over
    text the tool has already been through as well — the tool is not asked to
    be a spellchecker and should not be trusted as one.

    Why this is allowed to touch their writing when nothing else is:
    choosing Polished is asking for the wording to be cleaned up, a
    misspelling is unambiguously an error rather than a matter of voice, and
    the correction is from a closed list rather than a judgment. The
    as-written text stays in the version history, the document says which
    words were changed, and As Written remains the option for anybody who
    wants their typing left exactly as it is.
    """
    from app import typos

    fixed: list[str] = []

    def mend(text: str) -> str:
        found = typos.found(text)
        if not found:
            return text
        fixed.extend(s["word"] for s in found)
        return typos.corrected(text)

    for section in built:
        for clause in section.clauses:
            clause.text = mend(clause.text)
        for index, (term, meaning) in enumerate(section.terms):
            section.terms[index] = (term, mend(meaning))
        if getattr(section, "own_words", ""):
            section.own_words = mend(section.own_words)
        for table in getattr(section, "tables", []) or []:
            for row in table.get("rows") or []:
                for cell, value in enumerate(row):
                    if isinstance(value, str):
                        row[cell] = mend(value)

    # Deduplicated, first sighting first, so the document can name them.
    seen: list[str] = []
    for word in fixed:
        if word not in seen:
            seen.append(word)
    return len(fixed), seen


def _put_clause(clause: Any):
    def put(text: str) -> None:
        clause.text = text
    return put


def _put_term(section: Any, index: int, term: str):
    """`terms` holds (term, meaning) tuples, so the whole pair is replaced."""
    def put(text: str) -> None:
        section.terms[index] = (term, text)
    return put


def sections(built: list[Any], answers: dict[str, Any]) -> Outcome:
    """Polish every clause and definition of a built framework, in place.

    Takes the sections `prose.sections()` produced and rewrites the text of
    their clauses and of the meanings in the definitions section. Their own
    words — `own_words`, anything the clause map marks as typed rather than
    chosen, and any sentence carrying text they typed — are not sent
    anywhere.

    The definitions are included for a reason worth stating. They are
    assembled from the same answers as the clauses they define, so polishing
    one and not the other left section 3 defining an AI tool as "tools that
    write text… that recognize things in photos" while section 2 required the
    framework to apply to "tools that generate text… that recognize content
    in photographs". A definition that does not match the clause it defines
    is worse than an unpolished one.
    """
    from app import module_one as m1

    outcome = Outcome()

    # Spelling first, and whatever else happens. It needs no provider, no
    # network and no money, so a deployment with no writing tool configured
    # still gets this much of what "Polished" promises — and the document
    # says so rather than reporting that polishing did nothing.
    outcome.spelled, outcome.spelled_words = _fix_spelling(built)

    ok, why = available()
    if not ok:
        outcome.note = why
        return outcome

    from app.provider import AnthropicProvider
    provider = AnthropicProvider()
    outcome.provider = f"{provider.name}:{provider.model}"

    # Which questions they answered in their own prose. Those clauses carry
    # their sentences, and this module does not edit anybody's writing.
    #
    # Keyed by question *number*, because that is what a Clause records —
    # `Clause(filled, question.number)`. Keying it by `question.key` looked
    # right and matched nothing, so every typed answer would have been sent
    # out.
    typed = {question.number for step in m1.STEPS
             for question in step.questions
             if question.kind in ("short", "long", "rows")}
    theirs = _their_sentences(answers)

    def mine(text: str) -> bool:
        """Assembled by this application rather than written by them."""
        return not any(written in text for written in theirs)

    # What is going, gathered first so it can all be sent at once.
    wanted: list[tuple[str, Any, bool]] = []
    for section in built:
        for clause in section.clauses:
            if (clause.source and clause.source in typed) or not mine(
                    clause.text):
                outcome.skipped_their_words += 1
                continue
            wanted.append((clause.text, _put_clause(clause), False))
        for index, (term, meaning) in enumerate(section.terms):
            if not mine(meaning):
                outcome.skipped_their_words += 1
                continue
            wanted.append((meaning, _put_term(section, index, term), True))
    outcome.asked = len(wanted)
    if not wanted:
        return outcome

    # In parallel, because sixty-odd clauses at 2.7 seconds each is three
    # minutes and nobody waits three minutes for a download. Each call is
    # independent — one clause in, one clause out, no shared state — so there
    # is nothing to order and nothing to race.
    with concurrent.futures.ThreadPoolExecutor(max_workers=AT_ONCE) as pool:
        results = list(pool.map(
            lambda job: one(provider, job[0], defining=job[2]), wanted))

    for (before, put, _), (polished, why_not, attempted) in zip(wanted,
                                                                results):
        if polished != before:
            put(polished)
            outcome.changed += 1
        elif why_not and why_not != "unchanged":
            outcome.refused += 1
            # Both texts in full. A rejection nobody can read is a rejection
            # nobody can check, and the checks above were tuned by reading
            # these.
            outcome.rejections.append({"clause": before,
                                       "attempted": attempted,
                                       "why": why_not})
        else:
            outcome.kept += 1

    return outcome
