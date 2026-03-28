from pydantic import BaseModel, Field

# Wir benötigen hier aktuell eventuell gar keine Pydantic Modelle,
# da wir die Parameter direkt in den Tools als primitive Typen definieren.
# Falls wir komplexe Payloads an das Web-UI schicken, können wir sie hier definieren.

class IonosRecordCreate(BaseModel):
    name: str
    type: str
    content: str
    ttl: int = 3600
    prio: int | None = None
    disabled: bool = False
