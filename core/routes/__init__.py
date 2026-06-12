"""Route handler mixins cho HTTP Handler (tách từ qa_dashboard.py — issue #86, Phần B).

Mỗi mixin gom 1 nhóm route + helper CHỈ nhóm đó dùng. Handler trong qa_dashboard.py
kế thừa các mixin này; helper dùng chung (`_base_url`, `_redirect`, `_cookie`,
`_forbidden`, `_html`, `_is_admin`, ...) vẫn ở Handler và resolve qua MRO.

Layer rule (CLAUDE.md): KHÔNG import qa_dashboard ở đây (tránh vòng import).
"""
from routes.oauth import OAuthMixin
from routes.write import WriteMixin

__all__ = ['OAuthMixin', 'WriteMixin']
