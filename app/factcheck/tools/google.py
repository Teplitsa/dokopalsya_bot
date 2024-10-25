from datetime import UTC, datetime

import structlog
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import GOOGLE_API_KEY
from app.models.claim_models import Claim, GoogleClaimReview, VerificationResult

logger = structlog.get_logger(__name__)


async def google_claim_check(claim: Claim) -> VerificationResult:
    """
    Check a single claim using the Google Fact Check Tools API.

    Args:
        claim (Claim): The claim to be verified.

    Returns:
        VerificationResult: The result of the claim verification.
    """
    try:
        service = build("factchecktools", "v1alpha1", developerKey=GOOGLE_API_KEY)
        request = service.claims().search(
            query=claim.content, pageSize=10
        )  # Adjust pageSize as needed
        response = request.execute()

        claim_reviews = []
        if "claims" in response and response["claims"]:
            for claim_data in response["claims"]:
                for claim_review in claim_data.get("GoogleClaimReview", []):
                    claim_reviews.append(
                        GoogleClaimReview(
                            publisher={"site": claim_review["publisher"]["site"]},
                            url=claim_review["url"],
                            title=claim_review["title"],
                            review_date=(
                                datetime.fromisoformat(claim_review["reviewDate"])
                                if claim_review.get("reviewDate")
                                else None
                            ),
                            textual_rating=claim_review["textualRating"],
                            language_code=claim_review["languageCode"],
                        )
                    )

        return VerificationResult(
            claim_id=str(claim.id),
            claim=claim.content,
            google_claim_reviews=claim_reviews if claim_reviews else None,
            perplexity_claim_reviews=None,
            verified_at=datetime.now(UTC),
            error=None,
        )
    except HttpError as e:
        logger.error("Error checking claim", claim_id=claim.id, error=str(e))
        return VerificationResult(
            claim_id=str(claim.id),
            claim=claim.content,
            google_claim_reviews=None,
            perplexity_claim_reviews=None,
            error=str(e),
            verified_at=datetime.now(UTC),
        )
    except Exception as e:
        logger.error("Unexpected error checking claim", claim_id=claim.id, error=str(e))
        return VerificationResult(
            claim_id=str(claim.id),
            claim=claim.content,
            google_claim_reviews=None,
            perplexity_claim_reviews=None,
            error=str(e),
            verified_at=datetime.now(UTC),
        )
