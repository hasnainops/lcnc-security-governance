"""Input contract for sanitized Appsmith connector observations.

Counts, destination trust, policy revision and ingestion time are server-owned.
This module validates input; it does not resolve DNS or persist data.
"""

import re
from ipaddress import ip_address
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

Identifier = Annotated[
    str,
    Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9_.:-]+$"),
]
PendingReason = Literal[
    "pages_incomplete",
    "actions_incomplete",
    "datasources_incomplete",
    "connector_identity_unresolved",
]


class ObservationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
    )


class ObservedHttpDestination(ObservationModel):
    scheme: Literal["http", "https"]
    host: str = Field(min_length=1, max_length=253)
    port: int | None = Field(
        default=None, strict=True, ge=1, le=65535
    )

    @field_validator("host")
    @classmethod
    def validate_host(cls, value):
        if "%" in value:
            raise ValueError(
                "Expected a hostname or IP address without a zone"
            )
        try:
            return ip_address(value).compressed
        except ValueError:
            pass

        name = value.lower().removesuffix(".")
        label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
        if (
            not name
            or all(character in "0123456789." for character in name)
            or not all(
                re.fullmatch(label, part)
                for part in name.split(".")
            )
        ):
            raise ValueError(
                "Expected a hostname only, without URL components"
            )
        return name


class ObservedConnector(ObservationModel):
    connector_id: Identifier
    destination_state: Literal[
        "observed", "unresolved", "unsupported"
    ]
    destination: ObservedHttpDestination | None = None
    uses_api_key: StrictBool | None = None

    @model_validator(mode="after")
    def check_destination(self):
        observed = self.destination_state == "observed"
        if observed != (self.destination is not None):
            raise ValueError(
                "Destination must be supplied exactly when observed"
            )
        return self


class ObservedActionDestination(ObservationModel):
    """Sanitized action evidence, not a verified connector identity."""

    action_id: Identifier
    destination_state: Literal[
        "observed", "unresolved", "unsupported"
    ]
    destination: ObservedHttpDestination | None = None
    uses_api_key: StrictBool | None = None

    @model_validator(mode="after")
    def check_destination(self):
        observed = self.destination_state == "observed"
        if observed != (self.destination is not None):
            raise ValueError(
                "Destination must be supplied exactly when observed"
            )
        return self



class ObservedDataFieldEvidence(ObservationModel):
    """Sanitized widget field evidence, not a database schema."""

    scope: Literal["appsmith_widget_dsl"]

    coverage: Literal[
        "partial",
        "none_observed",
        "uncollected",
    ]

    field_identifiers: list[
        Annotated[
            str,
            Field(
                min_length=1,
                max_length=64,
                pattern=r"^[A-Za-z][A-Za-z0-9_]*$",
            ),
        ]
    ] = Field(max_length=1000)

    pages_expected: int = Field(strict=True, ge=0, le=1000)
    pages_inspected: int = Field(strict=True, ge=0, le=1000)
    widgets_inspected: int = Field(strict=True, ge=0)
    dynamic_bindings_detected: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def check_evidence(self):
        if self.pages_inspected > self.pages_expected:
            raise ValueError(
                "Inspected pages exceed expected pages"
            )

        if len(self.field_identifiers) != len(
            set(self.field_identifiers)
        ):
            raise ValueError(
                "Duplicate field identifiers"
            )

        if self.coverage == "uncollected":
            if (
                self.pages_inspected != 0
                or self.widgets_inspected != 0
                or self.dynamic_bindings_detected != 0
                or self.field_identifiers
            ):
                raise ValueError(
                    "Uncollected evidence cannot contain fields"
                )

        elif self.coverage == "none_observed":
            if (
                self.pages_expected == 0
                or self.pages_inspected != self.pages_expected
                or self.dynamic_bindings_detected != 0
                or self.field_identifiers
            ):
                raise ValueError(
                    "Invalid none_observed coverage"
                )

        elif self.coverage == "partial":
            if self.pages_inspected == 0:
                raise ValueError(
                    "Partial evidence requires inspected pages"
                )

            if (
                self.pages_inspected == self.pages_expected
                and not self.field_identifiers
                and self.dynamic_bindings_detected == 0
            ):
                raise ValueError(
                    "Empty inspected evidence must be none_observed"
                )

        return self


class AppsmithObservation(ObservationModel):
    contract_version: Literal["appsmith-observation-v1"]
    source: Literal["appsmith"]
    external_id: Identifier
    collector_version: Identifier
    observed_at: AwareDatetime

    # Complete enumeration does not imply resolvable destinations.
    collection_complete: StrictBool
    pending_reasons: list[PendingReason] = Field(max_length=4)
    page_ids: list[Identifier] = Field(
        default_factory=list, max_length=1000
    )
    connectors: list[ObservedConnector] = Field(max_length=1000)
    observed_actions: list[ObservedActionDestination] = Field(
        default_factory=list, max_length=1000
    )

    data_field_evidence: ObservedDataFieldEvidence | None = None

    @model_validator(mode="after")
    def check_collection(self):
        if self.collection_complete == bool(self.pending_reasons):
            raise ValueError(
                "Incomplete collection requires reasons; "
                "complete collection forbids them"
            )

        identifiers = [
            item.connector_id for item in self.connectors
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(
                "Connector identities must be unique within a snapshot"
            )

        if len(self.pending_reasons) != len(set(self.pending_reasons)):
            raise ValueError("Pending reasons must be unique")

        if len(self.page_ids) != len(set(self.page_ids)):
            raise ValueError("Page identities must be unique")

        action_ids = [
            item.action_id for item in self.observed_actions
        ]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError(
                "Action identities must be unique within a snapshot"
            )

        if self.data_field_evidence is not None:
            if "page_ids" not in self.model_fields_set:
                raise ValueError(
                    "Field evidence requires explicit page identities"
                )

            if (
                self.data_field_evidence.pages_expected
                != len(self.page_ids)
            ):
                raise ValueError(
                    "Field evidence page count mismatch"
                )

        return self
