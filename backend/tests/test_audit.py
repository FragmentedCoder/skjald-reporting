import multiprocessing

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.audit import GENESIS_HASH, AuditEntry, ChainCheck, _hash, append, verify
from app.db import make_engine


def _append_three(session):
    for action in ("auth.sign_in.succeeded", "customer.created", "auth.sign_out"):
        append(session, action, actor_id=1, actor_name="astrid")
    session.commit()


def _tamper(engine, *statements, params=None):
    """Do what an attacker with the database key could: drop the guards and edit."""
    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER audit_log_no_update"))
        conn.execute(text("DROP TRIGGER audit_log_no_delete"))
        for statement in statements:
            conn.execute(text(statement), params or {})


def test_entries_link_into_one_chain(session) -> None:
    first = append(session, "auth.sign_in.succeeded", actor_id=1, ip="10.0.0.5")
    second = append(
        session,
        "customer.created",
        actor_id=1,
        target_type="customer",
        target_id="7",
        details={"name": "Fjordvik Logistik A/S"},
    )
    session.commit()

    assert (first.seq, second.seq) == (1, 2)
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.hash
    assert verify(session) == ChainCheck(True, 2)


def test_details_are_stored_in_one_canonical_form(session) -> None:
    entry = append(session, "customer.created", details={"b": 1, "a": "Ærø"})
    assert entry.details == '{"a":"Ærø","b":1}'


def test_an_entry_rolls_back_with_the_action_it_records(session) -> None:
    append(session, "customer.created")
    session.rollback()
    assert session.scalar(select(func.count()).select_from(AuditEntry)) == 0


def test_the_database_refuses_edits(engine, session) -> None:
    _append_three(session)
    with engine.connect() as conn, pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("UPDATE audit_log SET action = 'nothing.happened'"))


def test_the_database_refuses_deletes(engine, session) -> None:
    _append_three(session)
    with engine.connect() as conn, pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text("DELETE FROM audit_log"))


def test_verify_catches_an_edited_entry(engine, session) -> None:
    _append_three(session)
    _tamper(engine, "UPDATE audit_log SET actor_name = 'someone else' WHERE seq = 2")
    assert verify(session) == ChainCheck(False, 1, 2, "it was changed after it was written")


def test_verify_catches_an_edited_entry_whose_hash_was_recomputed(engine, session) -> None:
    _append_three(session)
    row = session.execute(select(AuditEntry.__table__).where(AuditEntry.seq == 2)).one()
    forged = {**row._mapping, "action": "nothing.happened"}
    session.rollback()
    _tamper(
        engine,
        "UPDATE audit_log SET action = :action, hash = :hash WHERE seq = 2",
        params={"action": forged["action"], "hash": _hash(forged)},
    )
    assert verify(session) == ChainCheck(
        False, 2, 3, "it does not link to the entry before it"
    )


def test_verify_catches_a_removed_entry(engine, session) -> None:
    _append_three(session)
    _tamper(engine, "DELETE FROM audit_log WHERE seq = 2")
    assert verify(session) == ChainCheck(False, 1, 2, "the entry is missing")


def _append_many(data_dir, master_key_path, worker, count):
    engine = make_engine(data_dir, master_key_path)
    with Session(engine) as session:
        for i in range(count):
            append(session, "test.concurrent", details={"worker": worker, "i": i})
            session.commit()
    engine.dispose()


def test_processes_appending_at_once_keep_one_unbroken_chain(
    engine, data_dir, master_key_path
) -> None:
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        pool.starmap(_append_many, [(data_dir, master_key_path, w, 50) for w in range(4)])
    with Session(engine) as session:
        assert verify(session) == ChainCheck(True, 200)
