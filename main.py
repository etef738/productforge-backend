from main_refactored import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main_refactored:app", host="0.0.0.0", port=8000, reload=True)
