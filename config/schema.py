"""Shared schemas for actual DRF error responses."""
from drf_spectacular.utils import inline_serializer, extend_schema
from rest_framework import serializers

DetailError = inline_serializer(
    name="DetailError", fields={"detail": serializers.CharField()},
)
# Field validation errors can be a string or a list (existing subscription API).
ValidationErrorSchema = {
    "type": "object",
    "additionalProperties": {
        "oneOf": [
            {"type": "string"},
            {"type": "array", "items": {"type": "string"}},
        ],
    },
}


def documented_response(
    serializer, success=200, *, validation=False, forbidden=False, missing=False,
):
    responses = {success: serializer, 401: DetailError}
    if validation:
        responses[400] = ({"type": "array", "items": {"type": "string"}}
                          if success == 204 else ValidationErrorSchema)
    if forbidden:
        responses[403] = DetailError
    if missing:
        responses[404] = DetailError
    return extend_schema(responses=responses)
