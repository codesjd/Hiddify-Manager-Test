import dataclasses
from collections.abc import Mapping

def _as_dto(x, DTO):
    return x if not isinstance(x, Mapping) else DTO(**{k: v for k, v in x.items() if k in {f.name for f in dataclasses.fields(DTO)}})

@dataclasses.dataclass
class AccountDTO:
    uuid: str
    name: str

print(_as_dto({'uuid': '123', 'name': 'test', 'extra': 'ignored'}, AccountDTO))
print(_as_dto(AccountDTO('456', 'obj'), AccountDTO))
