from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_nsid: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")

    taken_at: Mapped[datetime | None] = mapped_column(index=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(index=True)
    last_updated: Mapped[datetime | None]

    is_public: Mapped[bool] = mapped_column(default=False)
    is_friend: Mapped[bool] = mapped_column(default=False)
    is_family: Mapped[bool] = mapped_column(default=False)

    url_t: Mapped[str | None]
    url_m: Mapped[str | None]
    url_l: Mapped[str | None]
    url_o: Mapped[str | None]
    width_o: Mapped[int | None]
    height_o: Mapped[int | None]

    views: Mapped[int | None]
    count_faves: Mapped[int | None]
    count_comments: Mapped[int | None]

    info_synced_at: Mapped[datetime | None]
    exif_synced_at: Mapped[datetime | None]
    sync_status: Mapped[str] = mapped_column(String, default="pending", index=True)
    sync_error: Mapped[str | None]


class Exif(Base):
    __tablename__ = "exif"

    photo_id: Mapped[str] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True
    )
    tagspace: Mapped[str] = mapped_column(String, primary_key=True)
    tag: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[str] = mapped_column(Text, default="")
    clean_num: Mapped[float | None] = mapped_column(Float)
    clean_str: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_exif_tag_num", "tag", "clean_num"),
        Index("ix_exif_tag_str", "tag", "clean_str"),
    )


class PhotoTag(Base):
    __tablename__ = "photo_tags"

    photo_id: Mapped[str] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String, primary_key=True)
    raw: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (Index("ix_photo_tags_tag", "tag"),)


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None]


class SyncQueue(Base):
    __tablename__ = "sync_queue"

    photo_id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None]
    enqueued_at: Mapped[datetime]


class Download(Base):
    __tablename__ = "downloads"

    photo_id: Mapped[str] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True
    )
    size: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "Original"
    path: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[str] = mapped_column(Text)
    downloaded_at: Mapped[datetime]


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
