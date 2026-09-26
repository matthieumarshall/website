"""Access control lists and permission dependencies (fastapi-permissions).

Routes declare what they need with an ``Annotated`` alias, for example::

    def edit_club(..., _: RequireStaff) -> ...
"""

from typing import Annotated

from fastapi_permissions import Allow, All, Authenticated, configure_permissions

from website.models import Post
from website.web.identity import get_active_principals

AclEntry = tuple[str, str, object]

Permission = configure_permissions(get_active_principals)

# Admins may do anything; content creators may create posts and upload images.
STAFF_ACL: list[AclEntry] = [
    (Allow, "role:admin", All),
    (Allow, "role:content_creator", ("create", "upload")),
]
# Management pages open to all staff (admins and content creators).
STAFF_MANAGE_ACL: list[AclEntry] = [
    (Allow, "role:admin", All),
    (Allow, "role:content_creator", All),
]
ADMIN_ACL: list[AclEntry] = [(Allow, "role:admin", All)]
AUTHENTICATED_ACL: list[AclEntry] = [(Allow, Authenticated, "view")]

RequireStaff = Annotated[object, Permission("edit", STAFF_MANAGE_ACL)]
RequireAdmin = Annotated[object, Permission("edit", ADMIN_ACL)]
RequirePostAuthor = Annotated[object, Permission("create", STAFF_ACL)]
RequireUploader = Annotated[object, Permission("upload", STAFF_ACL)]
RequireSignedIn = Annotated[object, Permission("view", AUTHENTICATED_ACL)]


class PostResource:
    """Wraps a Post and provides an ACL for fastapi-permissions."""

    def __init__(self, post: Post) -> None:
        """Wrap *post*."""
        self.post = post

    def __acl__(self) -> list[AclEntry]:
        """Authors and admins may edit or delete a post."""
        return [
            (Allow, f"user:{self.post.author_id}", ("edit", "delete")),
            (Allow, "role:admin", ("edit", "delete")),
        ]
