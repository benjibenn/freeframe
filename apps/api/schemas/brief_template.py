from typing import Any

from pydantic import BaseModel


# The template `sections` list is intentionally free-form (list of dicts), mirroring
# how brief_json itself is stored/rendered: the frontend builder guarantees the shape
# ({id, title, path, as, columns?}) and the renderer skips anything malformed. Keeping
# it loose here lets admins add section shapes we don't yet render without a schema bump.
class BriefTemplateResponse(BaseModel):
    sections: list[dict[str, Any]]


class BriefTemplateUpdate(BaseModel):
    sections: list[dict[str, Any]]
