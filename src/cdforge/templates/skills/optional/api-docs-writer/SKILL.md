---
name: api-docs-writer
description: Keep the OpenAPI schema and endpoint documentation in sync with the DRF views and serializers.
---

Whenever a view, serializer, or URL changes in a way that affects the public API:

- Add or update DRF `@extend_schema` annotations (from `drf_spectacular.utils`) so the
  generated OpenAPI schema at `/api/schema/` accurately describes the endpoint: request
  body, query parameters, response shape, and status codes.
- Keep any example request/response snippets in `README.md` in sync with the actual
  serializer fields.
- When removing or renaming an endpoint, note it under `### Changed` or `### Removed` in
  `CHANGELOG.md` since it is a contract change for API consumers.
