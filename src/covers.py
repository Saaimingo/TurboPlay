"""Armazenamento local e validado de capas da biblioteca PC."""
from __future__ import annotations

import hashlib
import io
import os
import re
import tempfile
import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError

_DEFAULT_CACHE = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "TurboPlay" / "covers"
_GAME_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_MAX_BYTES = 20 * 1024 * 1024
_MAX_EDGE = 8192
_MAX_PIXELS = 8_000_000
_MAX_ANIMATION_PIXELS = 16_000_000
_SUPPORTED_FORMATS = {".png": "PNG", ".gif": "GIF"}
_VALIDATION_CACHE: dict[Path, tuple[int, int, int, bytes, bool]] = {}


def _validated_id(game_id: str) -> str:
    if not isinstance(game_id, str) or not _GAME_ID_RE.fullmatch(game_id):
        raise ValueError("ID de jogo inválido")
    return game_id


def _cache_dir(cache_dir: Path | str | None) -> Path:
    return Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE


def _gif_has_complete_blocks(data: bytes) -> bool:
    """Exige blocos GIF terminados corretamente e trailer no fim do arquivo."""
    if len(data) < 14 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return False
    position = 13
    packed = data[10]
    if packed & 0x80:
        position += 3 * (1 << ((packed & 0x07) + 1))
    saw_image = False

    def skip_sub_blocks(pos: int) -> int | None:
        while pos < len(data):
            size = data[pos]
            pos += 1
            if size == 0:
                return pos
            pos += size
            if pos > len(data):
                return None
        return None

    while position < len(data):
        marker = data[position]
        position += 1
        if marker == 0x3B:
            return saw_image and position == len(data)
        if marker == 0x21:  # extension introducer + label + data sub-blocks
            if position >= len(data):
                return False
            position += 1
            skipped = skip_sub_blocks(position)
            if skipped is None:
                return False
            position = skipped
            continue
        if marker != 0x2C or position + 9 > len(data):
            return False
        descriptor_packed = data[position + 8]
        position += 9
        if descriptor_packed & 0x80:
            position += 3 * (1 << ((descriptor_packed & 0x07) + 1))
        if position >= len(data):
            return False
        minimum_code_size = data[position]
        position += 1
        if not 2 <= minimum_code_size <= 8:
            return False
        skipped = skip_sub_blocks(position)
        if skipped is None:
            return False
        position = skipped
        saw_image = True
    return False


def _validate_image(data: bytes, suffix: str) -> tuple[int, int] | None:
    """Decodifica a imagem inteira; cabeçalho e dimensões, sozinhos, não bastam."""
    expected_format = _SUPPORTED_FORMATS.get(suffix)
    if not expected_format or not data or len(data) > _MAX_BYTES:
        return None
    if expected_format == "GIF" and not _gif_has_complete_blocks(data):
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != expected_format:
                    return None
                width, height = image.size
                if (not width or not height or width > _MAX_EDGE or height > _MAX_EDGE
                        or width * height > _MAX_PIXELS):
                    return None
                image.verify()
            # verify() checa a estrutura; load() força a decodificação real dos pixels.
            with Image.open(io.BytesIO(data)) as image:
                total_pixels = 0
                for frame in range(getattr(image, "n_frames", 1)):
                    image.seek(frame)
                    frame_width, frame_height = image.size
                    total_pixels += frame_width * frame_height
                    if total_pixels > _MAX_ANIMATION_PIXELS:
                        return None
                    image.load()
        return width, height
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None


def fallback_identity(game_id: str, title: str) -> tuple[str, str]:
    """Duas cores estáveis por jogo para a capa genérica local (não oficial)."""
    identity = game_id if isinstance(game_id, str) else str(game_id)
    digest = hashlib.sha256(identity.encode("utf-8", errors="replace")).digest()
    background = f"#{24 + digest[0] // 8:02x}{28 + digest[1] // 8:02x}{38 + digest[2] // 8:02x}"
    accent = f"#{80 + digest[3] // 2:02x}{100 + digest[4] // 2:02x}{120 + digest[5] // 2:02x}"
    return background, accent


def get_cover(game_id: str, cache_dir: Path | str | None = None) -> Path | None:
    """Retorna uma capa local completamente decodificável, se existir."""
    gid = _validated_id(game_id)
    root = _cache_dir(cache_dir)
    for suffix in _SUPPORTED_FORMATS:
        path = root / f"{gid}{suffix}"
        try:
            stat = path.stat()
        except OSError:
            _VALIDATION_CACHE.pop(path, None)
            continue
        signature = (stat.st_size, stat.st_mtime_ns, stat.st_ino)
        try:
            with path.open("rb") as stream:
                data = stream.read(_MAX_BYTES + 1)
        except OSError:
            continue
        digest = hashlib.sha256(data).digest()
        cached = _VALIDATION_CACHE.get(path)
        if cached is not None and cached[:3] == signature and cached[3] == digest:
            if cached[4]:
                return path
            continue
        valid = len(data) <= _MAX_BYTES and bool(_validate_image(data, suffix))
        _VALIDATION_CACHE[path] = (*signature, digest, valid)
        if valid:
            return path
    return None


def set_cover(game_id: str, source: Path | str,
              cache_dir: Path | str | None = None) -> Path:
    """Valida PNG/GIF decodificando-o e copia atomicamente para cache local."""
    gid = _validated_id(game_id)
    src = Path(source)
    suffix = src.suffix.lower()
    if suffix not in _SUPPORTED_FORMATS:
        raise ValueError("Formato não suportado: use PNG ou GIF")
    try:
        with src.open("rb") as stream:
            data = stream.read(_MAX_BYTES + 1)
    except OSError as exc:
        raise ValueError("Arquivo de capa não encontrado ou inacessível") from exc
    if len(data) > _MAX_BYTES:
        raise ValueError("A capa não pode exceder 20 MB")
    if not _validate_image(data, suffix):
        raise ValueError("Imagem inválida, truncada, corrompida ou com dimensões excessivas")

    root = _cache_dir(cache_dir)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{gid}{suffix}"
    fd, temp_name = tempfile.mkstemp(prefix=f".{gid}_", suffix=suffix, dir=root)
    os.close(fd)
    temp = Path(temp_name)
    try:
        temp.write_bytes(data)
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    _VALIDATION_CACHE.pop(target, None)
    other = root / f"{gid}{'.gif' if suffix == '.png' else '.png'}"
    other.unlink(missing_ok=True)
    _VALIDATION_CACHE.pop(other, None)
    return target
