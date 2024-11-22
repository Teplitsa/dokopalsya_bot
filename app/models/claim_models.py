import uuid
from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional

import orjson
import pydantic
from pydantic import Field


def orjson_dumps(
    v: Any,
    *,
    default: Optional[Callable[[Any], Any]],
) -> str:
    """Serialize using orjson and decode to string."""
    return orjson.dumps(v, default=default).decode()


class BaseModel(pydantic.BaseModel):
    """Base model with customized JSON serialization."""

    class Config:
        json_loads = orjson.loads
        json_dumps = orjson_dumps
        json_encoders = {uuid.UUID: lambda x: f"{x}"}


class Claim(BaseModel):
    """Represents an individual factual claim."""

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4, description="Unique identifier for the claim."
    )
    content: str = Field(..., description="The factual claim extracted from the text.")
    extracted_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the claim was extracted."
    )


class ExtractedClaims(BaseModel):
    """Represents the extracted claims from a text."""

    original: str = Field(..., description="The original claim text.")
    english: str = Field(..., description="The translated claim text.")
    claims: List[str] = Field(..., description="List of extracted claims.")


class GoogleClaimReview(BaseModel):
    """Represents a claim review from a fact-checking source."""

    publisher: Dict[str, Any] = Field(
        ..., description="The publisher of the claim review."
    )
    url: str = Field(..., description="The URL of the claim review.")
    title: str = Field(..., description="The title of the claim review.")
    review_date: Optional[datetime] = Field(
        None, description="The date when the review was published."
    )
    textual_rating: str = Field(
        ...,
        description="The textual rating of the claim (e.g., 'True', 'False', 'Mostly True').",
    )
    language_code: str = Field(
        ..., description="The language code of the claim review."
    )


class PerplexitySource(BaseModel):
    """Represents a source in a Perplexity claim review."""
    name: str = Field(..., description="Name of the source")
    content: str = Field(..., description="Brief content from the source")
    url: Optional[str] = Field(None, description="URL link to the source")

class PerplexityVerification(BaseModel):
    """Represents the verification details in a Perplexity claim review."""
    source: List[PerplexitySource] = Field(..., description="List of sources used for verification")
    conclusion: str = Field(..., description="Conclusion confirming or refuting the claim with explanation")

class PerplexityClaimsReviewItem(BaseModel):
    """Represents a single claim review item."""
    claim: str = Field(..., description="The claim being reviewed")
    verification: PerplexityVerification = Field(..., description="Verification details")

class PerplexityResponse(BaseModel):
    """Represents the complete response from Perplexity including citations."""
    claim_reviews: List[PerplexityClaimsReviewItem] = Field(..., description="List of claim reviews")
    citations: Optional[List[str]] = Field(None, description="List of citation URLs used in the response")

class PerplexityClaimsReview(PerplexityResponse):
    """Represents the complete claim review response from Perplexity."""
    pass

class VerificationResult(BaseModel):
    """Represents the verification result of a factual claim."""

    claim_id: str = Field(..., description="The ID of the claim being verified.")
    claim: str = Field(..., description="The original factual claim.")
    google_claim_reviews: Optional[List[GoogleClaimReview]] = Field(
        None,
        description="Details of the fact check review from Google Fact Check Tools API.",
    )
    perplexity_claim_reviews: Optional[PerplexityClaimsReview] = Field(
        None,
        description="Details of the fact check review from Perplexity service.",
    )
    error: Optional[str] = Field(
        None, description="Error message if verification failed."
    )
    verified_at: Optional[datetime] = Field(
        default=None, description="Timestamp when the claim was verified."
    )

    @property
    def perplexity_verification(self) -> Optional[PerplexityVerification]:
        """Returns the verification from the first claim review if available."""
        if (self.perplexity_claim_reviews and 
            self.perplexity_claim_reviews.claim_reviews and 
            len(self.perplexity_claim_reviews.claim_reviews) > 0):
            return self.perplexity_claim_reviews.claim_reviews[0].verification
        return None

    @property
    def perplexity_first_review(self) -> Optional[PerplexityClaimsReviewItem]:
        """Returns the first claim review if available."""
        if (self.perplexity_claim_reviews and 
            self.perplexity_claim_reviews.claim_reviews and 
            len(self.perplexity_claim_reviews.claim_reviews) > 0):
            return self.perplexity_claim_reviews.claim_reviews[0]
        return None


class FactCheckSession(BaseModel):
    """Encapsulates a fact-checking session for a user's submission."""
    user_id: str = Field(
        ..., description="The unique identifier of the user who initiated the fact-checking session."
    )
    session_id: uuid.UUID = Field(
        default_factory=uuid.uuid4, description="Unique identifier for the session."
    )
    original_text: str = Field(
        ..., description="The original input text containing multiple factual claims."
    )
    claims: List[Claim] = Field(
        default_factory=list,
        description="List of extracted claims from the original text.",
    )
    verification_results: List[VerificationResult] = Field(
        default_factory=list, description="List of verification results for each claim."
    )
    created_at: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp when the session was created.",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the fact-checking session was completed.",
    )
