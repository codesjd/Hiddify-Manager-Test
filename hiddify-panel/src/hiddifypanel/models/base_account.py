import datetime
import uuid
from hiddifypanel.models.role import Role
from sqlalchemy import Column, String, BigInteger, Enum

from flask_login import UserMixin as FlaskLoginUserMixin
from hiddifypanel.models import Lang
from hiddifypanel.database import db
from werkzeug.security import generate_password_hash, check_password_hash
import hmac



class BaseAccount(db.Model, FlaskLoginUserMixin):  # type: ignore
    __abstract__ = True
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), nullable=False, unique=True, index=True)
    name = Column(String(512), nullable=False, default='')
    username = Column(String(100), nullable=True, default='', index=True)
    # werkzeug's default scrypt hash is a fixed 162 chars - 255 leaves
    # headroom for other hash methods without another migration.
    password = Column(String(255), nullable=True, default='')
    comment = Column(String(512), nullable=True, default='')
    telegram_id = Column(BigInteger, nullable=True, default=None, index=True)
    lang = Column(Enum(Lang), default=None)

    @property
    def role(self) -> Role | None:
        return None

    def get_id(self) -> str | None:
        return f'{self.__class__.__name__}_{self.id if hasattr(self, "id") else "-"}'

    def is_username_unique(self) -> bool:
        # cls must be the CLASS, not an instance: self.__class__() would make
        # cls.username / cls.id resolve to a fresh empty instance's attribute
        # *values* instead of the mapped Columns, so the filter compared
        # python literals ('' == 'admin2' -> False) and matched nothing,
        # making this always report "unique" (the reason duplicate admin
        # usernames slipped through, and why gen_username never detected a
        # collision).
        cls = self.__class__
        # no_autoflush: on create, flask-admin's create_model() does
        # session.add(model) *before* calling on_model_change (which calls
        # this). self.id is None when `cls.id != self.id` is built (captured
        # eagerly, becoming "id IS NOT NULL" in SQL), but running this query
        # would otherwise trigger autoflush, which INSERTs this same
        # not-yet-committed row and assigns it a real id - so the exclusion
        # no longer excludes it, and the row matches itself as a "duplicate"
        # (every new admin was rejected, regardless of username, until this
        # was added). Suppressing autoflush here keeps the row unflushed
        # (id still None) for the duration of this check.
        with db.session.no_autoflush:
            model = cls.query.filter(cls.username == self.username, cls.id != self.id).first()
        if model:
            return False
        return True

    def to_dict(self, convert_date=True) -> dict:
        return {
            'name': self.name,
            'comment': self.comment,
            'uuid': self.uuid,
            'telegram_id': self.telegram_id,
            'lang': self.lang
        }
    def update_password(self,new_password):
        self.password = generate_password_hash(new_password)
        db.session.commit()

    @classmethod
    def by_id(cls, id: int):
        # return cls.query.filter(cls.id == id).first()
        return db.session.query(cls).get(id)

    @classmethod
    def by_uuid(cls, uuid: str, create: bool = False):
        if not isinstance(uuid, str):
            uuid = str(uuid)
        account = cls.query.filter(cls.uuid == uuid).first()
        if not account and create:
            raise NotImplementedError
        return account

    @classmethod
    def by_username_password(cls, username: str, password: str):
        account = cls.query.filter(cls.username == username).first()
        if not account:
            return None

        if account.password and (account.password.startswith("scrypt:") or account.password.startswith("pbkdf2:")):
            if check_password_hash(account.password, password):
                return account
        elif account.password:
            # Legacy plaintext password only - an account with no password
            # set yet (account.password falsy) must never be logged into
            # via username/password, since hmac.compare_digest("", "")
            # would otherwise let a blank submission match a blank password.
            if hmac.compare_digest(account.password, password or ""):
                if password:
                    account.update_password(password)
                return account
        return None

    @classmethod
    def get_dto_class(cls):
        from hiddifypanel.models.dto import BaseAccountDTO, UserDTO, AdminUserDTO
        if cls.__name__ == 'User': return UserDTO
        if cls.__name__ == 'AdminUser': return AdminUserDTO
        return BaseAccountDTO

    @classmethod
    def add_or_update(cls, commit: bool = True, old_uuid=None, _dto=None, **data):
        from hiddifypanel.models.dto import _as_dto
        u = _dto or _as_dto(data, cls.get_dto_class())
        uuid_val = u.uuid if _dto else data.get('uuid')
        db_account: BaseAccount = cls.by_uuid(old_uuid or uuid_val, create=True)
        from hiddifypanel import hutils
        if hutils.auth.is_uuid_valid(uuid_val):
            db_account.uuid = uuid_val

        if _dto or 'name' in data:
            val = u.name if _dto else data.get('name')
            if val is not None:
                db_account.name = val

        if _dto or 'comment' in data:
            val = u.comment if _dto else data.get('comment')
            if val is not None:
                db_account.comment = val
        if _dto or 'telegram_id' in data:
            val = u.telegram_id if _dto else data.get('telegram_id')
            if val is not None:
                db_account.telegram_id = hutils.convert.to_int(val)
        if _dto or 'lang' in data:
            val = u.lang if _dto else data.get('lang')
            if val is not None:
                db_account.lang = val
        if commit:
            db.session.commit()  # type: ignore
        return db_account

    @classmethod
    def bulk_register(cls, accounts: list = [], commit: bool = True, remove: bool = False):
        from hiddifypanel.models.dto import _as_dto
        accounts = [_as_dto(u, cls.get_dto_class()) for u in accounts]
        for u in accounts:
            cls.add_or_update(commit=False, _dto=u)
        if remove:
            dd = {str(u.uuid): 1 for u in accounts}
            for d in cls.query.all():
                if d.uuid not in dd:
                    db.session.delete(d)  # type: ignore
        if commit:
            db.session.commit()  # type: ignore
