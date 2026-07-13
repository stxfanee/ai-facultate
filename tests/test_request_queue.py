import tempfile
import threading
import time
import unittest
from pathlib import Path

from server.queue.request_queue import (
    InferenceRequestQueue,
    RequestCancelledError,
    QueueWaitTimeoutError,
)
from server.memory.study_memory import initialize_database, set_preference


class RequestQueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "queue.sqlite3"
        initialize_database(self.database_path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_default_limit_serializes_generations_across_queue_instances(self):
        first_queue = InferenceRequestQueue(self.database_path)
        second_queue = InferenceRequestQueue(self.database_path)
        first_started = threading.Event()
        release_first = threading.Event()
        second_finished = threading.Event()
        positions = []
        active = 0
        max_active = 0
        state_lock = threading.Lock()

        def worker_one():
            nonlocal active, max_active
            with first_queue.request_context("user-one", "test"):
                with first_queue.llm_slot():
                    with state_lock:
                        active += 1
                        max_active = max(max_active, active)
                    first_started.set()
                    release_first.wait(timeout=5)
                    with state_lock:
                        active -= 1

        def callback(status, position, _request_id):
            if status == "queued" and position:
                positions.append(position)

        def worker_two():
            nonlocal active, max_active
            first_started.wait(timeout=5)
            with second_queue.request_context("user-two", "test", callback=callback):
                with second_queue.llm_slot():
                    with state_lock:
                        active += 1
                        max_active = max(max_active, active)
                        active -= 1
            second_finished.set()

        first_thread = threading.Thread(target=worker_one)
        second_thread = threading.Thread(target=worker_two)
        first_thread.start()
        second_thread.start()
        self.assertTrue(first_started.wait(timeout=5))
        time.sleep(0.4)
        self.assertFalse(second_finished.is_set())
        release_first.set()
        first_thread.join(timeout=5)
        second_thread.join(timeout=5)

        self.assertFalse(first_thread.is_alive())
        self.assertFalse(second_thread.is_alive())
        self.assertEqual(max_active, 1)
        self.assertIn(1, positions)
        diagnostics = first_queue.diagnostics()
        self.assertEqual(diagnostics["queued_requests"], 0)
        self.assertEqual(diagnostics["running_requests"], 0)

    def test_configured_limit_allows_two_generations(self):
        set_preference(self.database_path, "max_concurrent_generations", "2")
        queues = [
            InferenceRequestQueue(self.database_path),
            InferenceRequestQueue(self.database_path),
        ]
        both_running = threading.Barrier(3)
        release = threading.Event()
        active = 0
        max_active = 0
        state_lock = threading.Lock()

        def worker(index):
            nonlocal active, max_active
            queue = queues[index]
            with queue.request_context(f"user-{index}", "test"):
                with queue.llm_slot():
                    with state_lock:
                        active += 1
                        max_active = max(max_active, active)
                    both_running.wait(timeout=5)
                    release.wait(timeout=5)
                    with state_lock:
                        active -= 1

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        both_running.wait(timeout=5)
        release.set()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(max_active, 2)

    def test_queued_request_can_be_cancelled(self):
        queue = InferenceRequestQueue(self.database_path)
        blocker_ready = threading.Event()
        release_blocker = threading.Event()
        cancelled = threading.Event()

        def blocker():
            with queue.request_context("blocker", "test"):
                with queue.llm_slot():
                    blocker_ready.set()
                    release_blocker.wait(timeout=5)

        def waiting_request():
            blocker_ready.wait(timeout=5)
            try:
                with queue.request_context(
                    "waiting-user",
                    "test",
                    request_id="cancel-me-request",
                ):
                    with queue.llm_slot():
                        pass
            except RequestCancelledError:
                cancelled.set()

        blocker_thread = threading.Thread(target=blocker)
        waiting_thread = threading.Thread(target=waiting_request)
        blocker_thread.start()
        waiting_thread.start()
        self.assertTrue(blocker_ready.wait(timeout=5))

        deadline = time.time() + 5
        while time.time() < deadline:
            status = queue.get_request("cancel-me-request")
            if status and status["position"] == 1:
                break
            time.sleep(0.05)
        self.assertTrue(queue.cancel("cancel-me-request"))
        self.assertTrue(cancelled.wait(timeout=5))
        release_blocker.set()
        blocker_thread.join(timeout=5)
        waiting_thread.join(timeout=5)
        status = queue.get_request("cancel-me-request")
        self.assertEqual(status["status"], "failed")
        self.assertTrue(status["cancel_requested"])


    def test_new_request_replaces_abandoned_queued_request_for_same_user(self):
        queue = InferenceRequestQueue(self.database_path)
        old_request = queue.enqueue("same-user", "chat", request_id="old-abandoned")
        self.assertEqual(queue.get_request(old_request.request_id)["status"], "queued")

        new_request = queue.enqueue("same-user", "chat", request_id="new-active")

        old_status = queue.get_request(old_request.request_id)
        new_status = queue.get_request(new_request.request_id)
        self.assertEqual(old_status["status"], "failed")
        self.assertIn("inlocuita", old_status["error_message"])
        self.assertEqual(new_status["status"], "queued")

    def test_wait_timeout_marks_request_failed(self):
        queue = InferenceRequestQueue(self.database_path)
        waiting_queue = InferenceRequestQueue(self.database_path)
        with queue.request_context("blocker", "test"):
            with queue.llm_slot():
                with self.assertRaises(QueueWaitTimeoutError):
                    with waiting_queue.request_context(
                        "waiting-user",
                        "test",
                        request_id="timeout-request",
                    ):
                        with waiting_queue.llm_slot(timeout_seconds=0.15):
                            pass
        status = queue.get_request("timeout-request")
        self.assertEqual(status["status"], "failed")
        self.assertIn("așteptare", status["error_message"])


if __name__ == "__main__":
    unittest.main()


