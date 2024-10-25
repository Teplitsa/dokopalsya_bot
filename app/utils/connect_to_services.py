import structlog
import tenacity
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from tenacity import _utils

TIMEOUT_BETWEEN_ATTEMPTS = 2
MAX_TIMEOUT = 30


def before_log(retry_state: tenacity.RetryCallState) -> None:
    if retry_state.outcome is None:
        return
    if retry_state.outcome.failed:
        verb, value = "raised", retry_state.outcome.exception()
    else:
        verb, value = "returned", retry_state.outcome.result()
    logger = retry_state.kwargs["logger"]
    logger.info(
        "Retrying {callback} in {sleep} seconds as it {verb} {value}",
        callback=_utils.get_callback_name(retry_state.fn),  # type: ignore[arg-type]
        sleep=retry_state.next_action.sleep,  # type: ignore[union-attr]
        verb=verb,
        value=value,
        extra={
            "callback": _utils.get_callback_name(retry_state.fn),  # type: ignore[arg-type]
            "sleep": retry_state.next_action.sleep,  # type: ignore[union-attr]
            "verb": verb,
            "value": value,
        },
    )


def after_log(retry_state: tenacity.RetryCallState) -> None:
    logger = retry_state.kwargs["logger"]
    logger.info(
        "Finished call to {callback!r} after {time:.2f}, this was the {attempt} time calling it.",
        callback=_utils.get_callback_name(retry_state.fn),  # type: ignore[arg-type]
        time=retry_state.seconds_since_start,
        attempt=_utils.to_ordinal(retry_state.attempt_number),
        extra={
            "callback": _utils.get_callback_name(retry_state.fn),  # type: ignore[arg-type]
            "time": retry_state.seconds_since_start,
            "attempt": _utils.to_ordinal(retry_state.attempt_number),
        },
    )


@tenacity.retry(
    wait=tenacity.wait_fixed(TIMEOUT_BETWEEN_ATTEMPTS),
    stop=tenacity.stop_after_delay(MAX_TIMEOUT),
    before_sleep=before_log,
    after=after_log,
)
async def wait_postgres(
    logger: structlog.typing.FilteringBoundLogger,
    database_url: str,
) -> async_sessionmaker[AsyncSession]:
    engine: AsyncEngine = create_async_engine(database_url)
    session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda conn: conn.execute(text("SELECT 1")))
    logger.info("Connected to PostgreSQL.")
    return session_maker
