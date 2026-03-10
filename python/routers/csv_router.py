import asyncio
import io
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
import aiofiles
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from config import settings
from database import get_db
from routers.auth_router import get_current_user   # remove Depends() to make auth optional

router = APIRouter()

MAX_BYTES = settings.max_upload_mb * 1024 * 1024
CHUNK = settings.chunk_size

# Response schemas
class DataSeries(BaseModel):
    name: str
    data: List[Dict[str, Any]]   # [{x: ..., y: ...}, ...]

class CSVResult(BaseModel):
    upload_id: str
    filename: str
    row_count: int
    col_count: int
    columns: List[str]
    dtypes: Dict[str, str]
    sample_rows: List[Dict[str, Any]]
    numeric_summary: Dict[str, Any]
    data_series: List[DataSeries]   # ready for Recharts / Chart.js
    category_series: Optional[List[DataSeries]] = None
    processed_at: str

# Upload endpoint
@router.post("/upload", status_code=202)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    # current_user: dict = Depends(get_current_user),
):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files accepted")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {settings.max_upload_mb} MB.",
        )

    upload_id = str(uuid.uuid4())
    dest = os.path.join(settings.upload_dir, f"{upload_id}.csv")

    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    db = get_db()
    meta = {
        "upload_id": upload_id,
        "filename": file.filename,
        "size_bytes": len(content),
        # "user_id": current_user["user_id"],  # enable with auth
        "status": "queued",
        "progress_pct": 0,
        "created_at": datetime.utcnow(),
    }
    await db.csv_metadata.insert_one(meta)

    background_tasks.add_task(_process_csv, upload_id, dest, file.filename)

    return {"upload_id": upload_id, "status": "queued", "filename": file.filename}

# Status polling
@router.get("/status/{upload_id}")
async def get_status(upload_id: str):
    db = get_db()
    doc = await db.csv_metadata.find_one({"upload_id": upload_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Upload not found")
    return {
        "upload_id": upload_id,
        "status": doc["status"],
        "progress_pct": doc.get("progress_pct", 0),
        "error": doc.get("error"),
    }


# Retrieve chart-ready result
@router.get("/result/{upload_id}", response_model=CSVResult)
async def get_result(upload_id: str):
    db = get_db()
    result = await db.processing_results.find_one({"upload_id": upload_id}, {"_id": 0})
    if not result:
        meta = await db.csv_metadata.find_one({"upload_id": upload_id})
        if not meta:
            raise HTTPException(status_code=404, detail="Upload not found")
        status = meta.get("status", "unknown")
        raise HTTPException(status_code=202, detail=f"Processing status: {status}")
    return result

# Delete
@router.delete("/{upload_id}", status_code=204)
async def delete_upload(upload_id: str):
    db = get_db()
    await db.csv_metadata.delete_one({"upload_id": upload_id})
    await db.processing_results.delete_one({"upload_id": upload_id})
    path = os.path.join(settings.upload_dir, f"{upload_id}.csv")
    if os.path.exists(path):
        os.remove(path)

# Background processing
async def _process_csv(upload_id: str, filepath: str, filename: str):
    """
    Background task to process the CSV.
    Runs in the main event loop provided by FastAPI BackgroundTasks.
    Heavy pandas operations are offloaded to threads using asyncio.to_thread.
    """
    await _async_process(upload_id, filepath, filename)

async def _async_process(upload_id: str, filepath: str, filename: str):
    from database import get_db
    db = get_db()

    async def _update(status: str, pct: int, extra: dict = {}):
        await db.csv_metadata.update_one(
            {"upload_id": upload_id},
            {"$set": {"status": status, "progress_pct": pct, **extra}},
        )

    try:
        await _update("processing", 5)

        # ── Phase 1: count rows & collect column info via chunked read ────────
        # We run the chunked reading in a thread to avoid blocking
        def _read_chunks():
            total_rows = 0
            chunks_data = []
            reader = pd.read_csv(filepath, chunksize=CHUNK, low_memory=False)
            for i, chunk in enumerate(reader):
                # Coerce obvious date columns
                for col in chunk.columns:
                    if "date" in col.lower() or "time" in col.lower():
                        try:
                            chunk[col] = pd.to_datetime(chunk[col], errors="coerce")
                        except Exception:
                            pass
                chunks_data.append(chunk)
                total_rows += len(chunk)
            return chunks_data, total_rows

        chunks_data, total_rows = await asyncio.to_thread(_read_chunks)
        await _update("processing", 50)

        # ── Phase 2: concatenate and derive chart payload (in thread) ────────
        def _compute_results(chunks, rows):
            df: pd.DataFrame = pd.concat(chunks, ignore_index=True)
            col_names = list(df.columns)
            col_dtypes = {c: str(df[c].dtype) for c in df.columns}

            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            datetime_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
            categorical_cols = [
                c for c in df.select_dtypes(include=["object", "category"]).columns
                if df[c].nunique() <= 50
            ]

            numeric_summary = {}
            if numeric_cols:
                desc = df[numeric_cols].describe().to_dict()
                numeric_summary = {
                    col: {k: _safe(v) for k, v in stats.items()}
                    for col, stats in desc.items()
                }

            data_series = []
            x_axis = datetime_cols[0] if datetime_cols else None
            MAX_POINTS = 500
            plot_df = df.sample(MAX_POINTS).sort_values(x_axis) if x_axis and len(df) > MAX_POINTS else (df.iloc[::max(1, len(df)//MAX_POINTS)] if len(df) > MAX_POINTS else df)

            for num_col in numeric_cols[:8]:
                if x_axis:
                    series_data = [
                        {"x": _fmt_x(row[x_axis]), "y": _safe(row[num_col])}
                        for _, row in plot_df[[x_axis, num_col]].dropna().iterrows()
                    ]
                else:
                    series_data = [
                        {"x": idx, "y": _safe(val)}
                        for idx, val in enumerate(plot_df[num_col].dropna().tolist())
                    ]
                data_series.append({"name": num_col, "data": series_data})

            category_series = []
            for cat_col in categorical_cols[:4]:
                counts = df[cat_col].value_counts().head(20)
                category_series.append({
                    "name": cat_col,
                    "data": [{"x": str(k), "y": int(v)} for k, v in counts.items()],
                })

            sample_rows = df.head(10).where(pd.notnull(df), None).to_dict(orient="records")
            sample_rows = [{k: _safe(v) for k, v in row.items()} for row in sample_rows]

            return {
                "upload_id": upload_id,
                "filename": filename,
                "row_count": rows,
                "col_count": len(col_names),
                "columns": col_names,
                "dtypes": col_dtypes,
                "sample_rows": sample_rows,
                "numeric_summary": numeric_summary,
                "data_series": data_series,
                "category_series": category_series,
                "processed_at": datetime.utcnow().isoformat(),
            }

        result_doc = await asyncio.to_thread(_compute_results, chunks_data, total_rows)

        await db.processing_results.replace_one(
            {"upload_id": upload_id}, result_doc, upsert=True
        )
        await _update("complete", 100)

    except Exception as exc:
        await _update("error", 0, {"error": str(exc)})
        raise

# Helpers
def _safe(v):
    """Convert numpy/pandas scalars to JSON-safe Python types."""
    import math
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    if hasattr(v, "item"):          # numpy scalar
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return v

def _fmt_x(v):
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    return _safe(v)