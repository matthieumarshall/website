"""Business logic, one service class per area.

Services take a database connection (and any external collaborators) in
their constructor, raise :mod:`website.errors` exceptions, and never import
the web framework.
"""
