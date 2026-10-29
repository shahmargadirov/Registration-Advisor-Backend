from collections import defaultdict# Like a normal dicitonary but will also have a default of 0 so it will never raise a valueError

from fastapi import APIRouter, Request# APIRouter lets you creat endpoints. Request lets you read incoming data like a pdf

import state# review state file
from config import FALL_FILES#List of json files
from data.prereqs import PREREQS#Dictionary of prerequisites
from services.ai_scheduler import choose_schedule_with_ai# optional; unused unless OPENAI_API_KEY is set
from services.course_rules import (
    candidate_type_for_course,# checks course type
    prereqs_satisfied,# checks prereqs
    restriction_satisfied,#checks restriction
)
from services.degreeworks_parser import parse_degreeworks_text # Converts PDF into strcutre student data
from services.schedule_logic.DegreeWorks_builder_backup_inCaseAIFails import (# This is yourfallback schedule builder WHAT DO YOU MEAN
    fill_remaining_schedule,
    pick_schedule,
)

from services.schedule_logic.ai_helpers import shrink_candidates_for_ai# Reduce candidates before sending to ai

from services.schedule_logic.reasons import attach_reasons# Add reason to each class

from services.JSON_class_section_formatter import (#Load banner json data
    build_section_database,
    load_json_files,
)
from services.ucc import find_ucc_area_from_section, make_find_ucc_area # It maps classes
from utils.normalize import normalize
from utils.pdf_utils import extract_pdf_text # converts pdf to text
from utils.restrictions import build_crn_rule_lookup # builds rules for restrictions
from utils.modality import modality_matches_preference# FIlter online vs in person


router = APIRouter() # Create route group for this file

# schedule is clean_schedule and clean_schedule is the  filter version of final schedule
# ucc_area_remaining is rules about how many UCC classes are you still need

def enforce_priority(schedule, ucc_area_remaining):# here you prioritize major courses first
    # enforce_schedule is splitting schedule into majors and ucc, adds majors first(max 4)
    # add UCCS but only if used_ucc_area_count < ucc_area_remaining
    majors = []
    uccs = []

    for item in schedule:
        if item.get("type") == "MAJOR":
            majors.append(item)
        else:
            uccs.append(item)

    result = [] # Create the final schudle list that this function will return
    used_codes = set()#Creates a set to track course codes already added
    used_ucc_area_count = defaultdict(int)#Creates a dictionary that automatically start at 0

    for item in majors:# loops through all major classes first
        code = str(item.get("course_code"))

        if code in used_codes:#Checks if this course code was already added
            continue

        result.append(item)
        used_codes.add(code)

        if len(result) == 4:#stopping adding majors once you have 4
            break

    for item in uccs:
        code = str(item.get("course_code"))#gets course code
        area = item.get("ucc_area")#gets UCC area

        if code in used_codes: # skips if course was alreayd added
            continue

        if area:#only run this block if the class has a UCC area
            allowed_for_area = ucc_area_remaining.get(area, 0)#looks up how many classes are still needed for that UCC area
            if used_ucc_area_count[area] >= allowed_for_area: # Checks if you already added enough classes for this UCC area
                continue
            used_ucc_area_count[area] += 1 # This prevents recommending to many UCC classes from the same area

        result.append(item)
        used_codes.add(code)

        if len(result) == 5:
            return result

    for item in majors:#you loop through major classes again just in case you did not find enough UCCs
        code = str(item.get("course_code"))

        if code in used_codes:
            continue

        result.append(item)
        used_codes.add(code)

        if len(result) == 5:
            return result

    return result[:5]


