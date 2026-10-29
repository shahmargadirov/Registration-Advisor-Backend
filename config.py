from pathlib import Path#paths is a modern way to work with filepaths
from dotenv import load_dotenv#this laods environment variable form .env file


load_dotenv()# This loads variable from the .en file into your environment

PAGES_DIR = Path("/Users/ace/Desktop/Registration Advisor(Randi)/Registration Advisor(Randi)/pages")#creates a path object point to your pages folder

FALL_FILES = [
    PAGES_DIR / "page1.json",
    PAGES_DIR / "page2.json",
    PAGES_DIR / "page3.json",
    PAGES_DIR / "page4.json",
    PAGES_DIR / "page5.json",
]

SPRING_FILES = [
    PAGES_DIR / "spring1.json",
    PAGES_DIR / "spring2.json",
    PAGES_DIR / "spring3.json",
    PAGES_DIR / "spring4.json",
    PAGES_DIR / "spring5.json",
]

SAVE_DIR = Path("saved_students")#Creates a path object for a folder named saved_students
