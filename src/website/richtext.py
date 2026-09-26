"""Pure text and HTML utilities shared by services and templates."""

import re
from urllib.parse import urlparse

import nh3

# Allowed HTML tags / attributes for sanitised rich-text content
_ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "s",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "blockquote",
    "a",
    "img",
    "table",
    "thead",
    "tbody",
    "tfoot",
    "tr",
    "th",
    "td",
    "colgroup",
    "col",
    "span",
}
_ALLOWED_ATTRS = {
    "a": {"href", "title", "target", "aria-label"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan", "data-row", "data-cell"},
    "th": {"colspan", "rowspan", "scope"},
    "col": {"width"},
    "table": {"class"},
    "span": {"class", "data-row", "data-cell"},
}
_CLOSING_TAGS = ("</p>", "</blockquote>", "</li>", "</div>")
_TRAILING_PUNCTUATION = ".,;:!? \t\n"


def sanitise_html(raw: str) -> str:
    """Strip any HTML not on the rich-text allow-list."""
    return nh3.clean(raw, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)


def validate_http_url(value: str) -> str:
    """Validate and return a public HTTP(S) URL.

    Raises:
        ValueError: If *value* is not an absolute http or https URL.
    """
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an HTTP or HTTPS URL")
    return value.strip()


def safe_referer_path(referer: str) -> str:
    """Return the local path of a Referer header, defaulting to ``/news``."""
    if not referer:
        return "/news"
    path = urlparse(referer).path
    return path if path and path.startswith("/") else "/news"


def post_summary(content: str, post_id: int, length: int = 300) -> str:
    """Return an HTML summary of post content truncated at a word boundary.

    If the post is longer than length, it is truncated and an inline
    '... see more' link pointing to /news/{post_id} is appended.
    Unclosed HTML tags are safely balanced via sanitise_html.
    """
    if not content:
        return ""

    plain = re.sub(r"<[^>]+>", "", content).strip()
    if len(content) <= length or (
        len(plain) <= length and len(content) <= length + 100
    ):
        return content

    sliced = content[:length]
    sliced = re.sub(r"<[^>]*$", "", sliced)
    if " " in sliced:
        sliced = sliced.rsplit(" ", 1)[0]
    sliced = re.sub(r"<[^>]*$", "", sliced)
    sliced = sliced.rstrip(_TRAILING_PUNCTUATION)

    clean_body = sanitise_html(sliced)
    link = (
        f'... <a href="/news/{post_id}" aria-label="See more of this post">see more</a>'
    )

    for tag in _CLOSING_TAGS:
        if clean_body.endswith(tag):
            idx = len(clean_body) - len(tag)
            body_without_tag = clean_body[:idx].rstrip(_TRAILING_PUNCTUATION)
            return body_without_tag + link + tag

    return f"{clean_body}{link}"