@router.post("/upload")
async def upload_pdf(request: Request):
    state.candidates_store = []#clears old candidates
    candidates = []#Stores possible clases

    modality_preference = request.headers.get("X-Modality-Preference", "").strip()#Reads header from swift

    contents = await request.body()# Reads raw PDF bytes
    extracted_text = extract_pdf_text(contents) # convert PDF bytes to text

    parsed = parse_degreeworks_text(extracted_text)#Takes all degree works text and extract the student's academci data

    all_files = load_json_files(FALL_FILES)# You get all fall files
    crn_rule_lookup = build_crn_rule_lookup(PREREQS)# here its about getting the restriciton for each section
    all_sections = build_section_database(all_files, crn_rule_lookup)# this is to have each class in the right format

    find_ucc_area = make_find_ucc_area(all_sections)# fund_ucc_area is a function that you can use to find a UCC core area

    # This is where you extract student data
    completed_courses = parsed["completed_courses"]
    in_progress_courses = parsed["in_progress_courses"]
    major = parsed["major"]
    major_needed_courses = parsed["major_needed_courses"]
    ucc_requirements = parsed["ucc_requirements"]
    ucc_area_remaining = parsed["ucc_area_remaining"]


    # Build taken courses and this also prevents duplicates
    taken_courses = {
        normalize(c["course_number"])
        for c in completed_courses + in_progress_courses
    }

    needed_major = {# only keep major courses not already taken
        normalize(c) for c in major_needed_courses
        if normalize(c) not in taken_courses
    }

    ucc_needed = set()
    seen_ucc_areas = set()

    for section in all_sections:#loop every possible class
        course_code = normalize(section.get("course_code", ""))
        area_key = find_ucc_area_from_section(section)#finds which cateogry this class belongs to.

        if not area_key:# skip non UCC classes
            continue

        if area_key in seen_ucc_areas:# Only take one class per UCC area
            continue

        if ucc_area_remaining.get(area_key, 0) <= 0:#Skip satisfied UCC area
            continue

        if course_code in taken_courses:#skips if already taken
            continue

        if course_code in needed_major:#Avoid overlap with major
            continue

        ucc_needed.add(course_code)# Adds a ucc option
        seen_ucc_areas.add(area_key)

    allowed_courses = needed_major | ucc_needed

    ucc_section_count = defaultdict(int)# How many classes have been added for each UCC area
    ucc_area_count = defaultdict(int)# How many section have I added for this specific course

    for section in all_sections:
        course_code = normalize(section.get("course_code", ""))
        crn = section["crn"]
        is_ucc_course = course_code not in needed_major and course_code in ucc_needed

        # These are all filters again

        if not modality_matches_preference(section.get("modality"), modality_preference):
            continue# This check whether the clas smatchs the user_modality choice

        if course_code not in allowed_courses:# checks if in allowed course
            continue

        if course_code in taken_courses:#checks to see if youve already taken the coruse then you skip that if you have
            continue

        if not prereqs_satisfied(crn, completed_courses, in_progress_courses, PREREQS):# If student does not satisfy prereqs then skip
            continue

        if not restriction_satisfied(section, completed_courses, major):
            continue

        if is_ucc_course:# this block only runs if the course is a ucc
            area_key = find_ucc_area(course_code)# This finds which UCC area the course belongs to

            if not area_key:# If youcant digure our the course area skip it
                continue
