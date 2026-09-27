

from langchain_core.runnables import RunnableLambda

import random


def add_one(x: int) -> int:
    return x + 1


def buggy_double(y: int) -> int:
    """Buggy code that will fail 70% of the time"""

    if random.random() > 0.3:
        print('This code failed, and will probably be retried!')  # noqa: T201
        raise ValueError('Triggered buggy code')
    return y * 2


sequence = (

    RunnableLambda(add_one) |

    RunnableLambda(buggy_double).with_retry(  # Retry on failure

        stop_after_attempt=10,

        wait_exponential_jitter=False

    )
)

print(sequence.input_schema.model_json_schema())  # Show inferred input schema
# Show inferred output schema
print(sequence.output_schema.model_json_schema())
print(sequence.invoke(2))  # invoke the sequence (note the retry above!!)
