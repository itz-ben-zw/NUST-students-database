"""Unit tests for read-only assistant query authorization and input validation."""
from ai_assistant import _tool_result


class FakeConnection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        return self

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return {"student_count": 12}


def test_finance_tool_denies_student_role_without_query():
    conn = FakeConnection()
    result = _tool_result(conn, "get_finance_overview", {}, {"role": "student"})
    assert "error" in result
    assert conn.calls == []


def test_student_search_denies_finance_role_without_query():
    conn = FakeConnection()
    result = _tool_result(conn, "search_students", {"query": "Ben"}, {"role": "finance"})
    assert "error" in result
    assert conn.calls == []


def test_search_rejects_empty_query():
    conn = FakeConnection()
    result = _tool_result(conn, "search_students", {"query": " "}, {"role": "student_records"})
    assert "error" in result
    assert conn.calls == []


def test_demo_search_is_scoped_to_demo_student_numbers():
    conn = FakeConnection()
    result = _tool_result(conn, "search_students", {"query": "Ben"}, {"role": "demo"})
    assert result == {"students": [], "count": 0}
    assert conn.calls
    assert "s.student_no ~ '^N0'" in conn.calls[0][0]
    assert conn.calls[0][1][-1] is True


def test_unknown_tool_is_rejected():
    conn = FakeConnection()
    result = _tool_result(conn, "run_sql", {"sql": "DROP TABLE students"}, {"role": "system_admin"})
    assert "error" in result
    assert conn.calls == []


def test_demo_student_count_is_scoped_to_demo_records():
    conn = FakeConnection()
    result = _tool_result(conn, "get_student_count", {}, {"role": "demo"})
    assert result == {"student_count": 12}
    assert "student_no ~ '^N0'" in conn.calls[0][0]
    assert conn.calls[0][1] == (True,)


def test_finance_role_cannot_get_student_count():
    conn = FakeConnection()
    result = _tool_result(conn, "get_student_count", {}, {"role": "finance"})
    assert "error" in result
    assert conn.calls == []