# ucc_area_count[area_key] is how many candidates section you have arleady complted for this area
# ucc_area_remaining.get(area_key, 0) how many the student stilll needs for that area
            if ucc_area_count[area_key] >= ucc_area_remaining.get(area_key, 0):# this prevents your candidate list from being flooded with mutliple UCC from the same area
                continue

            ucc_area_count[area_key] += 1# if the clas passed the limit check add one
            ucc_section_count[course_code] += 1#counts how many section of this specifc UCC you accepted

        candidate_type = candidate_type_for_course(course_code, major, find_ucc_area)#you find out what kinda of course it is it could return major or UCC or SUPPORT

        professor = section.get("professor")# get professor name

        candidates.append({# possible class the student can take
            "course_code": course_code,
            "crn": crn,
            "type": candidate_type,
            "ucc_area": find_ucc_area(course_code),
            "section": section,#here the entire section dicitonary is inserted
            "professor": professor,
        })

    seen_crns = set()
    deduped_candidates = []#Creates an empty lsit of candidate after removing duplicates

    for candidate in candidates:#Loops through ever candidate collected
        if str(candidate["crn"]) not in seen_crns:#checks if this candidate crn has not been sued already
            seen_crns.add(str(candidate["crn"]))
            deduped_candidates.append(candidate)

    candidates = deduped_candidates#replace the old candidate list with the cleaned one with no duplicates

    major_candidates = [c for c in candidates if c.get("type") == "MAJOR"]# gets only majors
    ucc_candidates = [c for c in candidates if c.get("type") == "UCC"]# get only ucc candidates
    support_candidates = [c for c in candidates if c.get("type") == "SUPPORT"]# get only support classes

    ordered_candidates = major_candidates + ucc_candidates + support_candidates
    ordered_candidates = shrink_candidates_for_ai(ordered_candidates, max_per_course=2, max_total=12)

    student_profile_for_ai = {#what you send to ai
        "major": parsed["major"],
        "program": parsed["program"],
        "gpa": parsed["gpa"],
        "credits_remaining": parsed["credits_remaining"],
        "completed_courses": completed_courses,
        "in_progress_courses": in_progress_courses,
        "failed_courses": parsed["failed_courses"],
        "not_started_courses": parsed["not_started_courses"],
        "unmet_requirements": parsed["unmet_requirements"],
        "major_requirements": parsed["major_requirements"],
        "ucc_requirements": ucc_requirements,
        "registration_date": parsed["registration_date"],
        "selection_rules": {
            "max_classes": 5,
            "prefer_major_first": True,
            "use_ucc_only_if_needed": True,
            "only_one_option_per_choose_one_group": True,
            "only_one_science_option_at_a_time": True,
            "no_time_conflicts": True,
            "must_have_prereqs": True,
        },
    }

    try:
        final_schedule = choose_schedule_with_ai(
            student_profile_for_ai,
            ordered_candidates,#send possible classes
            max_classes=5,
        )
    except Exception:
        final_schedule = []

    if not final_schedule:  # no OpenAI key, or AI returned nothing — use local builder
        final_schedule = pick_schedule(ordered_candidates, ucc_area_remaining)
    else:
        final_schedule = fill_remaining_schedule(final_schedule, ordered_candidates, # I NEED THIS LINE
        max_classes=5)  # ai only give me like 3 class i'll fill the rest up this always happens

    clean_final = []#clean schedule list
    seen = set()#traack course codes already added
    seen_ucc_area_count = defaultdict(int)#tracks how many UCC per area hve bene added to final schedule

    for item in final_schedule:#loop through Ai or fallback chosen courses
        sec = item.get("section", item)
        code = normalize(sec.get("course_code", ""))

        if code in taken_courses:#Do not include taken course course
            continue

        if code in seen:#no duplicates allowed
            continue

        if item.get("type") == "UCC":# If this is a UCC class, apply extra UCC area limit
            ucc_area = item.get("ucc_area")

            if ucc_area:
                allowed_for_area = ucc_area_remaining.get(ucc_area, 0)#look up how many are allowed for this UCC area

                if seen_ucc_area_count[ucc_area] >= allowed_for_area:#if you already reached the limit skip
                    continue

                seen_ucc_area_count[ucc_area] += 1#otherwise add 1

        seen.add(code)
        clean_final.append(item)#Adds this item to clean schedule

        if len(clean_final) == 5:
            break

    final_schedule = enforce_priority(clean_final, ucc_area_remaining)# without enforce_prioerty majors will not be priorizted

    final_schedule = attach_reasons(final_schedule) # Here is where you attach reasons to final schedule

    student_profile = {
        "major": parsed["major"],
        "program": parsed["program"],
        "gpa": parsed["gpa"],
        "credits_required": parsed["credits_required"],
        "credits_applied": parsed["credits_applied"],
        "completed_courses": completed_courses,
        "exempt_courses": parsed["exempt_courses"],
        "failed_courses": parsed["failed_courses"],
        "final_schedule": final_schedule,
        "not_started_courses": parsed["not_started_courses"],
        "unmet_requirements": parsed["unmet_requirements"],
        "spring_term": [c for c in in_progress_courses if "Spring" in c["term"]],
        "summer_term": [c for c in in_progress_courses if "Summer" in c["term"]],
        "winter_term": [c for c in in_progress_courses if "Winter" in c["term"]],
        "fall_term": [c for c in in_progress_courses if "Fall" in c["term"]],
        "credits_remaining": parsed["credits_remaining"],
        "ucc_requirements": ucc_requirements,
        "major_requirements": parsed["major_requirements"],
    }

    state.candidates_store = candidates#saves all possible candidates in mememory so swap options can use them alter
    return student_profile
