from collections.abc import Iterable
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
SourceID = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
NodeID = Annotated[str, Field(pattern=r"^n:[0-9a-f]{64}$")]
RecordID = Annotated[str, Field(pattern=r"^line:[1-9][0-9]*$")]
EvidenceDerivation = Literal[
    "observed",
    "context-order",
    "route-inference",
    "response-correlation",
    "paramtrack-unique-method-path",
]


class CanonicalModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class Diagnostic(CanonicalModel):
    source: NonEmptyString | None
    line: Annotated[int, Field(ge=1)] | None
    code: NonEmptyString
    message: NonEmptyString

    @model_validator(mode="after")
    def validate_source_line(self) -> "Diagnostic":
        if self.line is not None and self.source is None:
            raise ValueError("diagnostic line requires a source")
        return self


class SourceArtifact(CanonicalModel):
    id: SourceID
    kind: Literal["contexttrack-jsonl", "paramtrack-csv", "ctype-graph"]


class EvidenceRef(CanonicalModel):
    source_id: SourceID
    records: Annotated[tuple[RecordID, ...], Field(min_length=1)]
    derivation: EvidenceDerivation

    @field_validator("records")
    @classmethod
    def validate_record_order(cls, records: tuple[str, ...]) -> tuple[str, ...]:
        expected = tuple(sorted(set(records), key=_record_number))
        if records != expected:
            raise ValueError("evidence records must be in canonical order")
        return records


def _record_number(record: str) -> int:
    return int(record.removeprefix("line:"))


def merge_evidence(evidence: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    records_by_key: dict[tuple[str, EvidenceDerivation], set[str]] = {}
    for reference in evidence:
        key = (reference.source_id, reference.derivation)
        records_by_key.setdefault(key, set()).update(reference.records)

    merged = [
        EvidenceRef(
            source_id=source_id,
            derivation=derivation,
            records=tuple(sorted(records, key=_record_number)),
        )
        for (source_id, derivation), records in records_by_key.items()
    ]
    return tuple(
        sorted(
            merged,
            key=lambda item: (item.source_id, item.derivation, item.records),
        )
    )


def sort_diagnostics(diagnostics: Iterable[Diagnostic]) -> tuple[Diagnostic, ...]:
    return tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.source is not None,
                item.source or "",
                item.line is not None,
                item.line or 0,
                item.code,
                item.message,
            ),
        )
    )
