import json
import logging
import unittest
from unittest.mock import Mock

from components.component3_observability import (
    log_component3_event,
    request_trace_id,
)


class Component3ObservabilityTests(unittest.TestCase):
    def test_safe_caller_trace_id_is_preserved(self):
        self.assertEqual(request_trace_id("request-123"), "request-123")

    def test_unsafe_or_oversized_trace_id_is_replaced(self):
        for value in ("bad trace", "../bad", "x" * 65, None):
            with self.subTest(value=value):
                generated = request_trace_id(value)
                self.assertEqual(len(generated), 32)
                int(generated, 16)

    def test_event_is_emitted_as_structured_json(self):
        logger = Mock(spec=logging.Logger)

        log_component3_event(
            logger,
            "prediction_completed",
            request_id="request-123",
            model_version="v3",
            latency_ms=12.5,
        )

        logger.log.assert_called_once()
        level, message, serialized = logger.log.call_args.args
        self.assertEqual(level, logging.INFO)
        self.assertEqual(message, "component3_event %s")
        payload = json.loads(serialized)
        self.assertEqual(payload["component"], "component3")
        self.assertEqual(payload["event"], "prediction_completed")
        self.assertEqual(payload["request_id"], "request-123")
        self.assertEqual(payload["model_version"], "v3")


if __name__ == "__main__":
    unittest.main()
