from pydantic import BaseModel, Field
from typing import Optional, List

class SendEmailRequest(BaseModel):
    to: str = Field(..., description="Die E-Mail Adresse des Empfängers")
    subject: str = Field(..., description="Der Betreff der E-Mail")
    body: str = Field(..., description="Der Textkörper der E-Mail (HTML oder Plain Text)")
    cc: Optional[str] = Field(None, description="Optional: CC Empfänger (kommasepariert)")
    bcc: Optional[str] = Field(None, description="Optional: BCC Empfänger (kommasepariert)")
    is_html: bool = Field(True, description="True, wenn der Body als HTML interpretiert werden soll")
    attachments: Optional[List[str]] = Field(None, description="Optional: Liste von Dateipfaden auf dem Server, die als Anhänge beigefügt werden sollen")

class FilterEmailRequest(BaseModel):
    folder: str = Field("INBOX", description="Der Name des IMAP-Standardordners")
    limit: int = Field(10, description="Anzahl an E-Mails, die maximal abgerufen werden")
    query: str = Field("ALL", description="IMAP SEARCH String (z.B. 'UNSEEN', 'FROM \"chef\"')", example="UNSEEN")

class MoveEmailRequest(BaseModel):
    uid: str = Field(..., description="Die IMAP UID der E-Mail, die verschoben werden soll")
    source_folder: str = Field(..., description="Der Quell-Ordner (z.B. 'INBOX')")
    dest_folder: str = Field(..., description="Der Ziel-Ordner (z.B. 'Archiv')")

class DeleteEmailRequest(BaseModel):
    uid: str = Field(..., description="Die IMAP UID der E-Mail")
    folder: str = Field(..., description="Der Ordner, in dem sich die E-Mail befindet")
    hard_delete: bool = Field(False, description="Wenn True, wird das \\Deleted Flag direkt gesetzt und expunged. Wenn False, landets im Papierkorb (Move-Befehl).")
