from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Technology(Base):
    __tablename__ = "technologies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
