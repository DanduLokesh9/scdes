"""British to American spelling, for everything a person reads.

Run:  python -m tools._americanize [--write] [paths...]

Without --write it reports what it would change. It rewrites prose only:

* Python — only string literals that read as prose (they contain a space, or
  start with a capital letter). A lowercase single-word string is a key, a
  stored option value or an identifier — "finalises", "organisation_type" —
  and renaming one would orphan stored data, so those are never touched.
  Comments are left as they are.
* JavaScript, HTML — whole words, outside identifiers (a word joined to
  another by "_" or camel case is not matched), with property names and
  attribute names skipped.

`BRITISH` is also what tests/test_american_spelling.py checks against, so a
British spelling reintroduced later fails the suite.
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from pathlib import Path

# ---------------------------------------------------------------- the words

_IZE_ROOTS = (
    "organ", "recogn", "real", "prior", "summar", "final", "author", "minim",
    "maxim", "standard", "categor", "character", "emphas", "special", "util",
    "critic", "apolog", "custom", "optim", "normal", "personal", "central",
    "digit", "visual", "sanit", "synchron", "memor", "penal", "legitim",
    "capital", "public", "scrutin", "item", "jeopard", "formal", "familiar",
    "harmon", "stabil", "theor", "local", "mobil", "monet", "anonym", "modern",
    "general", "initial", "legal", "neutral", "rational", "subsid", "symbol",
    "civil", "global", "human", "industrial", "institutional", "internal",
    "marginal", "material", "operational", "patron", "polar", "rand",
    "revolution", "sensit", "social", "special", "stigmat", "sympath",
    "trivial", "vandal", "vapor", "hospital", "incentiv", "democrat",
    "commercial", "conceptual", "contextual", "decentral", "desensit",
    "hypothes", "immun", "ironic", "journal", "liberal", "maxim", "mesmer",
    "metabol", "motor", "national", "privat", "professional", "radical",
    "regular", "rubber", "scandal", "serial", "strateg", "templat", "terror",
    "tokenis", "urban", "victim", "westernis", "fertil", "fossil", "galvan",
    "glamor", "idol", "individual", "italic", "jargon", "lion", "magnet",
    "moral", "naturalis", "orient", "oxid", "pasteur", "plagiar", "popular",
    "pressur", "proselyt", "publici", "real", "recogn", "reorgan", "revital",
    "romantic", "satir", "secular", "sermon", "signal", "solemn", "steril",
    "subsidi", "summar", "temporar", "tranquil", "tyrann", "unrecogn",
    "unorgan", "unauthor", "reauthor", "deprior", "reprior", "demoral",
    "desensitis", "decriminal", "criminal", "computer", "container",
    "digital", "energ", "equal", "evangel", "extern", "fantas", "feminis",
    "harmon", "homogen", "intellectual", "internation", "legitim", "linear",
    "miniatur", "optimis", "overemphas", "particular", "philosoph",
    "politic", "prioritis", "rational", "recapital", "reconceptual",
    "relativ", "securit", "sensation", "specialis", "subdivid", "trauma",
    "virtual", "vocal", "synthes", "emphas", "apologi", "recognis",
    "character", "sympath", "authoris", "organis", "real", "util",
    "annual", "notar", "raster",
)
_IZE_ENDINGS = {"ise": "ize", "ises": "izes", "ised": "ized", "ising": "izing",
                "isation": "ization", "isations": "izations",
                "isational": "izational", "isationally": "izationally",
                "iser": "izer",
                "isers": "izers", "isable": "izable"}

_SIMPLE = {
    # -our
    "colour": "color", "colours": "colors", "coloured": "colored",
    "behaviour": "behavior", "behaviours": "behaviors",
    "behavioural": "behavioral", "favour": "favor", "favours": "favors",
    "favourite": "favorite", "favourable": "favorable", "honour": "honor",
    "honours": "honors", "honoured": "honored", "labour": "labor",
    "neighbour": "neighbor", "neighbours": "neighbors",
    "neighbouring": "neighboring", "rumour": "rumor", "humour": "humor",
    "harbour": "harbor", "endeavour": "endeavor", "vigour": "vigor",
    "flavour": "flavor", "armour": "armor", "odour": "odor", "valour": "valor",
    # -re
    "centre": "center", "centres": "centers", "centred": "centered",
    "metre": "meter", "metres": "meters", "theatre": "theater",
    "fibre": "fiber", "calibre": "caliber",
    # -ll-
    "labelled": "labeled", "labelling": "labeling", "modelled": "modeled",
    "modelling": "modeling", "travelled": "traveled",
    "travelling": "traveling", "traveller": "traveler",
    "cancelled": "canceled", "cancelling": "canceling",
    "counselled": "counseled", "fuelled": "fueled", "levelled": "leveled",
    "signalled": "signaled", "totalled": "totaled", "totalling": "totaling",
    "channelled": "channeled", "enrolment": "enrollment",
    "enrolments": "enrollments", "fulfil": "fulfill", "fulfils": "fulfills",
    "fulfilment": "fulfillment", "instalment": "installment",
    "instalments": "installments", "skilful": "skillful", "wilful": "willful",
    "marvellous": "marvelous", "jewellery": "jewelry",
    # -ence
    "licence": "license", "licences": "licenses", "defence": "defense",
    "offence": "offense", "offences": "offenses", "pretence": "pretense",
    # -yse
    "analyse": "analyze", "analysed": "analyzed", "analyses_v": "analyzes",
    "analysing": "analyzing", "paralyse": "paralyze", "catalyse": "catalyze",
    # the rest
    "programme": "program", "programmes": "programs",
    "catalogue": "catalog", "catalogues": "catalogs",
    "catalogued": "cataloged", "judgement": "judgment",
    "judgements": "judgments", "acknowledgement": "acknowledgment",
    "acknowledgements": "acknowledgments", "ageing": "aging",
    "grey": "gray", "whilst": "while", "amongst": "among",
    "practise": "practice", "practised": "practiced",
    "sceptical": "skeptical", "manoeuvre": "maneuver", "mould": "mold",
    "learnt": "learned", "spelt": "spelled", "cheque": "check",
    "tyre": "tire", "storey": "story", "plough": "plow",
    "draught": "draft", "aeroplane": "airplane", "oestrogen": "estrogen",
    "paediatric": "pediatric", "orthopaedic": "orthopedic",
    "encyclopaedia": "encyclopedia", "towards": "toward",
    "afterwards": "afterward", "focussed": "focused",
    "focussing": "focusing", "benefitted": "benefited",
}


def _build() -> dict[str, str]:
    words = dict(_SIMPLE)
    words.pop("analyses_v")          # "analyses" is also the plural noun
    for root in set(_IZE_ROOTS):
        if root.endswith(("is", "si")) and not root.endswith("is"):
            continue
        base = root[:-2] if root.endswith("is") else root
        for brit, amer in _IZE_ENDINGS.items():
            words[base + brit] = base + amer
    return words


BRITISH: dict[str, str] = _build()
# Words where the -ise form is also correct American English, or a real
# different word, and must never be rewritten.
for keep in ("revise", "advise", "comprise", "exercise", "expertise",
             "franchise", "promise", "premise", "surprise", "supervise",
             "televise", "compromise", "enterprise", "otherwise", "disguise",
             "devise", "despise", "improvise", "chastise", "concise",
             "precise", "raise", "praise", "noise", "cruise", "wise", "rise",
             "arise", "demise", "excise", "merchandise", "treatise",
             "paradise", "advertise", "premises", "itemiser"):
    BRITISH.pop(keep, None)

_WORD = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]+(?![A-Za-z0-9_])")


def _cased(original: str, american: str) -> str:
    if original.isupper() and len(original) > 1:
        return american.upper()
    if original[0].isupper():
        return american[0].upper() + american[1:]
    return american


def convert(text: str) -> str:
    def one(m: re.Match) -> str:
        w = m.group(0)
        amer = BRITISH.get(w.lower())
        return _cased(w, amer) if amer else w
    return _WORD.sub(one, text)


def british_words(text: str) -> list[str]:
    return [m.group(0) for m in _WORD.finditer(text)
            if m.group(0).lower() in BRITISH]


# ---------------------------------------------------------------- Python

def _is_prose(token_text: str) -> bool:
    body = token_text.lstrip("rRbBuUfF").strip("'\"")
    return bool(re.search(r"\s", body)) or bool(body[:1].isupper())


def python_prose(source: str):
    """(absolute start, absolute end, text) of every prose string token."""
    lines = source.split("\n")
    offsets, total = [], 0
    for line in lines:
        offsets.append(total)
        total += len(line) + 1
    kinds = {tokenize.STRING}
    for name in ("FSTRING_MIDDLE", "TSTRING_MIDDLE"):
        if hasattr(tokenize, name):
            kinds.add(getattr(tokenize, name))
    reader = io.StringIO(source).readline
    for tok in tokenize.generate_tokens(reader):
        if tok.type not in kinds:
            continue
        if tok.type == tokenize.STRING and not _is_prose(tok.string):
            continue
        if tok.type != tokenize.STRING and not (
                re.search(r"\s", tok.string) or tok.string[:1].isupper()):
            continue
        start = offsets[tok.start[0] - 1] + tok.start[1]
        end = offsets[tok.end[0] - 1] + tok.end[1]
        yield start, end, source[start:end]


def convert_python(source: str) -> str:
    out, last = [], 0
    for start, end, text in python_prose(source):
        out.append(source[last:start])
        out.append(convert(text))
        last = end
    out.append(source[last:])
    return "".join(out)


# ---------------------------------------------------------------- JS / HTML

#: A word used as a property, an attribute or a CSS class is code, not prose.
#: A hyphen alone is not: "cross-utilisation" is prose. Only a hyphen after
#: a code-ish prefix (`data-`, `aria-`, a CSS class stem) is.
_CODE_CONTEXT = re.compile(r"(?:[.#]|(?:data|aria|ig|pj|dh|vr|ck|in|ov|rg|pr|bg|vs|au|vn|st|ed|ro|pb|pt|tl|bc|bl|gr|sn|cv|cw|hv|hw|hc)-)$")


def convert_markup(source: str) -> str:
    def one(m: re.Match) -> str:
        w = m.group(0)
        amer = BRITISH.get(w.lower())
        if not amer:
            return w
        before = source[max(0, m.start() - 6):m.start()]
        after = source[m.end():m.end() + 1]
        # A property (`.colour`), an attribute or class (`data-colour`,
        # `#colour`), an object key (`colour:`), an assignment, or a lone
        # quoted word (`"organisation"`, a stored value) is code.
        if _CODE_CONTEXT.search(before):
            return w
        if after in (":", "=") and w[0].islower():
            return w
        if before[-1:] in ("'", '"', "`") and after == before[-1:]:
            return w
        return _cased(w, amer)
    return _WORD.sub(one, source)


# ---------------------------------------------------------------- driver

SKIP = {
    # Quotes a reference agency's own documents verbatim.
    "discretion.py",
    # This file lists the British spellings on purpose.
    "_americanize.py", "test_american_spelling.py",
    # Explains that British spellings are real words and are never flagged
    # as typos in what a person types; converting it would garble that.
    "typos.py", "test_typos.py",
}


def run(paths: list[Path], write: bool) -> int:
    changed = 0
    for path in paths:
        if path.name in SKIP or "speech" in path.parts or \
                path.name.endswith(".min.js"):
            continue
        raw = path.read_bytes().decode("utf-8")
        new = (convert_python(raw) if path.suffix == ".py"
               else convert_markup(raw))
        if new != raw:
            changed += 1
            diff = sum(1 for a, b in zip(british_words(raw),
                                         british_words(new)) if a != b)
            print(f"{path}: {len(british_words(raw)) - len(british_words(new))} words")
            if write:
                path.write_bytes(new.encode("utf-8"))
    return changed


if __name__ == "__main__":
    args = sys.argv[1:]
    write = "--write" in args
    targets = [Path(a) for a in args if a != "--write"]
    files: list[Path] = []
    for t in targets:
        if t.is_dir():
            files += [p for p in t.rglob("*") if p.suffix in (".py", ".js", ".html")]
        else:
            files.append(t)
    print(f"{run(files, write)} files {'changed' if write else 'would change'}")
