"""Serve documents that are kept gzipped at rest (see ``services.archive``).

A request for ``name.pdf`` whose file is stored as ``name.pdf.gz`` is answered
with the gzip bytes and ``Content-Encoding: gzip``, which browsers decode
transparently. The rare client that does not accept gzip gets the file
decompressed on the fly.
"""

import gzip
import mimetypes
import os
import stat
from pathlib import Path
from urllib.parse import quote

import anyio.to_thread
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.types import Receive, Scope, Send

from website.services.archive import ARCHIVE_SUFFIX, is_archived, stored_file

_NOT_FOUND = 404
_RANGE_HEADERS = (b"range", b"if-range")


def _accepts_gzip(scope: Scope) -> bool:
    accept = Headers(scope=scope).get("accept-encoding", "")
    return any(
        part.split(";")[0].strip() in ("gzip", "*") for part in accept.split(",")
    )


def _media_type(logical_name: str) -> str:
    return mimetypes.guess_type(logical_name)[0] or "application/octet-stream"


class GzipFileResponse(FileResponse):
    """Stream a ``.gz`` file as a gzip-encoded response of its original type.

    Byte ranges are not offered: they would address the compressed bytes,
    which in-browser PDF viewers do not expect.
    """

    def __init__(
        self,
        path: Path | str,
        media_type: str,
        filename: str | None = None,
        stat_result: os.stat_result | None = None,
    ) -> None:
        """Serve the archive at *path* as *media_type*, optionally as a download."""
        super().__init__(
            path, media_type=media_type, filename=filename, stat_result=stat_result
        )
        del self.headers["accept-ranges"]
        self.headers["content-encoding"] = "gzip"
        self.headers["vary"] = "Accept-Encoding"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Send the whole file, ignoring any Range request."""
        headers = [(k, v) for k, v in scope["headers"] if k not in _RANGE_HEADERS]
        await super().__call__({**scope, "headers": headers}, receive, send)


def _inflated_response(path: Path, media_type: str, filename: str | None) -> Response:
    headers = {"vary": "Accept-Encoding"}
    if filename is not None:
        encoded = quote(filename)
        headers["content-disposition"] = f"attachment; filename*=utf-8''{encoded}"
    return Response(
        gzip.decompress(path.read_bytes()), media_type=media_type, headers=headers
    )


def stored_file_response(
    path: Path, scope: Scope, media_type: str, filename: str | None = None
) -> Response:
    """Return a response for logical *path*, which may be stored gzipped.

    Raises:
        HTTPException: 404 if neither the file nor its archive exists.
    """
    found = stored_file(path)
    if found is None:
        raise HTTPException(status_code=_NOT_FOUND)
    if not is_archived(found):
        return FileResponse(found, media_type=media_type, filename=filename)
    if _accepts_gzip(scope):
        return GzipFileResponse(found, media_type=media_type, filename=filename)
    return _inflated_response(found, media_type, filename)


class StoredFiles(StaticFiles):
    """StaticFiles that also finds files kept as ``<name>.gz`` at rest."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Serve *path*, falling back to its gzipped archive when it is missing."""
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != _NOT_FOUND or path.endswith(ARCHIVE_SUFFIX):
                raise
            full_path, stat_result = await anyio.to_thread.run_sync(
                self.lookup_path, path + ARCHIVE_SUFFIX
            )
            if stat_result is None or not stat.S_ISREG(stat_result.st_mode):
                raise
        media_type = _media_type(path)
        if not _accepts_gzip(scope):
            return await anyio.to_thread.run_sync(
                _inflated_response, Path(full_path), media_type, None
            )
        response = GzipFileResponse(
            full_path, media_type=media_type, stat_result=stat_result
        )
        if self.is_not_modified(response.headers, Headers(scope=scope)):
            return NotModifiedResponse(response.headers)
        return response
