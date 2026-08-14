"""Parse an agency's instrument workbooks into editable field schemas.

The instruments are templates, not prose. They share a small number of
repeating block shapes, so one parser produces the schema that Configure renders
as controls, the lifecycle walkthrough renders as a form, and writeback fills by
cell address. Nothing here assumes an agency, a count, or a naming scheme.

Block kinds
-----------
title         leading "APPENDIX X — ..." / framework-reference / INSTRUCTIONS rows
section       an all-caps banner row that opens a new group of fields
field_block   Label: | value | [hint]        (D, E tiers, G, K, L, J stopping rules)
checklist     # | Requirement | Status | Notes / Evidence   (H)
param_table   a table carrying a Weight and/or Score column (B, D scoring, J domains)
record_table  any other real table: header row + data rows (A, C, I, M, J schedule)

Every field records the cell its value is written to, which is what makes
writeback exact rather than positional.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field as dc_field, asdict
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

APPENDIX_DIR = Path(__file__).resolve().parent.parent / "corpus" / "appendices"

# ---------------------------------------------------------------- control types

CONTROL_TEXT = "text"
CONTROL_LONG_TEXT = "long_text"
CONTROL_NUMBER = "number"
CONTROL_SELECT = "select"
CONTROL_DATE = "date"
CONTROL_SLIDER = "slider"

# "[Select: Water / Land and Waste / Air]" and "(Yes / No / Unknown)" both
# enumerate their own options — the templates declare their own control types.
_BRACKET_SELECT = re.compile(r"\[\s*select\s*:\s*(?P<opts>[^\]]+)\]", re.I)
_PAREN_SELECT = re.compile(r"\((?P<opts>[^()]*/[^()]*)\)")
_BRACKET_HINT = re.compile(r"\[(?P<hint>[^\]]+)\]")
_LEADING_NUMBER = re.compile(r"^\s*(\d+[.)]|\d+\.\d+)\s+")
_ROMAN_SECTION = re.compile(r"^[IVXLC]+\.\s+[A-Z]")
_DATE_WORDS = re.compile(r"\b(date|expiration|as of)\b", re.I)

# A banner row rather than a field: SECTION 1: ..., DOMAIN 2: ..., LANE A — ...,
# COMPOSITE RESULTS, I. FEDERAL STATUTES.
_SECTION_PREFIX = re.compile(r"^(section|domain|lane|part|tier|step)\b", re.I)


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _slug(text: str, taken: set[str]) -> str:
    base = _LEADING_NUMBER.sub("", text)
    base = _BRACKET_HINT.sub("", base)
    base = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")[:60] or "field"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    taken.add(key)
    return key


def _is_upperish(text: str) -> bool:
    """True when a row reads as a banner rather than a sentence."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(c.isupper() for c in letters) / len(letters) >= 0.8


def _split_options(raw: str) -> list[str]:
    parts = [p.strip(" .") for p in re.split(r"\s*/\s*|\s{2,}", raw) if p.strip(" .")]
    return [p for p in parts if len(p) <= 60]


def _infer_control(label: str, hint: str, existing: Any) -> tuple[str, list[str], str]:
    """Return (control, options, cleaned_help_text) for one field."""
    blob = f"{label} {hint}"

    m = _BRACKET_SELECT.search(blob)
    if m:
        return CONTROL_SELECT, _split_options(m.group("opts")), _clean_help(hint)

    m = _PAREN_SELECT.search(blob)
    if m:
        opts = _split_options(m.group("opts"))
        if len(opts) >= 2:
            return CONTROL_SELECT, opts, _clean_help(hint)

    if _DATE_WORDS.search(label):
        return CONTROL_DATE, [], _clean_help(hint)

    if isinstance(existing, (int, float)) and not isinstance(existing, bool):
        return CONTROL_NUMBER, [], _clean_help(hint)

    # A numbered prose question ("3. Where is SCDES data hosted?") wants a
    # paragraph, not a one-line input.
    if _LEADING_NUMBER.match(label) or len(label) > 90 or label.rstrip().endswith("?"):
        return CONTROL_LONG_TEXT, [], _clean_help(hint)

    return CONTROL_TEXT, [], _clean_help(hint)


