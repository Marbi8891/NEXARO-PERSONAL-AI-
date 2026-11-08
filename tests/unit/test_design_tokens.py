"""El sistema de diseño debe cumplir WCAG 2.1 AA en claro y oscuro, y no dejar colores sueltos."""

import re
import struct
import zlib
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
TOKENS = (FRONTEND / "css" / "tokens.css").read_text(encoding="utf-8")
LIGHT_DARK = re.compile(
    r"--([a-z0-9-]+):\s*light-dark\(\s*(#[0-9a-f]{6})\s*,\s*(#[0-9a-f]{6})\s*\)"
)
SINGLE = re.compile(r"--([a-z0-9-]+):\s*(#[0-9a-f]{6})\s*;")


def _palette(mode: int) -> dict[str, str]:
    colors = {m.group(1): m.group(2) for m in SINGLE.finditer(TOKENS)}
    colors.update({m.group(1): m.group(2 + mode) for m in LIGHT_DARK.finditer(TOKENS)})
    return colors


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# (primer plano, fondo, mínimo): 4.5 texto normal, 3.0 componentes de interfaz y texto grande.
PAIRS = [
    ("text", "bg", 4.5),
    ("text", "panel", 4.5),
    ("text", "panel-2", 4.5),
    ("muted", "bg", 4.5),
    ("muted", "panel", 4.5),
    ("muted", "panel-2", 4.5),
    ("primary-text", "primary", 4.5),
    ("primary-text", "primary-hover", 4.5),
    ("accent", "panel", 4.5),
    ("accent", "bg", 4.5),
    ("focus", "panel", 3.0),
    ("focus", "bg", 3.0),
    ("border-input", "panel", 3.0),
    ("border-input", "bg", 3.0),
    ("sidebar-text", "sidebar", 4.5),
    ("sidebar-text", "sidebar-active", 4.5),
    ("sidebar-muted", "sidebar", 4.5),
    ("sidebar-muted", "sidebar-active", 4.5),
    ("ok", "ok-bg", 4.5),
    ("ok", "panel", 4.5),
    ("warn", "warn-bg", 4.5),
    ("warn", "panel", 4.5),
    ("danger", "danger-bg", 4.5),
    ("danger", "panel", 4.5),
    ("text", "info-bg", 4.5),
    ("module-personal-ai", "panel", 4.5),
    ("module-finance", "panel", 4.5),
    ("module-business", "panel", 4.5),
    ("module-security", "panel", 4.5),
    ("module-developer", "panel", 4.5),
]


@pytest.mark.parametrize("mode", [0, 1], ids=["claro", "oscuro"])
@pytest.mark.parametrize(("fg", "bg", "minimum"), PAIRS)
def test_contrast_meets_wcag_aa(mode: int, fg: str, bg: str, minimum: float) -> None:
    palette = _palette(mode)
    ratio = contrast(palette[fg], palette[bg])
    assert ratio >= minimum, f"{fg} sobre {bg}: {ratio:.2f} < {minimum}"


def test_components_do_not_hardcode_colors() -> None:
    offenders = []
    for css in sorted((FRONTEND / "css").glob("*.css")):
        if css.name == "tokens.css":
            continue
        for number, line in enumerate(css.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", line):
                offenders.append(f"{css.name}:{number}")
    assert offenders == [], f"colores fuera de tokens.css: {offenders}"


def _png_pixel(path: Path, x: int, y: int) -> tuple[int, ...]:
    data = path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    offset, idat = 8, b""
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        if kind == b"IDAT":
            idat += data[offset + 8 : offset + 8 + length]
        offset += 12 + length
    raw = zlib.decompress(idat)
    stride = 1 + width * 4
    assert len(raw) == height * stride
    start = y * stride + 1 + x * 4
    return tuple(raw[start : start + 4])


def test_pwa_icons_follow_the_symbol() -> None:
    icon = FRONTEND / "icons" / "icon-512.png"
    assert _png_pixel(icon, 0, 0)[3] == 0  # esquina redondeada transparente
    assert _png_pixel(icon, 100, 256) == (0x2B, 0x5C, 0x97, 255)  # fondo acero
    assert _png_pixel(icon, 168, 256) == (255, 255, 255, 255)  # barra izquierda de la N
    maskable = FRONTEND / "icons" / "icon-maskable-512.png"
    assert _png_pixel(maskable, 0, 0) == (
        0x2B,
        0x5C,
        0x97,
        255,
    )  # sin bordes: la plataforma recorta
