"""Convert FastAPI uploads into the framework-free :class:`UploadedFile`."""

from fastapi import UploadFile

from website.services.uploads import FileStore, UploadedFile


async def read_upload(file: UploadFile, store: FileStore) -> UploadedFile:
    """Read at most one byte more than *store* accepts, so oversize is detectable."""
    data = await file.read(store.policy.max_bytes + 1)
    return UploadedFile(
        filename=file.filename, content_type=file.content_type, data=data
    )
