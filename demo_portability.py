"""Portability proof — point the app at a different agency and see it adapt.

Builds a synthetic corpus for an agency that shares nothing with SCDES: a
different state, a different domain (health, not environment), instruments
called "Schedule" numbered 1–5 rather than "Appendix" A–N, checkpoints called
"Stage" rather than "Gate", different roles, different statutory programmes.

Nothing about either agency is in the code. If the profile below comes out
right, the application is genuinely agency-neutral.

Run:  python demo_portability.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from docx import Document
from openpyxl import Workbook

RULE = "─" * 76


def build_corpus(root: Path) -> None:
    for sub in ("framework", "manual", "appendices", "charter", "config"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    # -- the framework ---------------------------------------------------
    doc = Document()
    doc.add_heading("Ohio Department of Health Services "
                    "Artificial Intelligence Governance Framework", 0)
    doc.add_paragraph(
        "This governance framework establishes how the Ohio Department of "
        "Health Services (ODHS) authorises, oversees and retires artificial "
        "intelligence. The framework is adopted by the Director of Health "
        "Services and executed on March 3, 2027.")
    for n, (title, body) in enumerate([
        ("Purpose and Scope",
         "This framework applies to every AI system operated by the Ohio "
         "Department of Health Services."),
        ("Definitions and Authority",
         "The Director of Health Services holds final authority. The Privacy "
         "Officer and the Chief Medical Informatics Officer advise the Board."),
        ("Authorized Use Case Structure",
         "Use cases are grouped into Bucket 1 (internal operations), Bucket 2 "
         "(member-facing services) and Bucket 3 (research). Bucket assignment "
         "determines the review path."),
        ("Oversight Board and Decision Levels",
         "The AI Oversight Board records decisions at Level A (Director "
         "unilateral), Level B (written concurrence) and Level C (convened "
         "session). The Board Chair convenes the Board."),
        ("Risk Management Policy",
         "Projects are classified Minimal Risk, Moderate Risk or Severe Risk "
         "using the weighted matrix in Schedule 2. Programmes subject to HIPAA, "
         "CMS or SNAP delegation carry elevated weight."),
        ("Incident Response",
         "Incidents are graded Level 1 through Level 3. A Level 2 incident "
         "suspends the system and notifies the Board Chair."),
    ], start=1):
        doc.add_heading(f"{n}. {title}", level=1)
        doc.add_paragraph(body)
    doc.save(root / "framework" / "ODHS_AI_Governance_Framework.docx")

    # -- the manual ------------------------------------------------------
    doc = Document()
    doc.add_heading("Ohio Department of Health Services AI Operations Manual", 0)
    doc.add_paragraph(
        "This operations manual carries out the framework. Its operational "
        "tools are organized as Schedules 1 through 5 to this Manual.")
    for n, (title, body) in enumerate([
        ("Relationship to the Framework",
         "This Manual implements Section 1 of the Governance Framework."),
        ("Bucket Assignment Procedure",
         "The Privacy Officer assigns a Bucket at intake per Schedule 1."),
        ("Risk Classification Procedure",
         "Scoring uses Schedule 2. A composite of 6 to 10 with no Severe "
         "factor yields Minimal Risk."),
        ("Stage-Gate Approval Procedure",
         "Projects pass Stage 1 (Concept), Stage 2 (Pilot) and Stage 3 "
         "(Deployment) using the checklists in Schedule 4."),
        ("Incident Response Procedure",
         "A Level 2 incident requires suspension and notification of the "
         "Board Chair within twelve hours."),
    ], start=1):
        doc.add_heading(f"{n}. {title}", level=1)
        doc.add_paragraph(body)
    doc.save(root / "manual" / "ODHS_AI_Operations_Manual.docx")

    # -- the charter -----------------------------------------------------
    doc = Document()
    doc.add_heading("ODHS AI Oversight Board Charter", 0)
    doc.add_paragraph("This charter was executed on March 3, 2027 by the "
                      "Director of Health Services.")
    doc.save(root / "charter" / "ODHS_Board_Charter_SIGNED_2027-03-03.docx")

    # -- the instruments: Schedules 1–5, not Appendices A–N ---------------
    def sheet_header(ws, title: str, subtitle: str = "") -> None:
        ws["A1"] = title
        ws["A2"] = ("Ohio Department of Health Services AI Governance "
                    "Framework, adopted __________, 2027")
        if subtitle:
            ws["A3"] = subtitle

    wb = Workbook(); ws = wb.active; ws.title = "Use Case Catalog"
    sheet_header(ws, "SCHEDULE 1 — AI USE CASE TAXONOMY")
    ws.append([]); ws.append(["ID", "Service Domain", "Use Case Category",
                              "Specific Application", "Bucket (1/2/3)",
                              "Typical Risk Classification", "Data Sources",
                              "Federal Program Nexus"])
    for row in [
        ["MB-001", "Member Services", "Eligibility Screening",
         "Automated benefit eligibility pre-screening", "2", "Moderate",
         "Case records, income data", "CMS / Medicaid"],
        ["PH-001", "Public Health", "Surveillance",
         "Outbreak signal detection from reportable disease feeds", "1",
         "Minimal", "Reportable disease data", "CDC"],
        ["OP-001", "Operations", "Document Processing",
         "Intelligent routing of incoming correspondence", "1", "Minimal",
         "Incoming mail", "None"],
    ]:
        ws.append(row)
    wb.save(root / "appendices" / "Schedule_1_Use_Case_Taxonomy.xlsx")

    wb = Workbook(); ws = wb.active; ws.title = "Risk Scoring Tool"
    sheet_header(ws, "SCHEDULE 2 — AI RISK CLASSIFICATION MATRIX",
                 "Weighted scoring tool for AI project risk classification")
    ws.append([])
    ws.append(["#", "Risk Factor", "Minimal (1)", "Moderate (2)", "Severe (3)",
               "Score (1, 2, or 3)", "Weight", "Weighted Score", "Notes"])
    for i, (name, low, mid, high, weight) in enumerate([
        ("Clinical Impact", "No clinical bearing", "Indirect", "Direct", 2.0),
        ("Member-Facing Exposure", "Internal only", "Limited", "Direct", 1.0),
        ("Protected Health Information", "None", "De-identified", "PHI", 2.0),
        ("Reversibility", "Easily reversed", "Moderate effort", "Difficult", 1.0),
        ("Federal Program Nexus", "None", "Indirect", "Delegated (CMS, SNAP)", 1.5),
    ], start=1):
        ws.append([i, name, low, mid, high, None, weight, None, None])
    ws.append([])
    ws.append([None, "COMPOSITE RESULTS"])
    ws.append([None, "Total Weighted Score", None, None, None, 0, None,
               "Max possible: 22.5"])
    ws.append([])
    ws.append([None, "Classification", "Severe Factor Count", "Approval Required"])
    ws.append([None, "MINIMAL RISK", "6–10", "Zero Severe factors",
               "Division-level approval"])
    ws.append([None, "MODERATE RISK", "11–15", "Any one Severe factor",
               "Board review"])
    ws.append([None, "SEVERE RISK", "16–22.5", "Two or more Severe factors",
               "Board review plus independent review"])
    wb.save(root / "appendices" / "Schedule_2_Risk_Classification_Matrix.xlsx")

    wb = Workbook(); ws = wb.active; ws.title = "Project Intake Form"
    sheet_header(ws, "SCHEDULE 3 — AI PROJECT INTAKE FORM")
    ws.append([])
    ws.append(["PROJECT IDENTIFICATION"])
    for label, hint in [
        ("Project Name", "[Descriptive name for the AI project]"),
        ("Registry ID", "[Assigned by the Office of the Director]"),
        ("Submission Date", ""),
        ("Division / Program", "[Select: Member Services / Public Health / "
                               "Behavioral Health / Operations / Other (specify)]"),
        ("Project Sponsor (Name & Title)", "[Person with authority]"),
        ("Proposed Operational Owner", "[Name and Title]"),
    ]:
        ws.append([label, None, hint])
    wb.save(root / "appendices" / "Schedule_3_Project_Intake_Form.xlsx")

    wb = Workbook()
    for n, (stage, items) in enumerate([
        ("Stage 1 - Concept", ["Problem statement defined",
                               "Bucket identified (Bucket 1, 2, or 3)",
                               "Preliminary risk classification per Schedule 2"]),
        ("Stage 2 - Pilot", ["Pilot scope defined",
                             "Privacy review complete",
                             "Stopping rules agreed"]),
        ("Stage 3 - Deployment", ["Pilot results meet criteria",
                                  "Model documentation complete",
                                  "Board approval recorded"]),
    ]):
        ws = wb.active if n == 0 else wb.create_sheet()
        ws.title = stage
        ws["A1"] = f"STAGE REVIEW CHECKLIST — {stage.split('- ')[1].upper()}"
        ws["A2"] = ("Ohio Department of Health Services AI Governance "
                    "Framework, adopted __________, 2027")
        ws.append([]); ws.append(["PROJECT INFORMATION"])
        ws.append(["Project Name"]); ws.append(["Registry ID"])
        ws.append([]); ws.append(["REQUIREMENTS"])
        ws.append(["#", "Requirement", "Status", "Notes / Evidence"])
        for i, item in enumerate(items, start=1):
            ws.append([i, item, None, None])
    wb.save(root / "appendices" / "Schedule_4_Stage_Review_Checklists.xlsx")

    wb = Workbook(); ws = wb.active; ws.title = "AI Incident Report"
    sheet_header(ws, "SCHEDULE 5 — AI INCIDENT REPORT FORM")
    ws.append([]); ws.append(["INCIDENT IDENTIFICATION"])
    for label in ["Incident Report #", "Date/Time Detected", "Reported By",
                  "AI System Name", "System Risk Classification"]:
        ws.append([label])
    wb.save(root / "appendices" / "Schedule_5_AI_Incident_Report.xlsx")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="odhs-corpus-"))
    try:
        build_corpus(tmp)

        # Point every module at the other agency's corpus.
        from app import audit, ingest_docx, ingest_xlsx, profile
        audit.CORPUS = tmp
        ingest_docx.CORPUS = tmp
        ingest_xlsx.APPENDIX_DIR = tmp / "appendices"
        profile.CORPUS = tmp
        profile.PROFILE_FILE = tmp / "config" / "agency.yaml"
        profile.invalidate()

        p = profile.discover()

        print(f"\n{RULE}\n  SAME APPLICATION, DIFFERENT AGENCY\n{RULE}")
        print(f"  name           : {p.name}")
        print(f"  short          : {p.short_name}")
        print(f"  jurisdiction   : {p.jurisdiction}")
        print(f"  adoption       : {p.adoption_date}")
        print(f"    discovered by: {p.adoption_source[:64]}")

        print(f"\n  instruments    : called '{p.instrument_noun}', "
              f"keys {p.instrument_keys}")
        for k, v in sorted(p.instruments.items()):
            print(f"      {k}: {v['title'][:40]:<42} role={v['role'] or '-'}")

        print(f"\n  checkpoints    : called '{p.gate_noun}', {len(p.gates)} of them")
        for g in p.gates:
            print(f"      {p.gate_noun} {g['key']}: {g['name'][:34]:<36} "
                  f"{g['requirements']} reqs")

        print(f"\n  operating units: {p.org_units}")
        print(f"  roles          : {p.roles[:6]}")
        print(f"  programmes     : {p.statutory_programmes}")

        # The vocabulary layer should follow the corpus, not SCDES habit.
        from app.integrity import observed_vocabulary
        from app.ingest_docx import parse_all as parse_docs
        from app.ingest_xlsx import parse_all as parse_appendices
        text = {d.doc_label: "\n".join(f"{c.heading}\n{c.text}" for c in d.chunks)
                for d in parse_docs()}
        vocab = observed_vocabulary(text, {s.letter: s for s in parse_appendices()})
        print(f"\n  vocabulary derived from this agency's own words:")
        for concept, counts in vocab.items():
            if counts:
                print(f"      {concept:<26} {counts}")

        print(f"\n{RULE}")
        print("  Nothing above was supplied. It was all read out of the corpus.")
        print(f"{RULE}\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
