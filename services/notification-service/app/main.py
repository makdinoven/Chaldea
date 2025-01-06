from fastapi import FastAPI
from consumers.user_registration import start as start_user_registration_consumer
import models
from database import engine

app = FastAPI()

models.Base.metadata.create_all(bind=engine)

@app.on_event("startup")
async def startup_event():
    # Запускаем consumer для очереди `user_registration`
    start_user_registration_consumer()

@app.get("/")
def health_check():
    return {"status": "Notification Service is running"}