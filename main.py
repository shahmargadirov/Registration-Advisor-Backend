from fastapi import FastAPI

from routes.upload import router as upload_router
from routes.schedule_upload import router as schedule_upload_router
from routes.swap import router as swap_router
from routes.confirm import router as confirm_router
from services.wp_api import get_all_classes

# The app runs without OpenAI. Scheduling uses local rules by default.
# If OPENAI_API_KEY is set later, /upload can optionally use AI.

app = FastAPI()# This is your server instance
app.include_router(upload_router)# This connects /upload to your app
app.include_router(schedule_upload_router)
app.include_router(swap_router)# takes all endpoints inside swap_router and attach them to the main app
app.include_router(confirm_router)


@app.get("/")
def root():
    return {"message": "Backend"}

if __name__ == "__main__":
    classes = get_all_classes(page_max_size=10)

    print("Total classes returned:", len(classes))

    for course in classes[:3]:
        print(course)
        print("-" * 50)


