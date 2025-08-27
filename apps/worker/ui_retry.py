import time
from typing import Callable, Optional, Type

def retry(fn: Callable, tries: int = 5, delay: float = 0.6, exc: Type[Exception] = Exception):
    for i in range(tries):
        try:
            return fn()
        except exc as e:
            if i == tries - 1:
                raise
            time.sleep(delay * (1.4 ** i))  # backoff
