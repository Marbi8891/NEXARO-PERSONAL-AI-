"""Texto de un PDF para el módulo de documentos (ADR-0018).

Solo PDF con texto: un PDF escaneado (imágenes) no tiene nada que extraer y se rechaza con un error
claro; no hay OCR. `pypdf` es Python puro: se acota el tamaño, las páginas y el texto acumulado, y
cualquier fallo del analizador con un archivo malformado se trata como «PDF no válido».
"""

import io

from pypdf import PdfReader

from products.personal_ai.documents import MAX_CHARS, DocumentError, DocumentTooLargeError

MAX_PAGES = 300
_MAGIC = b"%PDF-"


class InvalidPdfError(DocumentError):
    pass


class EncryptedPdfError(DocumentError):
    pass


class NoTextError(DocumentError):
    pass


class TooManyPagesError(DocumentError):
    pass


def extract_text(data: bytes) -> str:
    """Texto de todas las páginas, separadas por una línea en blanco. Bloqueante: llamar desde un
    hilo."""
    if not data.lstrip()[:1024].startswith(_MAGIC):
        raise InvalidPdfError("El archivo no es un PDF válido")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise EncryptedPdfError("El PDF está protegido con contraseña")
        if len(reader.pages) > MAX_PAGES:
            raise TooManyPagesError(f"El PDF supera las {MAX_PAGES} páginas")
        pages: list[str] = []
        total = 0
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(text)
                total += len(text)
                if total > MAX_CHARS:  # corta antes de procesar el resto del archivo
                    raise DocumentTooLargeError(
                        f"El texto del PDF supera los {MAX_CHARS} caracteres"
                    )
    except DocumentError:
        raise
    except Exception as exc:  # pypdf lanza tipos muy variados ante archivos malformados
        raise InvalidPdfError("No se ha podido leer el PDF") from exc
    if not pages:
        raise NoTextError("El PDF no contiene texto (¿es un escaneado?). No hay OCR")
    return "\n\n".join(pages)
