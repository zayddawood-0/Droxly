"""
tasks/remediation-plan.md R3 test support — builds minimal, real (not
mocked) PDF byte strings in-memory so parser tests exercise pypdf/pdfplumber
against actual valid PDF structure rather than fixture files on disk.
"""

import io

import pypdf


def build_text_pdf(pages_text: list[str]) -> bytes:
    """
    Hand-assembles a minimal, valid single/multi-page PDF with a real
    content stream per page ("BT ... Tj ET") — both pypdf and pdfplumber
    parse this as a normal text-bearing PDF, exercising the real extraction
    path `PdfParser.parse` runs in production.
    """
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + i} 0 R" for i in range(len(pages_text)))
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages_text)} >>".encode()
    )

    # Object numbering scheme: 1=catalog, 2=pages, 3..3+n-1=page objects,
    # 3+n..3+2n-1=content-stream objects, 3+2n=the shared font object.
    font_obj_num = 3 + len(pages_text) * 2
    for i in range(len(pages_text)):
        content_obj_num = 3 + len(pages_text) + i
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 "
            f"{font_obj_num} 0 R >> >> /MediaBox [0 0 612 792] "
            f"/Contents {content_obj_num} 0 R >>".encode()
        )

    for text in pages_text:
        escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        stream = f"BT /F1 24 Tf 100 700 Td ({escaped}) Tj ET".encode()
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    buf = io.BytesIO()
    buf.write(b"%PDF-1.4\n")
    offsets = []
    for idx, obj in enumerate(objects, start=1):
        offsets.append(buf.tell())
        buf.write(f"{idx} 0 obj\n".encode())
        buf.write(obj)
        buf.write(b"\nendobj\n")

    xref_offset = buf.tell()
    n_objs = len(objects) + 1
    buf.write(f"xref\n0 {n_objs}\n".encode())
    buf.write(b"0000000000 65535 f \n")
    for off in offsets:
        buf.write(f"{off:010d} 00000 n \n".encode())
    buf.write(
        f"trailer\n<< /Size {n_objs} /Root 1 0 R >>\nstartxref\n"
        f"{xref_offset}\n%%EOF".encode()
    )
    return buf.getvalue()


def build_blank_pdf(page_count: int = 3) -> bytes:
    """A structurally valid PDF with zero extractable text on any page (the "no text layer" / scanned-image stand-in)."""
    writer = pypdf.PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def build_encrypted_pdf() -> bytes:
    """A structurally valid, password-protected PDF (pypdf.is_encrypted == True at open time, no password needed to detect it)."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="secret", owner_password="ownersecret")
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
