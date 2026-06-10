from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text

from app.core.database import Base


class DatasetItem(Base):
    __tablename__ = "dataset_items"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=True)
    external_id = Column(String(128), nullable=True)
    dataset_type = Column(String(32), nullable=False)
    raw_data_json = Column(JSON, nullable=False)
    hidden_reference_json = Column(JSON, nullable=True)
    status = Column(String(32), nullable=False)
    claimed_by = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    item_key = Column(String(128), nullable=True)
    pack_id = Column(String(64), nullable=True)
    is_valid = Column(Boolean, nullable=True, default=True)
    is_first_annotated = Column(Boolean, nullable=True, default=False)
    category = Column(String(64), nullable=True)
    supplier = Column(String(64), nullable=True)
    invalid_reason = Column(String(256), nullable=True)
    annotation_phase = Column(String(32), nullable=True)
    phase_status = Column(String(32), nullable=True)
    qc_status = Column(String(32), nullable=True)
    round_no = Column(Integer, nullable=True, default=1)
    total_rounds = Column(Integer, nullable=True, default=1)
    skipped_by = Column(Integer, nullable=True)

    # --- 官方数据集导入字段 ---
    source_namespace = Column(String(64), nullable=True)
    source_file = Column(String(256), nullable=True)
    source_zip_sha256 = Column(String(64), nullable=True)
    raw_payload = Column(JSON, nullable=True)
    raw_payload_sha256 = Column(String(64), nullable=True)
    is_official_raw = Column(Boolean, nullable=True, default=False)
    gold_payload = Column(JSON, nullable=True)
    official_id = Column(String(64), nullable=True)
