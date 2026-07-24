from datetime import datetime
from typing import List, Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    users: Mapped[List["User"]] = relationship(back_populates="branch")
    inventories: Mapped[List["Inventory"]] = relationship(back_populates="branch")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="admin")

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=None, nullable=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("branches.id"), nullable=True
    )

    branch: Mapped[Optional["Branch"]] = relationship(back_populates="users")


class Inventory(Base):
    __tablename__ = "inventories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    branch: Mapped["Branch"] = relationship(back_populates="inventories")
