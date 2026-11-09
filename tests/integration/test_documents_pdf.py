"""Subida de PDF: extracción de texto, rechazos claros y los permisos de los demás documentos."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from nexaro_core.database import Database
from products.personal_ai import pdf
from tests.conftest import ORIGIN, audit_actions

HEADERS = {"Origin": ORIGIN, "Content-Type": "application/pdf"}
Factory = Callable[..., TestClient]


def make_pdf(pages: list[str]) -> bytes:
    """PDF válido mínimo (Helvetica, una línea de texto por página), con tabla xref correcta."""
    objects: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    font_id = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        content_id = 4 + 2 * i
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
        )
        stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return out


def setup_org(logged_in: Factory) -> tuple[TestClient, str]:
    admin = logged_in("owner@example.com", role="admin")
    org = admin.post(
        "/api/organizations",
        json={"name": "acme", "slug": "acme"},
        headers={"Origin": ORIGIN},
    )
    return admin, str(org.json()["id"])


def post_pdf(
    client: TestClient, org: str, data: bytes, title: str = "Contrato", headers: dict | None = None
):
    return client.post(
        f"/api/organizations/{org}/documents/pdf",
        params={"title": title, "source": "contrato.pdf"},
        content=data,
        headers=headers or HEADERS,
    )


def test_extract_text_joins_pages() -> None:
    text = pdf.extract_text(
        make_pdf(["La fianza son dos mensualidades", "Preaviso de treinta dias"])
    )
    assert "dos mensualidades" in text and "treinta dias" in text


def test_pdf_upload_creates_a_searchable_document_with_audit(
    logged_in: Factory, database: Database
) -> None:
    admin, org = setup_org(logged_in)

    response = post_pdf(admin, org, make_pdf(["La fianza son dos mensualidades"]))

    assert response.status_code == 201, response.text
    listed = admin.get(f"/api/organizations/{org}/documents").json()["documents"]
    assert listed[0]["title"] == "Contrato" and listed[0]["source"] == "contrato.pdf"
    found = admin.get(f"/api/organizations/{org}/documents/search", params={"q": "fianza"}).json()
    assert found["results"][0]["title"] == "Contrato"
    assert "document.create" in audit_actions(database)


@pytest.mark.parametrize(
    ("data", "status", "fragment"),
    [
        (b"esto no es un pdf", 422, "no es un PDF"),
        (b"%PDF-1.4\nbasura sin estructura", 422, "No se ha podido leer"),
        (make_pdf([""]), 422, "no contiene texto"),
    ],
)
def test_invalid_or_textless_pdfs_are_rejected_with_a_clear_message(
    logged_in: Factory, data: bytes, status: int, fragment: str
) -> None:
    admin, org = setup_org(logged_in)

    response = post_pdf(admin, org, data)

    assert response.status_code == status
    assert fragment in response.json()["detail"]
    assert admin.get(f"/api/organizations/{org}/documents").json()["documents"] == []


def test_too_many_pages_and_too_much_text_are_rejected(
    logged_in: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin, org = setup_org(logged_in)
    monkeypatch.setattr(pdf, "MAX_PAGES", 2)
    assert post_pdf(admin, org, make_pdf(["a", "b", "c"])).status_code == 413
    monkeypatch.setattr(pdf, "MAX_CHARS", 10)
    response = post_pdf(admin, org, make_pdf(["texto bastante largo para el limite"]))
    assert response.status_code == 413


def test_wrong_content_type_and_empty_title_are_rejected(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    data = make_pdf(["hola"])
    assert post_pdf(admin, org, data, headers={"Origin": ORIGIN}).status_code == 415
    assert post_pdf(admin, org, data, title="   ").status_code == 422


def test_duplicate_pdf_content_is_rejected(logged_in: Factory) -> None:
    admin, org = setup_org(logged_in)
    data = make_pdf(["mismo contenido"])
    assert post_pdf(admin, org, data).status_code == 201
    assert post_pdf(admin, org, data, title="Otro").status_code == 409


def test_pdf_upload_needs_write_permission_membership_and_origin(
    logged_in: Factory, add_user: Callable
) -> None:
    admin, org = setup_org(logged_in)
    add_user("v@example.com")
    admin.post(
        f"/api/organizations/{org}/members",
        json={"email": "v@example.com", "role": "viewer"},
        headers={"Origin": ORIGIN},
    )
    viewer = TestClient(admin.app)
    viewer.post(
        "/api/auth/login",
        json={"email": "v@example.com", "password": "correct-horse-battery"},
        headers={"Origin": ORIGIN},
    )
    outsider = logged_in("out@example.com")
    data = make_pdf(["hola"])

    assert post_pdf(viewer, org, data).status_code == 403
    assert post_pdf(outsider, org, data).status_code == 404
    assert (
        post_pdf(admin, org, data, headers={"Content-Type": "application/pdf"}).status_code == 403
    )
