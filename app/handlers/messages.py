import re
import uuid

from aiogram import F, Router, flags
from aiogram.filters import Command, CommandStart
from aiogram.types import LinkPreviewOptions, Message

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
    welcome_text = (
        "Привет! Я бот ФактЧекер, и моя задача — помочь тебе проверять достоверность "
        "новостей, утверждений и статей с помощью Perplexity.\n\n"
        "<b>Что я умею:</b>\n"
        "• Проверяю тексты и посты в Telegram на достоверность.\n"
        "• Предоставляю результаты проверки с подробной информацией о проверенных источниках.\n\n"
        "<b>Как использовать:</b>\n"
        "• Отправь мне текст или Telegram-пост.\n"
        "• Получи проверку фактов и убедись в достоверности информации.\n\n"
        "Кстати, у нас есть ещё один полезный бот — «Насквозь» @naskvos_bot. "
        "Он помогает распознавать эмоциональные манипуляции в сообщениях и новостях. "
        "Попробуйте его, чтобы стать более уверенными в том, что вас не вводят в заблуждение."
    )
    await message.answer(welcome_text, parse_mode="HTML")


@router.message(Command(commands="info"))
@flags.chat_action("typing")
async def process_info_command(message: Message) -> None:
    logger.debug('Info command received', user_id=message.from_user.id)
    info_text = (
        "<b>Проект ФактЧекер</b> создан для борьбы с дезинформацией и распространением "
        "недостоверных сведений.\n\n"
        "<b>Цель проекта</b> — предоставить удобный инструмент для проверки фактов с помощью "
        "Perplexity, чтобы каждый мог убедиться в достоверности информации и "
        "не стать жертвой ложных новостей.\n\n"
        "Используй ФактЧекер для того, чтобы получать только проверенные данные и "
        "бороться с ложной информацией в сети!"
    )
    await message.answer(info_text, parse_mode="HTML")


@flags.chat_action("typing")
@router.message(Command(commands=re.compile(r".*")))
async def process_other_commands(message: Message) -> None:
    logger.debug('Other command received', user_id=message.from_user.id, command=message.text)
    await message.answer("Ответ на другие команды")


@router.message(F.text | F.caption)
@flags.chat_action("typing")
async def message(message: Message) -> None:
    """
    Handle incoming messages.
    """
    # Generate trace_id at the start of message processing
    trace_id = str(uuid.uuid4())
    short_user_id = generate_short_user_id(message.from_user.id)
    
    text = message.text or message.caption or ""
    logger.info('Processing message', user_id=short_user_id, text_length=len(text))

    session = FactCheckSession(original_text=text, user_id=short_user_id)
    
    # Extract claims
    claims = await extract_claims(text, short_user_id, trace_id)
    session.claims = claims

    if not claims:
        logger.info('No claims found in message', user_id=short_user_id)
        await message.reply(
            "Результаты проверки фактов:\nНе обнаружено фактических утверждений в вашем сообщении.",
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        return

    # Send intermediate message with extracted claims
    claims_message = "Мы проанализировали отправленный текст и извлекли "

    if len(claims) == 1:
        claims_message += "следующее ключевое утверждение:\n\n"
        claims_message += f"<b>{claims[0].content}</b>\n"
    else:
        claims_message += "следующие ключевые утверждения:\n\n"
        for idx, claim in enumerate(claims, start=1):
            claims_message += f"{idx}. <b>{claim.content}</b>\n"
    claims_message += "\nПродолжаем проверку..."

    await message.reply(claims_message, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))

    # Continue with fact-checking process
    processed_session = await process_fact_check_session(session, short_user_id, trace_id)

    # Prepare response based on verification_results
    response_lines = ["Результаты проверки утверждений:"]
    
    total_claims = len(processed_session.claims)
    for idx, claim in enumerate(processed_session.claims, start=1):
        results = [
            r
            for r in processed_session.verification_results
            if r.claim_id == str(claim.id)
        ]
        if results:
            for result in results:
                # Add claim with number only if there are multiple claims
                if total_claims > 1:
                    response_lines.append(f"\n{idx}. <b>{claim.content}</b>\n")
                else:
                    response_lines.append(f"\n<b>{claim.content}</b>\n")
                
                if result.google_claim_reviews:
                    review = result.google_claim_reviews[0]
                    verdict = review.textual_rating
                    source = review.publisher.get("site", "Неизвестный источник")
                    response_lines.append(f"<b>Вердикт:</b> {verdict}")
                    response_lines.append(f"<b>Источник:</b> <a href='{source.url}'>{source.name}</a>")
                
                if result.perplexity_claim_reviews and result.perplexity_claim_reviews.claim_reviews:
                    review = result.perplexity_claim_reviews.claim_reviews[0]
                    if review:
                        conclusion = review.verification.conclusion
                        response_lines.append(f"<b>Заключение:</b> {conclusion}")
                        response_lines.append("\n<b>Источники:</b>")
                        
                        # Add sources with their content and URLs
                        for source in review.verification.source:
                            response_lines.append(f"<a href='{source.url}'>{source.name}</a>")
                            if source.content:
                                response_lines.append(f"<blockquote>{source.content}</blockquote>")
                else:
                    response_lines.append("⚠️ Нет достоверной информации.")
        else:
            # Add claim with number only if there are multiple claims
            if total_claims > 1:
                response_lines.append(f"\n{idx}. <b>{claim.content}</b>")
            else:
                response_lines.append(f"\n<b>{claim.content}</b>")
            response_lines.append("⚠️ Нет достоверной информации.")

    response = "\n".join(response_lines)

    logger.info('Sending fact-check response', user_id=short_user_id, claims_count=len(processed_session.claims))
    await message.reply(response, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))
