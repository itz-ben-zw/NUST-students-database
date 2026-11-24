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

def test_student_assistant_can_only_query_its_linked_student_id():
    conn = FakeConnection(rows=[{
        "student_no": "N000001Y", "first_name": "Demo", "last_name": "Student",
        "status": "Registered", "programme": "Informatics", "faculty": "Computing",
        "invoice_no": "INV-1", "issued_on": "2026-01-01", "due_on": "2026-02-01",
        "academic_year": "2026", "semester_number": 1, "currency": "USD",
        "billed_cents": 10000, "paid_cents": 2500,
    }])
    result = _tool_result(conn, "get_my_student_account", {}, {
        "role": "student", "student_id": 42,
    })
    assert result["student"]["student_number"] == "N000001Y"
    assert result["accounts"][0]["outstanding_cents"] == 7500
    assert "WHERE s.id = %s" in conn.calls[0][0]
    assert conn.calls[0][1] == (42,)


def test_student_assistant_rejects_missing_verified_student_id():
    conn = FakeConnection()
    result = _tool_result(conn, "get_my_student_account", {}, {"role": "student"})
    assert "error" in result
    assert conn.calls == []


def test_student_role_cannot_use_employee_wide_student_search():
    conn = FakeConnection()
    result = _tool_result(conn, "search_students", {"query": "someone"}, {
        "role": "student", "student_id": 42,
    })
    assert "error" in result
    assert conn.calls == []
