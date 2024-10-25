import asyncio
from datetime import UTC, datetime
from typing import Awaitable, Callable, Dict, List, Union

from app.config import FACT_CHECK_TOOL
from app.models.claim_models import Claim, FactCheckSession, VerificationResult
from app.utils.logging import get_logger

from .extractor import extract_claims
from .tools.google import google_claim_check
from .tools.perplexity import perplexity_claim_check

logger = get_logger("factcheck", "verification")

# Dictionary to store fact-check tools
fact_check_tools: Dict[
    str,
    Union[
        Callable[[Claim, str], VerificationResult],
        Callable[[Claim, str], Awaitable[VerificationResult]],
    ],
] = {
    "google": google_claim_check,
    "perplexity": perplexity_claim_check,
}

def register_fact_check_tool(
    name: str,
    tool: Union[
        Callable[[Claim, str], VerificationResult],
        Callable[[Claim, str], Awaitable[VerificationResult]],
    ],
) -> None:
    """
    Register a new fact-check tool (synchronous or asynchronous).

    Args:
        name (str): The name of the tool.
        tool (Union[Callable[[Claim, str], VerificationResult], Callable[[Claim, str], Awaitable[VerificationResult]]]):
            The function to perform fact-checking.
    """
    fact_check_tools[name] = tool
    logger.info(f"Registered new fact-check tool: {name}")

async def verify_single_claim(
    claim: Claim, short_user_id: str
) -> VerificationResult:
    """
    Verify a single claim using the configured fact-check tool.

    Args:
        claim (Claim): The claim to be verified.
        short_user_id (str): The short user ID generated from the message object.

    Returns:
        VerificationResult: The result of the claim verification from the specified tool.
    """
    if FACT_CHECK_TOOL not in fact_check_tools:
        logger.error(f"Unknown fact-check tool: {FACT_CHECK_TOOL}", user_id=short_user_id)
        return VerificationResult(
            claim_id=str(claim.id),
            claim=claim.content,
            google_claim_reviews=None,
            perplexity_claim_reviews=None,
            error=f"Unknown fact-check tool: {FACT_CHECK_TOOL}",
            verified_at=datetime.now(UTC),
        )

    try:
        tool = fact_check_tools[FACT_CHECK_TOOL]
        result = (
            await tool(claim, short_user_id)
            if asyncio.iscoroutinefunction(tool)
            else tool(claim, short_user_id)
        )
        return await result if isinstance(result, Awaitable) else result
    except Exception as e:
        logger.error(f"Error in {FACT_CHECK_TOOL} fact-check", error=str(e), user_id=short_user_id)
        return VerificationResult(
            claim_id=str(claim.id),
            claim=claim.content,
            google_claim_reviews=None,
            perplexity_claim_reviews=None,
            error=str(e),
            verified_at=datetime.now(UTC),
        )

async def verify_multiple_claims(
    claims: List[Claim], short_user_id: str, concurrency_limit: int = 10
) -> List[VerificationResult]:
    """
    Verify a list of claims using the configured fact-check tool concurrently.

    Args:
        claims (List[Claim]): The list of claims to verify.
        short_user_id (str): The short user ID generated from the message object.
        concurrency_limit (int): The maximum number of concurrent verification tasks.

    Returns:
        List[VerificationResult]: The verification results for all claims.
    """
    semaphore = asyncio.Semaphore(concurrency_limit)
    results: List[VerificationResult] = []

    async def sem_verify_claim(claim: Claim):
        async with semaphore:
            result = await verify_single_claim(claim, short_user_id)
            results.append(result)

    tasks = [sem_verify_claim(claim) for claim in claims]
    await asyncio.gather(*tasks, return_exceptions=False)

    logger.info(
        "Claims verification completed",
        total_claims=len(claims),
        verified_claims=len(results),
        user_id=short_user_id
    )
    return results

async def process_fact_check_session(
    session: FactCheckSession, short_user_id: str
) -> FactCheckSession:
    """
    Process a full fact-checking session, including claims extraction and verification.

    Args:
        session (FactCheckSession): The fact-checking session to process.
        short_user_id (str): The short user ID generated from the message object.

    Returns:
        FactCheckSession: The updated session with extracted claims and their verification results.
    """
    # Extract facts from the original text
    session.claims = await extract_claims(session.original_text, short_user_id)

    if not session.claims:
        logger.warn("No claims extracted in the session", user_id=short_user_id)
        session.completed_at = datetime.now(UTC)
        return session

    logger.info(
        "Starting verification of extracted claims", num_facts=len(session.claims), user_id=short_user_id
    )

    # Verify the extracted claims concurrently using the configured tool
    session.verification_results = await verify_multiple_claims(
        session.claims, short_user_id
    )

    session.completed_at = datetime.now(UTC)
    logger.info(
        "Fact checking process completed for session", session_id=session.session_id, user_id=short_user_id
    )

    return session
