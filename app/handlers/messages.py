import re

from aiogram import F, Router, flags
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.factcheck import process_fact_check_session
from app.factcheck.extractor import extract_claims
from app.models.claim_models import FactCheckSession
from app.utils.logging import get_logger
from app.utils.user_utils import generate_short_user_id

router = Router()

logger = get_logger("handlers", "messages")


@router.message(CommandStart())
async def process_start_command(message: Message) -> None:
    logger.debug('Start command received', user_id=message.from_user.id)
    await message.answer("Welcome! Use /info for more information.")


@router.message(Command(commands="info"))
@flags.chat_action("typing")
async def process_info_command(message: Message) -> None:
    logger.debug('Info command received', user_id=message.from_user.id)
    await message.answer("reply.info()")


@flags.chat_action("typing")
@router.message(Command(commands=re.compile(r".*")))
async def process_other_commands(message: Message) -> None:
    logger.debug('Other command received', user_id=message.from_user.id, command=message.text)
    await message.answer("reply.other_commands()")


@router.message(F.text | F.caption)
@flags.chat_action("typing")
async def message(message: Message, db: AsyncSession | None = None) -> None:
    text = message.text or message.caption or ""
    user_id = message.from_user.id if message.from_user else None
    short_user_id = generate_short_user_id(user_id)
    logger.info('Processing message', user_id=short_user_id, text_length=len(text))

    session = FactCheckSession(original_text=text, user_id=short_user_id)
    
    # Extract claims
    claims = await extract_claims(text, short_user_id)
    session.claims = claims

    if not claims:
        logger.info('No claims found in message', user_id=short_user_id)
        await message.reply(
            "Результаты проверки фактов:\nНе обнаружено фактических утверждений в вашем сообщении."
        )
        return

    # Send intermediate message with extracted claims
    claims_message = "Мы проанализировали отправленный текст и извлекли следующие ключевые утверждения:\n\n"
    for idx, claim in enumerate(claims, start=1):
        claims_message += f"{idx}. {claim.content}\n"
    claims_message += "\nПродолжаем проверку этих утверждений..."

    await message.reply(claims_message)

    # Continue with fact-checking process
    processed_session = await process_fact_check_session(session, short_user_id)

    # Prepare response based on verification_results
    response_lines = ["Результаты проверки утверждений:"]
    for idx, claim in enumerate(processed_session.claims, start=1):
        results = [
            r
            for r in processed_session.verification_results
            if r.claim_id == str(claim.id)
        ]
        if results:
            for result in results:
                if result.google_claim_reviews:
                    review = result.google_claim_reviews[0]  # Take the first review
                    verdict = review.textual_rating
                    source = review.publisher.get("site", "Неизвестный источник")
                    response_lines.append(f"{idx}. {verdict} - Источник: {source}")
                elif result.perplexity_claim_reviews and result.perplexity_claim_reviews.claim_reviews:
                    review = result.perplexity_claim_reviews.first_review  # Use the property we defined
                    if review:
                        conclusion = review.verification.conclusion
                        sources = ", ".join([source.name for source in review.verification.source])
                        response_lines.append(f"{idx}. {conclusion} - Источники: {sources}")
                else:
                    response_lines.append(f"{idx}. {claim.content} – ⚠️ Нет достоверной информации.")
        else:
            response_lines.append(f"{idx}. {claim.content} – ⚠️ Нет достоверной информации.")
        response_lines.append("")  # Add an empty line between claims

    response = "\n".join(response_lines)

    logger.info('Sending fact-check response', user_id=short_user_id, claims_count=len(processed_session.claims))
    await message.reply(response)
