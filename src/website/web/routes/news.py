"""News posts and rich-text image uploads."""

from typing import Annotated

from fastapi import APIRouter, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi_permissions import has_permission

from website.models.forms import PostForm
from website.web.csrf import CsrfProtected
from website.web.deps import (
    CurrentUserDep,
    PostDeleter,
    PostEditor,
    Posts,
    RendererDep,
    UploadStoreDep,
)
from website.web.identity import get_active_principals
from website.web.security import PostResource, RequirePostAuthor, RequireUploader
from website.web.uploads import read_upload

router = APIRouter()
_PAGE = "news"
_FORM = "post_form.html"


@router.get("/news", response_class=HTMLResponse)
def news(
    request: Request, posts: Posts, ui: RendererDep, page: int = 1
) -> HTMLResponse:
    """Show a page of news posts."""
    return ui.page(
        request, "news.html", _PAGE, paginated=posts.page(page), base_url="/news"
    )


@router.get("/news/create", response_class=HTMLResponse)
def news_create_form(
    request: Request, _: RequirePostAuthor, ui: RendererDep
) -> HTMLResponse:
    """Staff: show the new post form."""
    return ui.page(request, _FORM, _PAGE, post=None, form_action="/news/create")


@router.post("/news/create", response_class=HTMLResponse)
def news_create_submit(
    form: Annotated[PostForm, Form()],
    _: RequirePostAuthor,
    _csrf: CsrfProtected,
    user: CurrentUserDep,
    posts: Posts,
) -> RedirectResponse:
    """Staff: publish a post."""
    assert user is not None  # noqa: S101 — guaranteed by the permission check  # nosec B101
    posts.create(form, author_id=user.id)
    return RedirectResponse(url="/news", status_code=302)


@router.get("/news/{post_id}", response_class=HTMLResponse)
def news_detail(
    post_id: int, request: Request, posts: Posts, ui: RendererDep
) -> HTMLResponse:
    """Show a single post."""
    post = posts.get(post_id)
    can_edit = has_permission(
        get_active_principals(request), "edit", PostResource(post)
    )
    return ui.page(request, "post_detail.html", _PAGE, post=post, can_edit=can_edit)


@router.get("/news/{post_id}/edit", response_class=HTMLResponse)
def news_edit_form(
    request: Request, resource: PostEditor, ui: RendererDep
) -> HTMLResponse:
    """Author or admin: show the edit form."""
    post = resource.post
    return ui.page(
        request, _FORM, _PAGE, post=post, form_action=f"/news/{post.id}/edit"
    )


@router.post("/news/{post_id}/edit", response_class=HTMLResponse)
def news_edit_submit(
    form: Annotated[PostForm, Form()],
    resource: PostEditor,
    _csrf: CsrfProtected,
    posts: Posts,
) -> RedirectResponse:
    """Author or admin: save a post."""
    posts.update(resource.post.id, form)
    return RedirectResponse(url=f"/news/{resource.post.id}", status_code=302)


@router.post("/news/{post_id}/delete")
def news_delete(
    resource: PostDeleter, _csrf: CsrfProtected, posts: Posts
) -> RedirectResponse:
    """Author or admin: delete a post."""
    posts.delete(resource.post.id)
    return RedirectResponse(url="/news", status_code=302)


@router.post("/api/upload/image")
async def upload_image(
    file: UploadFile, _: RequireUploader, store: UploadStoreDep
) -> JSONResponse:
    """Staff: store an image for the rich-text editor and return its URL."""
    filename = store.save(await read_upload(file, store))
    return JSONResponse({"url": f"/uploads/{filename}"})
