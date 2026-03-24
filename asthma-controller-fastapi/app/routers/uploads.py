from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
import pandas as pd
import shutil
import os
from sqlalchemy.orm import Session
from models import crud
from models.database import get_db

router = APIRouter()
uploads_tag = "File Uploads"


@router.post("/upload/", tags=[uploads_tag])
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith((".csv", ".xls", ".xlsx")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload a CSV or Excel file.",
        )

    file_path = f"uploads/{file.filename}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        if file.filename.endswith(".csv"):
            data = pd.read_csv(file_path)
        else:
            data = pd.read_excel(file_path)

        # Process the data and save to the database
        # This part will depend on your specific implementation in crud.py
        await crud.save_data(data, db)

        return {"message": "File uploaded and data processed successfully."}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"An error occurred while processing the file: {e}"
        )
    finally:
        os.remove(file_path)  # Clean up the uploaded file after processing
