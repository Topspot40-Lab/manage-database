from fastapi import APIRouter, HTTPException, Path, Query
import os
import json

router = APIRouter()

# Define the directory where files are saved
SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "json_files", "genredecade")

@router.get("/saved-files")
def list_saved_files():
    try:
        decade_dirs = os.listdir(SAVE_DIR)
        all_files = []
        for decade in decade_dirs:
            decade_path = os.path.join(SAVE_DIR, decade)
            if os.path.isdir(decade_path):
                for f in os.listdir(decade_path):
                    if f.endswith(".json"):
                        all_files.append(f"{decade}/{f}")
        return all_files
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing files: {e}")

@router.get("/saved-files/{decade}/{filename}")
def get_saved_file(
    decade: str = Path(..., description="Decade folder name, e.g. '1960s'"),
    filename: str = Path(..., description="JSON filename, e.g. 'rock_1960s.json'")
):
    filepath = os.path.join(SAVE_DIR, decade, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")

@router.delete("/saved-files/{decade}/{filename}")
def delete_saved_file(
    decade: str = Path(..., description="Decade folder name"),
    filename: str = Path(..., description="File to delete")
):
    filepath = os.path.join(SAVE_DIR, decade, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(filepath)
        return {"message": f"{filename} deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting file: {e}")

@router.put("/saved-files/rename/{decade}/{old_filename}")
def rename_saved_file(
    decade: str = Path(..., description="Decade folder name"),
    old_filename: str = Path(..., description="Current file name"),
    new_filename: str = Query(..., description="New name for the file")
):
    old_path = os.path.join(SAVE_DIR, decade, old_filename)
    new_path = os.path.join(SAVE_DIR, decade, new_filename)

    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="Original file not found")
    if os.path.exists(new_path):
        raise HTTPException(status_code=400, detail="New filename already exists")

    try:
        os.rename(old_path, new_path)
        return {"message": f"File renamed to {new_filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error renaming file: {e}")
