"""A small PDF writer, standard library only.

The project keeps PDF libraries off the server on purpose (see
tools/build_nda_pdf.py: reportlab is a build-time tool, not a runtime
dependency). The framework answers report has to be made on the server, each
day, so this writes the few things it needs directly: letter pages, the two
standard Helvetica faces, word-wrapped paragraphs, headings, gray notes, and
"Page n of N" footers. The document title and language are set, so a screen
reader announces the title rather than a file name.

Text is set in the PDF's WinAnsi (cp1252) encoding, which covers American
English including curly quotes and dashes; anything outside it becomes "?".
"""

from __future__ import annotations

from datetime import datetime, timezone

PAGE_W, PAGE_H = 612, 792            # US letter, in points
MARGIN = 54
BOTTOM = 60

#: Helvetica advance widths (1/1000 em) for printable ASCII, from the
#: standard font metrics. Used to wrap lines so they fit the page.
_W = dict(zip(
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~",
    [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
     556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
     1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
     667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
     333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
     556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]))
_NARROW = {"‘": 222, "’": 222, "“": 333, "”": 333, "–": 556, "—": 1000,
           "•": 350, "·": 278}


def text_width(text: str, size: float, bold: bool = False) -> float:
    units = sum(_W.get(ch, _NARROW.get(ch, 556)) for ch in text)
    return units * size / 1000 * (1.07 if bold else 1.0)


def _wrap(text: str, size: float, width: float, bold: bool) -> list[str]:
    lines: list[str] = []
    for para in str(text).split("\n"):
        words, line = para.split(" "), ""
        for word in words:
            trial = (line + " " + word) if line else word
            if text_width(trial, size, bold) <= width:
                line = trial
                continue
            if line:
                lines.append(line)
            # A single word longer than the line is broken where it must be.
            while text_width(word, size, bold) > width:
                cut = len(word)
                while cut > 1 and text_width(word[:cut], size, bold) > width:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            line = word
        lines.append(line)
    return lines


def _escape(text: str) -> bytes:
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class Document:
    """Lay out text top to bottom, starting new pages as needed."""

    def __init__(self, title: str, footer_note: str = "") -> None:
        self.title = title
        self.footer_note = footer_note
        self.pages: list[list[bytes]] = []
        self.y = 0.0
        self._new_page()

    def _new_page(self) -> None:
        self.pages.append([])
        self.y = PAGE_H - MARGIN

    def space(self, points: float) -> None:
        self.y -= points

    def text(self, text: str, *, size: float = 10, bold: bool = False,
             gray: bool = False, indent: float = 0, before: float = 0,
             keep_with_next: float = 0) -> None:
        """A wrapped paragraph. `keep_with_next` asks for that much room below
        it as well, so a heading is not stranded at the foot of a page."""
        width = PAGE_W - 2 * MARGIN - indent
        lines = _wrap(text, size, width, bold)
        lead = size * 1.38
        self.y -= before
        if self.y - lead * min(len(lines), 2) - keep_with_next < BOTTOM:
            self._new_page()
        font = b"/F2" if bold else b"/F1"
        colour = b"0.38 g" if gray else b"0.07 g"
        for line in lines:
            if self.y - lead < BOTTOM:
                self._new_page()
            self.y -= lead
            self.pages[-1].append(
                b"BT " + colour + b" " + font + b" " + f"{size:g}".encode() + b" Tf "
                + f"{MARGIN + indent:.1f} {self.y:.1f}".encode() + b" Td ("
                + _escape(line) + b") Tj ET")

    def rule(self, before: float = 4, after: float = 8) -> None:
        self.y -= before
        self.pages[-1].append(f"0.8 G 0.5 w {MARGIN} {self.y:.1f} m {PAGE_W - MARGIN} {self.y:.1f} l S"
                              .encode())
        self.y -= after

    def build(self) -> bytes:
        total = len(self.pages)
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        stamp = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")
        title = _escape(self.title)
        catalog = add(b"")                                   # filled in below
        pages_obj = add(b"")
        f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
        info = add(b"<< /Title (" + title + b") /Producer (GoverningAI.US) /CreationDate (" + stamp.encode()
                   + b") >>")
        kids = []
        for n, ops in enumerate(self.pages, start=1):
            footer = f"Page {n} of {total}"
            if self.footer_note:
                footer = f"{self.footer_note}  ·  {footer}"
            ops = ops + [b"BT 0.45 g /F1 8 Tf " + f"{MARGIN} 30".encode() + b" Td ("
                         + _escape(footer) + b") Tj ET"]
            stream = b"\n".join(ops)
            content = add(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream
                          + b"\nendstream")
            kids.append(add(b"<< /Type /Page /Parent " + str(pages_obj).encode() + b" 0 R /MediaBox [0 0 "
                            + f"{PAGE_W} {PAGE_H}".encode() + b"] /Resources << /Font << /F1 "
                            + str(f1).encode() + b" 0 R /F2 " + str(f2).encode() + b" 0 R >> >> /Contents "
                            + str(content).encode() + b" 0 R >>"))
        objects[pages_obj - 1] = (b"<< /Type /Pages /Count " + str(total).encode() + b" /Kids ["
                                  + b" ".join(str(k).encode() + b" 0 R" for k in kids) + b"] >>")
        objects[catalog - 1] = (b"<< /Type /Catalog /Pages " + str(pages_obj).encode()
                                + b" 0 R /Lang (en-US) /ViewerPreferences << /DisplayDocTitle true >> >>")

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
        out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
        out += (f"trailer\n<< /Size {len(objects) + 1} /Root {catalog} 0 R /Info {info} 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode()
        return bytes(out)
