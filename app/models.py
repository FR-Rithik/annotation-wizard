from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ApiClient(Base):
    __tablename__ = "api_clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    key_hash = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    client_id = Column(Integer, ForeignKey("api_clients.id"), nullable=False)


class AccessRequest(Base):
    __tablename__ = "access_requests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    organization = Column(String(100), nullable=True)
    intended_use = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DatasetJob(Base):
    __tablename__ = "dataset_jobs"

    id = Column(String(64), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    client_id = Column(Integer, ForeignKey("api_clients.id"), nullable=True)
    status = Column(String(50), default="ready_for_review")
    total_images = Column(Integer, default=0)
    reviewed_images = Column(Integer, default=0)
    total_annotations = Column(Integer, default=0)
    storage_dir = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    images = relationship("DatasetImage", back_populates="job", cascade="all, delete-orphan", order_by="DatasetImage.order_index")
    client = relationship("ApiClient")


class DatasetImage(Base):
    __tablename__ = "dataset_images"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String(64), ForeignKey("dataset_jobs.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    relative_path = Column(String(500), nullable=False)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    status = Column(String(50), default="not_reviewed")
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("DatasetJob", back_populates="images")
    annotations = relationship("Annotation", back_populates="image", cascade="all, delete-orphan", order_by="Annotation.id")


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey("dataset_images.id"), nullable=False, index=True)
    class_id = Column(Integer, nullable=False)
    class_name = Column(String(50), nullable=False)
    x_min = Column(Float, nullable=False)
    y_min = Column(Float, nullable=False)
    x_max = Column(Float, nullable=False)
    y_max = Column(Float, nullable=False)
    confidence = Column(Float, nullable=True)
    is_prediction = Column(Boolean, default=True)
    is_modified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    image = relationship("DatasetImage", back_populates="annotations")

