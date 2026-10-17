"""
Updates eval_runs 9, 10, 11 status to 'dry_run'.
"""
from backend.app.db.session import SessionLocal
from sqlalchemy import text

def main():
    session = SessionLocal()
    try:
        rows_before = session.execute(
            text("SELECT id, run_name, status, git_commit FROM eval_runs WHERE id IN (9, 10, 11) ORDER BY id")
        ).fetchall()
        print("Before update:")
        for r in rows_before:
            print(f"  id={r[0]} run_name={r[1]} status={r[2]} git_commit={r[3]}")
            
        session.execute(
            text("UPDATE eval_runs SET status = 'dry_run' WHERE id IN (9, 10, 11)")
        )
        session.commit()
        
        rows_after = session.execute(
            text("SELECT id, run_name, status, git_commit FROM eval_runs WHERE id IN (9, 10, 11) ORDER BY id")
        ).fetchall()
        print("After update:")
        for r in rows_after:
            print(f"  id={r[0]} run_name={r[1]} status={r[2]} git_commit={r[3]}")
    finally:
        session.close()

if __name__ == "__main__":
    main()
