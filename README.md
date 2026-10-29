# REGI Backend Split Version

This is your FastAPI backend separated into related files.

## How to run

From inside this folder:

```bash
uvicorn main:app --reload
```

## File map

```text
main.py                         Starts FastAPI and connects routes
config.py                       dotenv, JSON file paths
state.py                        Shared candidates_store for swaps

routes/upload.py                /upload Degree Works PDF endpoint
routes/schedule_upload.py       /upload-schedule Banner schedule PDF endpoint
routes/swap.py                  /swap-options and /swap endpoints
routes/confirm.py               /confirm-schedule save/load endpoints

services/degreeworks_parser.py  Parses Degree Works text
services/section_loader.py      Loads JSON schedule files and builds section objects
services/ucc.py                 UCC area detection and UCC requirement parsing
services/course_rules.py        Prerequisite/restriction/major logic
services/schedule_logic.py      Time conflicts, swaps, filling schedules
services/ai_scheduler.py        Optional OpenAI schedule picking (skipped without a key)

data/prereqs.py                 Your manual prerequisite/restriction dictionary

utils/normalize.py              normalize() helper
utils/pdf_utils.py              PDF text extraction helper
```

## Important fix

Your original confirm endpoint had this:

```python
@app.post("https://shifter-gorgeous-onlooker.ngrok-free.dev/confirm-schedule")
```

FastAPI routes should be path-only, so it is now:

```python
@router.post("/confirm-schedule")
```

Your Swift app can still call the full ngrok URL:

```text
https://shifter-gorgeous-onlooker.ngrok-free.dev/confirm-schedule
```
