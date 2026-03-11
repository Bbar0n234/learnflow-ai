from contextlib import AbstractAsyncContextManager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore


def create_checkpointer(db_url: str) -> AbstractAsyncContextManager[AsyncPostgresSaver]:
    return AsyncPostgresSaver.from_conn_string(db_url)


def create_store(db_url: str) -> AbstractAsyncContextManager[AsyncPostgresStore]:
    return AsyncPostgresStore.from_conn_string(db_url)
