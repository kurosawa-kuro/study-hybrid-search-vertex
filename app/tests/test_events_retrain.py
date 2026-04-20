from fastapi.testclient import TestClient


class _RecordingRunner:
    def __init__(self, execution: str) -> None:
        self._execution = execution
        self.calls = 0

    def start(self) -> str:
        self.calls += 1
        return self._execution


def test_events_retrain_delegates_to_training_job_runner(app_with_search_stub):
    app = app_with_search_stub
    runner = _RecordingRunner("projects/p/.../executions/xyz")
    app.state.training_job_runner = runner

    r = TestClient(app).post("/events/retrain")

    assert r.status_code == 200
    assert r.json() == {"execution": "projects/p/.../executions/xyz"}
    assert runner.calls == 1
