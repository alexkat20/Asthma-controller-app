import socket
import time
import uuid

from repositories import database as db
from repositories import scheduler_lock_repository as lock_repo
from repositories.database import init_db
from services import act_service
from services.reminder_service import check_reminders

CHECK_INTERVAL_SECONDS = 60
LOCK_LEASE_SECONDS = 90

HOLDER_ID = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"


def _run_one_tick() -> None:
    try:
        check_reminders()
    except Exception as exc:
        print(f"[scheduler] ошибка (напоминания): {exc}")
    try:
        act_service.check_and_notify_due_users()
    except Exception as exc:
        print(f"[scheduler] ошибка (ACT): {exc}")


def main() -> None:
    init_db()
    print(f"[scheduler] запущен, holder_id={HOLDER_ID}, интервал={CHECK_INTERVAL_SECONDS}с")

    while True:
        conn = db.get_connection()
        try:
            got_lock = lock_repo.try_acquire(conn, HOLDER_ID, LOCK_LEASE_SECONDS)
        finally:
            conn.close()

        if got_lock:
            _run_one_tick()
        else:
            print("[scheduler] лок занят другим экземпляром — пропускаю этот тик")

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
