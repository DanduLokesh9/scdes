"""M1 demo — the spine.

Shows the three things M1 had to prove:
  1. one parser reads all fourteen appendices into editable field schemas
  2. the narrative documents chunk into exactly-citable sections
  3. no governed change happens outside the guard, and the record is tamper-evident

Run:  python demo_m1.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app import mode as mode_mod
from app.audit import JsonlAuditLog
from app.authz import CHAT_ACTOR, Actor, Role, Target, guard
from app.ingest_docx import parse_all as parse_docs
from app.ingest_xlsx import parse_all as parse_appendices, report

RULE = "─" * 74


def head(title: str) -> None:
    print(f"\n{RULE}\n  {title}\n{RULE}")


def main() -> None:
    head("1 · THE APPENDICES PARSE AS STRUCTURED DATA")
    schemas = parse_appendices()
    print(report(schemas))

    head("2 · THE ADOPTED RISK MODEL, READ FROM APPENDIX B")
    b = next(s for s in schemas if s.letter == "B")
    block = next(bl for sh in b.sheets for bl in sh.blocks if bl.kind == "param_table")
    print("  Six weighted factors — these values come out of the workbook, not the code:\n")
    for row in block.sample_rows:
        if row.get("Risk Factor") and row.get("Weight"):
            print(f"     {row['Risk Factor']:<24} weight ×{row['Weight']}")
    print("\n  Bands:")
    for row in block.sample_rows:
        first = (row.get("#") or "").strip()
        if first.endswith("RISK"):
            detail = " · ".join(v for k, v in row.items()
                                if v and k not in ("#", "_group"))[:88]
            print(f"     {first:<16} {detail}")

    head("3 · A FORM FIELD KNOWS THE CELL IT WRITES BACK TO")
    g = next(s for s in schemas if s.letter == "G")
    fields = [f for sh in g.sheets for bl in sh.blocks for f in bl.fields]
    print(f"  Appendix G — Project Intake: {len(fields)} fields\n")
    for f in fields[:6]:
        opts = f"  options={f.options[:4]}" if f.options else ""
        print(f"     {f.value_cell:>5}  {f.control:<10} {f.label[:44]:<46}{opts}")
    picker = next((f for f in fields if f.options and "bureau" in f.label.lower()), None)
    if picker:
        print(f"\n  The template declares its own control type — {picker.label}:")
        print(f"     select → {picker.options}")

    head("4 · EVERY ANSWER CAN CITE ITS EXACT SECTION")
    docs = parse_docs()
    manual = next(d for d in docs if d.doc_label == "SCDES AI Operations Manual")
    for section in ("6.2", "22.4", "15"):
        chunk = next((c for c in manual.chunks if c.section == section), None)
        if chunk:
            print(f"     {chunk.citation}")
            print(f"        {chunk.text[:150].strip()}...\n")

    head("5 · THE GUARD — CHAT AND OPERATORS CHANGE NOTHING GOVERNED")
    with tempfile.TemporaryDirectory() as tmp:
        log = JsonlAuditLog(Path(tmp) / "log.jsonl")
        mode_mod.MODE_FILE = Path(tmp) / "mode.json"
        mode_mod.save(mode_mod.ModeRecord())

        operator = Actor("liz.operator", "Liz (Water Bureau)", Role.OPERATOR)
        ot = Actor("sean.ot", "Sean (OT)", Role.OT)
        council = Actor("council.a", "Council Member A", Role.COUNCIL)

        attempts = [
            (CHAT_ACTOR, Target.CONFIG, "edit_risk_weight"),
            (operator, Target.CONFIG, "edit_risk_weight"),
            (operator, Target.FRAMEWORK, "amend"),
            (ot, Target.CONFIG, "edit_risk_weight"),
            (ot, Target.FRAMEWORK, "amend"),
            (council, Target.FRAMEWORK, "amend"),
        ]
        print(f"  Mode: {mode_mod.current().label}\n")
        for actor, target, action in attempts:
            d = guard(actor, target, action, audit=log)
            mark = "ALLOW " if d.allowed else "REFUSE"
            print(f"     [{mark}] {actor.name:<24} {action} → {target.value}")
            print(f"              {d.reason}")

        head("6 · THE COUNCIL CLOSES THE GATE, AND OT LOSES THE FREE HAND")
        mode_mod.adopt_operating(
            members=["council.a", "council.b", "council.c"],
            parameter_set_hash="p-set-7c2e10",
            summary="Tuned parameter set adopted; guardrails activated.",
            audit=log, actor="council.a",
        )
        print(f"  Mode: {mode_mod.current().label}\n")
        d = guard(ot, Target.CONFIG, "edit_risk_weight", audit=log)
        print(f"     [{'ALLOW ' if d.allowed else 'REFUSE'}] {ot.name:<24} "
              f"edit_risk_weight → config")
        print(f"              {d.reason}")
        print(f"              routes to Council: {d.requires_council}")

        head("7 · THE RECORD IS TAMPER-EVIDENT")
        ok, message = log.verify()
        print(f"  {len(log.entries())} entries — grants and refusals alike")
        print(f"  verify(): {message}")

        rows = log.path.read_text(encoding="utf-8").splitlines()
        rows[1] = rows[1].replace('"denied"', '"allowed"')
        log.path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        ok, message = log.verify()
        print(f"\n  After quietly flipping one refusal to a grant:")
        print(f"  verify(): {message}")

    print()


if __name__ == "__main__":
    main()
