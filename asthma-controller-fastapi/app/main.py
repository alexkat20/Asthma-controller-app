from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import readings, medicine, users, uploads
import uvicorn

app = FastAPI(
    title="Asthma Controller API",
    description="API for managing asthma-related data, including user profiles, medication, and peak flow readings.",
    version="1.0.0",
    docs_url="/docs",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(readings.router)
app.include_router(medicine.router)
app.include_router(users.router)
app.include_router(uploads.router)


@app.get("/")
async def root():
    return {"message": "Welcome to the Asthma Controller API"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