def _clean_help(hint: str) -> str:
    m = _BRACKET_HINT.search(hint)
    return _norm(m.group("hint")) if m else _norm(hint)


# ------------------------------------------------------------------- data model


@dataclass
class Field:
    key: str
    label: str
    control: str
    sheet: str
    value_cell: str
    label_cell: str = ""
    options: list[str] = dc_field(default_factory=list)
    help_text: str = ""
    default: Any = None
    governs: str = ""          # filled in by config.py for tunable parameters
    merged_range: str = ""


@dataclass
class Block:
    kind: str
    sheet: str
    first_row: int
    last_row: int
    title: str = ""
    columns: list[str] = dc_field(default_factory=list)
    header_row: int = 0
    fields: list[Field] = dc_field(default_factory=list)
    sample_rows: list[dict[str, str]] = dc_field(default_factory=list)
    row_count: int = 0


@dataclass
class SheetSchema:
    name: str
    blocks: list[Block] = dc_field(default_factory=list)
    unclassified: list[dict[str, Any]] = dc_field(default_factory=list)

    @property
    def field_count(self) -> int:
        return sum(len(b.fields) for b in self.blocks)


@dataclass
class AppendixSchema:
    letter: str
    title: str
    source_file: str
    sheets: list[SheetSchema] = dc_field(default_factory=list)

    @property
    def field_count(self) -> int:
        return sum(s.field_count for s in self.sheets)

    @property
    def unclassified_count(self) -> int:
        return sum(len(s.unclassified) for s in self.sheets)

    def block_kinds(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for sheet in self.sheets:
            for block in sheet.blocks:
                counts[block.kind] = counts.get(block.kind, 0) + 1
        return counts


# ----------------------------------------------------------------- row analysis


@dataclass
class Row:
    index: int
    cells: list[tuple[int, str, Any]]   # (column index, text, raw value)

    @property
    def filled(self) -> int:
        return len(self.cells)

    @property
    def text(self) -> str:
        return " | ".join(c[1] for c in self.cells)

    def colon_cells(self) -> int:
        return sum(1 for _, t, _ in self.cells if t.endswith(":"))


def _read_rows(ws) -> list[Row]:
    rows: list[Row] = []
    for r_idx, raw in enumerate(ws.iter_rows(), start=1):
        cells = [
            (c.column, _norm(c.value), c.value)
            for c in raw
            if _norm(c.value)
        ]
        rows.append(Row(r_idx, cells))
    return rows


def _merge_lookup(ws) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for rng in ws.merged_cells.ranges:
        lookup[rng.start_cell.coordinate] = str(rng)
    return lookup


def _looks_like_header(row: Row, following: list[Row]) -> bool:
    """A table header has >=3 column labels, and either data beneath it or an
    empty template body (most appendices ship unfilled, so 'no rows' is normal)."""
    if row.filled < 3:
        return False
    if row.colon_cells() >= 2:          # "Bureau/Division: | | Completed By: |" is a field row
        return False
    texts = [t for _, t, _ in row.cells]
    # A column label is never a number or a formula — that marks a computed
    # row such as Appendix B's "Total Weighted Score | =SUM(H7:H12) | Max: 24".
    for _, text, raw in row.cells:
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return False
        if text.startswith("="):
            return False
    # One long column label is fine ("Data Use Restrictions — Can Vendor Use...?"),
    # a row of long labels is prose.
    if any(len(t) > 130 for t in texts):
        return False
    if sum(len(t) for t in texts) / len(texts) > 60:
        return False
    if sum(1 for t in texts if t.endswith(".")) >= 2:
        return False
    if _resumes_table(row, following):
        return True
    # A blank template table: header row with nothing under it yet.
    return all(nxt.filled == 0 for nxt in following[:2])


def _resumes_table(header: Row, following: list[Row], window: int = 4) -> bool:
    """True when a row sharing the header's column footprint appears just below."""
    header_cols = {c for c, _, _ in header.cells}
    for nxt in following[:window]:
        if nxt.filled >= 2 and len(header_cols & {c for c, _, _ in nxt.cells}) >= 2:
            return True
    return False


def _table_kind(columns: list[str]) -> str:
    joined = " ".join(columns).lower()
    if "status" in joined and "requirement" in joined:
        return "checklist"
    if "weight" in joined or re.search(r"\bscore\b", joined):
        return "param_table"
    return "record_table"


#: Title, authority and instruction lines — context, not fields. Matched by
#: shape rather than by agency name: any agency's header block cites its own
#: framework or manual and carries an adoption line.
_META_PREFIX = re.compile(
    r"^(appendix|schedule|attachment|annex|exhibit|instructions?|important|"
    r"framework reference|related|authority|current as of|bluebook|tier \d)",
    re.I
)
_META_CONTAINS = re.compile(
    r"\badopted\b.*\b(19|20)\d{2}\b|\b(governance framework|operations manual|"
    r"policy framework|procedures manual)\b", re.I
)


def _is_section(row: Row) -> bool:
    if row.filled != 1:
        return False
    text = row.cells[0][1]
    if text.endswith(":") or len(text) > 90:
        return False
    if _META_PREFIX.match(text) or _META_CONTAINS.search(text):
        return False                    # a title line, not a banner
    if _SECTION_PREFIX.match(text) or _ROMAN_SECTION.match(text):
        return True
    return _is_upperish(text) and len(text.split()) <= 12


def _is_meta(row: Row, seen_content: bool) -> bool:
    """Title / authority / instruction rows carry context, not fields."""
    if row.filled != 1:
        return False
    text = row.cells[0][1]
    if _META_PREFIX.match(text) or _META_CONTAINS.search(text):
        return True
    return not seen_content and len(text) > 40


# --------------------------------------------------------------------- parsing


def _value_cell(row: Row, label_col: int, ws_merges: dict[str, str],
                max_col: int) -> tuple[str, str]:
    """The cell a field's answer is written into: first cell right of the label."""
    target_col = label_col + 1
    for col, _, _ in row.cells:
        if col > label_col:
            # A hint sits to the right too; the answer cell is the gap before it.
            target_col = label_col + 1 if col > label_col + 1 else col + 1
            break
    target_col = min(max(target_col, label_col + 1), max(max_col, label_col + 1))
    coord = f"{get_column_letter(target_col)}{row.index}"
    return coord, ws_merges.get(coord, "")


def _parse_sheet(ws) -> SheetSchema:
    schema = SheetSchema(name=ws.title)
    rows = _read_rows(ws)
    merges = _merge_lookup(ws)
    max_col = ws.max_column or 2
    taken: set[str] = set()

    current_section = ""
    pending_fields: list[Field] = []
    pending_start = 0
    seen_content = False
    i = 0

    def flush_fields(end_row: int) -> None:
        nonlocal pending_fields, pending_start
        if pending_fields:
            schema.blocks.append(Block(
                kind="field_block", sheet=ws.title, first_row=pending_start,
                last_row=end_row, title=current_section,
                fields=pending_fields, row_count=len(pending_fields),
            ))
            pending_fields = []

    while i < len(rows):
        row = rows[i]

        if row.filled == 0:
            i += 1
            continue

        # --- a real table -------------------------------------------------
        if _looks_like_header(row, rows[i + 1:]):
            flush_fields(row.index - 1)
            columns = [t for _, t, _ in row.cells]
            col_indices = [c for c, _, _ in row.cells]
            header_cols_set = set(col_indices)
            kind = _table_kind(columns)

            # Body rows. A banner *inside* a table ("I. FEDERAL STATUTES",
            # "DIMENSION 2: DATA QUALITY") groups the rows beneath it rather than
            # ending the table, so only stop if the column footprint really ends.
            body: list[tuple[Row, str]] = []
            j = i + 1
            blanks = 0
            group = ""
            while j < len(rows):
                nxt = rows[j]
                if nxt.filled == 0:
                    blanks += 1
                    if blanks >= 3:
                        break
                    j += 1
                    continue
                # Data rows in a uniform table also satisfy "looks like a
                # header" — only a row whose column footprint genuinely differs
                # starts a new table.
                nxt_cols = {c for c, _, _ in nxt.cells}
                # A long checklist repeats its header after each banner; that
                # repeat is not an item.
                if [t for _, t, _ in nxt.cells] == columns:
                    j += 1
                    continue
                shared = len(header_cols_set & nxt_cols)
                if (shared < max(2, len(header_cols_set) // 2)
                        and _looks_like_header(nxt, rows[j + 1:])):
                    break
                if _is_section(nxt):
                    if not _resumes_table(row, rows[j + 1:]):
                        break
                    group = nxt.cells[0][1]
                    blanks = 0
                    j += 1
                    continue
                blanks = 0
                body.append((nxt, group))
                j += 1

            fields: list[Field] = []
            samples: list[dict[str, str]] = []
            for brow, brow_group in body:
                cell_map = {c: (t, v) for c, t, v in brow.cells}
                first_text = cell_map.get(col_indices[0], ("", None))[0]
                row_label = first_text or cell_map.get(col_indices[1], ("", None))[0]
                if not row_label:
                    continue
                sample = {
                    col: cell_map.get(cidx, ("", None))[0]
                    for col, cidx in zip(columns, col_indices)
                }
                if brow_group:
                    sample["_group"] = brow_group
                samples.append(sample)
                if kind in ("checklist", "param_table"):
                    # One editable field per (row, answerable column).
                    for col_name, cidx in zip(columns, col_indices):
                        low = col_name.lower()
                        if low in ("#",) or "requirement" in low or "criterion" in low:
                            continue
                        if kind == "param_table" and low in (
                            "low (1)", "moderate (2)", "high (3)",
                            "measurement method", "target / threshold",
                        ):
                            continue
                        raw = cell_map.get(cidx, ("", None))[1]
                        descriptive = " ".join(
                            cell_map.get(c, ("", None))[0] for c in col_indices
                        )
                        control, options, help_text = _infer_control(
                            col_name, descriptive, raw
                        )
                        if "weight" in low:
                            control, options = CONTROL_SLIDER, []
                        elif re.search(r"\bscore\b", low):
                            control = CONTROL_SELECT
                            options = _score_options(col_name)
                        elif low == "status":
                            control = CONTROL_SELECT
                            options = ["Met", "Not Met", "N/A"]
                        prefix = f"{brow_group} · " if brow_group else ""
                        label = f"{prefix}{row_label} — {col_name}"
                        coord = f"{get_column_letter(cidx)}{brow.index}"
                        fields.append(Field(
                            key=_slug(label, taken), label=label, control=control,
                            sheet=ws.title, value_cell=coord,
                            label_cell=f"{get_column_letter(col_indices[0])}{brow.index}",
                            options=options, help_text=help_text, default=raw,
                            merged_range=merges.get(coord, ""),
                        ))

            schema.blocks.append(Block(
                kind=kind, sheet=ws.title, first_row=row.index,
                last_row=body[-1][0].index if body else row.index,
                title=current_section, columns=columns, header_row=row.index,
                fields=fields, sample_rows=samples[:40], row_count=len(body),
            ))
            seen_content = True
            i = j
            continue

        # --- banner -------------------------------------------------------
        if _is_section(row):
            flush_fields(row.index - 1)
            current_section = row.cells[0][1]
            schema.blocks.append(Block(
                kind="section", sheet=ws.title, first_row=row.index,
                last_row=row.index, title=current_section,
            ))
            seen_content = True
            i += 1
            continue

        # --- title / authority / instruction ------------------------------
        if _is_meta(row, seen_content):
            flush_fields(row.index - 1)
            schema.blocks.append(Block(
                kind="note", sheet=ws.title, first_row=row.index,
                last_row=row.index, title=row.cells[0][1],
            ))
            i += 1
            continue

        # --- field row(s) -------------------------------------------------
        if row.colon_cells() >= 2 and row.filled >= 3:
            # An inline run of label:/value pairs on one row (Appendix I header).
            made = False
            for col, text, _ in row.cells:
                if not text.endswith(":"):
                    continue
                label = text.rstrip(":").strip()
                coord, merged = _value_cell(
                    Row(row.index, [(col, text, None)]), col, merges, max_col
                )
                control, options, help_text = _infer_control(label, "", None)
                if not pending_fields:
                    pending_start = row.index
                pending_fields.append(Field(
                    key=_slug(label, taken), label=label, control=control,
                    sheet=ws.title, value_cell=coord,
                    label_cell=f"{get_column_letter(col)}{row.index}",
                    options=options, help_text=help_text,
                    merged_range=merged,
                ))
                made = True
            if made:
                seen_content = True
                i += 1
                continue

        if row.filled <= 3:
            label_col, label = row.cells[0][0], row.cells[0][1]
            trailing = [(c, t, v) for c, t, v in row.cells[1:]]
            hint = " ".join(t for _, t, _ in trailing)
            existing = trailing[0][2] if trailing else None
            # A bracketed cell is guidance; a bare cell is a pre-filled value.
            if trailing and _BRACKET_HINT.search(trailing[-1][1]):
                existing = trailing[0][2] if len(trailing) > 1 else None

            coord, merged = _value_cell(row, label_col, merges, max_col)
            control, options, help_text = _infer_control(
                label.rstrip(":"), hint, existing
            )
            if not pending_fields:
                pending_start = row.index
            pending_fields.append(Field(
                key=_slug(label, taken), label=label.rstrip(":").strip(),
                control=control, sheet=ws.title, value_cell=coord,
                label_cell=f"{get_column_letter(label_col)}{row.index}",
                options=options, help_text=help_text, default=existing,
                merged_range=merged,
            ))
            seen_content = True
            i += 1
            continue

        schema.unclassified.append({
            "row": row.index, "filled": row.filled, "text": row.text[:160]
        })
        i += 1

    flush_fields(rows[-1].index if rows else 0)
    return schema


def _score_options(col_name: str) -> list[str]:
    m = re.search(r"\(\s*(\d)\s*[-–]\s*(\d)\s*\)", col_name)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return [str(n) for n in range(lo, hi + 1)]
    if "1, 2, or 3" in col_name or "1/2/3" in col_name:
        return ["1", "2", "3"]
    return ["1", "2", "3"]


#: Nouns an agency might use for its instruments. Not every agency issues
#: "Appendices" — Schedules, Attachments, Annexes and Exhibits are all common.
INSTRUMENT_FILE_NOUNS = ["Appendix", "Schedule", "Attachment", "Annex",
                         "Exhibit", "Form", "Tool"]

#: A workbook titles itself with whichever noun its agency uses.
_NOUN_START = re.compile(r"^\s*(?:%s)\b" % "|".join(INSTRUMENT_FILE_NOUNS), re.I)

#: The key may be a letter (A–N) or a number (1–12); do not assume either.
_APPENDIX_FILE = re.compile(
    r"^(?:%s)[ _-](?P<letter>[A-Z0-9]{1,3})[ _-](?P<slug>.+)\.xlsx$"
    % "|".join(INSTRUMENT_FILE_NOUNS), re.I)


def parse_appendix(path: Path) -> AppendixSchema:
    m = _APPENDIX_FILE.search(path.name)
    letter = m.group("letter").upper() if m else path.stem[:1].upper()
    wb = load_workbook(path, data_only=False, read_only=False)
    title = ""
    sheets: list[SheetSchema] = []
    for ws in wb.worksheets:
        sheet_schema = _parse_sheet(ws)
        if not title:
            for block in sheet_schema.blocks:
                if block.kind == "note" and _NOUN_START.match(block.title):
                    title = block.title
                    break
        sheets.append(sheet_schema)
    wb.close()
    if not title and m:
        noun = re.match(r"^(%s)" % "|".join(INSTRUMENT_FILE_NOUNS),
                        path.name, re.I)
        title = (f"{noun.group(1).title() if noun else 'Appendix'} {letter} — "
                 f"{m.group('slug').replace('_', ' ')}")
    return AppendixSchema(
        letter=letter, title=title, source_file=path.name, sheets=sheets
    )


def parse_all(directory: Path | None = None) -> list[AppendixSchema]:
    """Parse every instrument workbook in the corpus.

    `directory` resolves at call time, not at import: the corpus can be
    repointed at another agency while the process is running, and a default
    argument would freeze it to whatever was configured on first import.

    The filename prefix is not assumed either — an agency may issue Schedules
    or Attachments rather than Appendices.
    """
    directory = directory or APPENDIX_DIR
    prefixes = "|".join(INSTRUMENT_FILE_NOUNS)
    pattern = re.compile(rf"^({prefixes})[ _-]", re.I)
    return [parse_appendix(p) for p in sorted(directory.glob("*.xlsx"))
            if pattern.match(p.name) and not p.name.startswith("~$")]


# ---------------------------------------------------------------------- report


def report(schemas: list[AppendixSchema]) -> str:
    lines: list[str] = []
    lines.append("APPENDIX PARSE COVERAGE")
    lines.append("=" * 78)
    header = f"{'App':<4} {'Sheets':>6} {'Fields':>7} {'Uncls':>6}  Block kinds"
    lines.append(header)
    lines.append("-" * 78)
    total_fields = total_uncls = 0
    for s in schemas:
        kinds = ", ".join(
            f"{k}×{v}" for k, v in sorted(s.block_kinds().items())
            if k not in ("note",)
        )
        lines.append(
            f"{s.letter:<4} {len(s.sheets):>6} {s.field_count:>7} "
            f"{s.unclassified_count:>6}  {kinds}"
        )
        total_fields += s.field_count
        total_uncls += s.unclassified_count
    lines.append("-" * 78)
    lines.append(f"{'ALL':<4} {sum(len(s.sheets) for s in schemas):>6} "
                 f"{total_fields:>7} {total_uncls:>6}")
    if total_uncls:
        lines.append("")
        lines.append("UNCLASSIFIED ROWS")
        for s in schemas:
            for sheet in s.sheets:
                for u in sheet.unclassified:
                    lines.append(
                        f"  {s.letter} / {sheet.name} r{u['row']} "
                        f"({u['filled']} cells): {u['text']}"
                    )
    return "\n".join(lines)


def detail(schema: AppendixSchema, limit: int = 14) -> str:
    lines = [f"{schema.title}   [{schema.source_file}]", "=" * 78]
    for sheet in schema.sheets:
        lines.append(f"\n-- SHEET: {sheet.name}  ({sheet.field_count} fields)")
        for block in sheet.blocks:
            if block.kind == "note":
                continue
            head = f"   [{block.kind}] rows {block.first_row}-{block.last_row}"
            if block.title:
                head += f"  · {block.title}"
            lines.append(head)
            if block.columns:
                lines.append(f"       columns: {' | '.join(block.columns)}")
            for f in block.fields[:limit]:
                opts = f" opts={f.options}" if f.options else ""
                help_ = f" — {f.help_text[:50]}" if f.help_text else ""
                lines.append(
                    f"       {f.value_cell:>6}  {f.control:<10} {f.label[:52]}"
                    f"{opts}{help_}"
                )
            if len(block.fields) > limit:
                lines.append(f"       ... {len(block.fields) - limit} more fields")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    schemas = parse_all()
    if not schemas:
        print(f"No appendix workbooks found in {APPENDIX_DIR}", file=sys.stderr)
        return 1

    if "--json" in argv:
        out = APPENDIX_DIR.parent / "index" / "appendix_schemas.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps([asdict(s) for s in schemas], indent=2, default=str),
            encoding="utf-8",
        )
        print(f"wrote {out}")
        return 0

    for arg in argv:
        if len(arg) == 1 and arg.upper() in "ABCDEFGHIJKLMN":
            match = [s for s in schemas if s.letter == arg.upper()]
            if match:
                print(detail(match[0]))
                return 0

    print(report(schemas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
