import asyncio
import pytest
import selectors
import sys

@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

@pytest.fixture(scope="session")
def event_loop():
    """
    Force SelectorEventLoop on Windows for Psycopg3 compatibility.
    """
    if sys.platform == 'win32':
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    else:
        loop = asyncio.new_event_loop()
    
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
