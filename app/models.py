from datetime import date, datetime
from typing import Optional, List

from sqlmodel import SQLModel, Field, Relationship


class User(SQLModel, table=True):
    """Application user model."""

    id: Optional[int] = Field(default=None, primary_key=True)

    username: str = Field(index=True, unique=True)
    email: Optional[str] = Field(default=None, index=True)
    password_hash: str

    is_active: bool = Field(default=True)
    is_admin: bool = Field(default=False)

    servers: List["Server"] = Relationship(back_populates="owner")


class Server(SQLModel, table=True):
    """Server/VPS entry owned by a user."""

    id: Optional[int] = Field(default=None, primary_key=True)

    # Owner
    owner_id: int = Field(foreign_key="user.id")
    owner: Optional[User] = Relationship(back_populates="servers")

    # General info
    name: str
    hostname: Optional[str] = None
    type: str = "vps"  # vps, dedicated, storage, managed, other
    provider: str
    location: Optional[str] = None

    # Network
    ipv4: Optional[str] = None
    ipv6: Optional[str] = None

    # Cost / billing
    billing_period: str = "monthly"  # monthly, yearly, other
    price: float = 0.0
    currency: str = "EUR"
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    tags: Optional[str] = None  # e.g. "prod,critical,backup"

    # Hardware
    cpu_model: Optional[str] = None
    cpu_cores: Optional[int] = None
    ram_mb: Optional[int] = None
    storage_gb: Optional[int] = None
    storage_type: Optional[str] = None  # nvme, ssd, hdd, ceph, ...

    # Access (no private SSH keys, only hints)
    mgmt_url: Optional[str] = None
    mgmt_user: Optional[str] = None
    mgmt_password_encrypted: Optional[str] = None
    ssh_user: Optional[str] = None
    ssh_key_hint: Optional[str] = None  # e.g. "id_ed25519_ovh"

    notes: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    archived: bool = Field(default=False)

    # ----- Convenience properties for badges / UI -----

    @property
    def days_until_contract_end(self) -> Optional[int]:
        """
        Number of days until the contract_end date.

        Returns:
            int: positive or zero if in the future,
                 negative if already past,
                 None if no contract_end is set.
        """
        if not self.contract_end:
            return None
        return (self.contract_end - date.today()).days

    @property
    def is_expired(self) -> bool:
        """Return True if the contract_end date lies in the past."""
        return self.contract_end is not None and self.contract_end < date.today()

    @property
    def is_expiring_soon(self) -> bool:
        """
        Return True if the contract will end within the next 30 days.

        This is used for "expiring soon" badges in the UI.
        """
        days = self.days_until_contract_end
        return days is not None and 0 <= days <= 30
