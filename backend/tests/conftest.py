import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg2://vbt:vbt_dev@localhost:5432/vbt_accounts_test")
os.environ["UPLOAD_DIR"] = "/tmp/vbt-test-uploads"
os.environ["ENABLE_MANUAL_ENTRY"] = "true"

from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.deps import Actor  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.schemas import BankAccountIn, CompanyIn, ExpenseCategoryIn, PartyIn, PaymentTermIn, ProductIn  # noqa: E402
from app.services import masters  # noqa: E402
from app.services.bootstrap import ensure_fy, ensure_reference_data  # noqa: E402

PASSWORD = "Test@123456"


@pytest.fixture(scope="session", autouse=True)
def schema():
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture()
def db():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as c:
        c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    s = SessionLocal()
    ensure_reference_data(s)
    ensure_fy(s, 2025)
    ensure_fy(s, 2026, make_current=True)
    s.commit()
    yield s
    s.rollback()
    s.close()


def _user(db, username, role_code) -> User:
    role = db.scalar(select(Role).where(Role.code == role_code))
    u = User(full_name=username.title(), username=username, password_hash=hash_password(PASSWORD), role_id=role.id,
             must_change_password=False)
    db.add(u)
    db.flush()
    return u


class World:
    """A small company with one TN dealer, one Kerala dealer, a supplier, a product, bank and cash."""


@pytest.fixture()
def w(db):
    x = World()
    x.db = db
    x.admin = Actor(_user(db, "admin", "super_admin"))
    x.mgr = Actor(_user(db, "manager", "accounts_manager"))
    x.acct = Actor(_user(db, "accountant", "accountant"))
    x.ceo = Actor(_user(db, "ceo", "management"))
    x.auditor = Actor(_user(db, "auditor", "auditor"))
    masters.save_company(db, x.admin, CompanyIn(legal_name="Test Biotech Pvt Ltd", state_code="33",
                                                state_name="Tamil Nadu", gstin="33AADCV1234F1Z6"))
    t30 = masters.save_term(db, x.admin, PaymentTermIn(name="30 days", days=30))
    x.tn = masters.save_party(db, x.admin, PartyIn(code="D1", name="TN Dealer", is_customer=True, state_code="33",
                                                   state_name="Tamil Nadu", gstin="33AAPFM1234K1Z2",
                                                   payment_term_id=t30.id, credit_limit=Decimal("100000")))
    x.kl = masters.save_party(db, x.admin, PartyIn(code="D2", name="Kerala Dealer", is_customer=True,
                                                   state_code="32", state_name="Kerala", payment_term_id=t30.id))
    x.sup = masters.save_party(db, x.admin, PartyIn(code="S1", name="Supplier One", is_supplier=True,
                                                    state_code="33", state_name="Tamil Nadu", payment_term_id=t30.id))
    x.prod = masters.save_product(db, x.admin, ProductIn(code="P1", name="Azospirillum 1 L", hsn_code="3101",
                                                         unit="Ltr", gst_rate=Decimal("5"),
                                                         sale_price=Decimal("320")))
    x.bank = masters.save_bank(db, x.admin, BankAccountIn(name="Bank", kind="bank",
                                                          opening_balance=Decimal("100000"),
                                                          opening_date=date(2026, 4, 1)))
    x.cash = masters.save_bank(db, x.admin, BankAccountIn(name="Cash", kind="cash",
                                                          opening_balance=Decimal("5000"),
                                                          opening_date=date(2026, 4, 1)))
    x.cat = masters.save_category(db, x.admin, ExpenseCategoryIn(name="Travel"))
    db.commit()
    return x
