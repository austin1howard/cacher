This will be a lightweight python api using fastapi. it should have 3 endpoints:
- /healthz for health check
- /get to retrieve an endpoint, with a single query argument `url` that is a URL (validate this with fastapi)
- /refresh to refresh a cached endpoint, with a single query argument `url` that is a URL (validate this with fastapi)

maintain an in-memory cache of the response per url, and return that cached value on `/get` calls. on the `/refresh` endpoint, refresh the cached value of that URL. if `/get` is called and there's no cached data, retrieve the data from the url first and cache that...do this in a typical check > lock > recheck > get code pattern.

using pydantic settings, there should be a setting called allowed_hosts, which is a list of hostnames which can be used on the url query param. validate these on `/get` and `/refresh` calls.

create this, update the README.md to simply reflect the project, and generate a CLAUDE.md file too.

Interview me for any requirements gaps or architecture questions.