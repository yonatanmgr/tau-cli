import math
import pickle
from datetime import datetime, timedelta
from tau_tools.moodle import Moodle, AdditionalAssignmentInfo, RecordingInfo, AssignmentInfo, CourseInfo
from tau_tools.ims import IMS, GradeInfo
from pathlib import Path
import pandas as pd
import questionary
from sys import stdout as terminal
from time import sleep
from itertools import cycle
from threading import Thread
import webbrowser
import re

# Constants
DEFAULT_CACHE_DIR = Path.home() / "tau"
LOGIN_DETAILS = ("", "", "")
CACHE_TTL = timedelta(days=0)
CACHE_FILES = {
    "courses": DEFAULT_CACHE_DIR / "courses_cache.pkl",
    "assignments": DEFAULT_CACHE_DIR / "assignments_cache.pkl",
    "grades": DEFAULT_CACHE_DIR / "grades_cache.pkl",
    "recordings": DEFAULT_CACHE_DIR / "recordings_cache.pkl",
    "login_details": DEFAULT_CACHE_DIR / "login_details.pkl",
}


def reverse_hebrew_substrings(text):
    """
    Extracts Hebrew substrings from the input text, reverses them,
    and returns the modified text with flipped Hebrew substrings.

    Args:
        text (str): The input text containing Hebrew and other characters.

    Returns:
        str: The modified text with reversed Hebrew substrings.
    """
    # Define a regular expression pattern to match Hebrew characters
    hebrew_pattern = r'[\u0590-\u05FF]+'

    # Function to reverse a matched Hebrew substring
    def reverse_match(match):
        return match.group(0)[::-1]

    if not re.search(hebrew_pattern, text):
        return text

    # Use re.sub to replace Hebrew substrings with their reversed versions
    flipped_text = re.sub(hebrew_pattern, reverse_match, text)

    # Reverse the order of words in the text
    flipped_text = " ".join(reversed(flipped_text.split()))

    return flipped_text


def loading_animation(running_text: str = "Running", finished_text: str = "Done!"):
    """Displays a loading animation while a function runs.

    Args:
        running_text (str): Text to display during execution.
        finished_text (str): Text to display after execution completes.

    Returns:
        function: A decorated function with the loading animation.
    """
    diff = len(running_text) - len(finished_text) + 2
    spaces = " " * diff if diff > 0 else ""

    def wrapper(f):
        def wrapped(*args, **kwargs):
            done = False

            def animation():
                for c in cycle(['\u28fe', '\u28f7', '\u28ef', '\u28df', '\u287f', '\u28bf', '\u28db', '\u28ed']):
                    if done:
                        break
                    terminal.write(f'\r{running_text} ' + c)
                    terminal.flush()
                    sleep(0.1)
                terminal.write(f'\r{finished_text}' + spaces + "\n")
                terminal.flush()

            t = Thread(target=animation)
            t.start()

            result = f(*args, **kwargs)
            done = True
            t.join()
            return result

        return wrapped

    return wrapper


def load_cache(cache_file, cache_ttl=CACHE_TTL):
    """Loads cached data from a file if it is valid.

    Args:
        cache_file (Path): Path to the cache file.
        cache_ttl (timedelta): Time-to-live for the cache.

    Returns:
        any: Cached data if valid, otherwise None.
    """
    if cache_file.exists():
        with open(cache_file, "rb") as f:
            try:
                cache = pickle.load(f)
                if datetime.now() - cache["last_updated"] < cache_ttl:
                    return cache["data"]
            except (pickle.UnpicklingError, EOFError):
                print(f"Cache file {cache_file} is corrupted. Reinitializing.")
    return None


def save_cache(data, cache_file):
    """Saves data to a cache file.

    Args:
        data (any): Data to be cached.
        cache_file (Path): Path to the cache file.
    """
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "wb") as f:
        pickle.dump({"data": data, "last_updated": datetime.now()}, f)


def get_login_details():
    """Retrieves login details from the cache or prompts the user for them.

    Returns:
        tuple: A tuple containing username, user ID, and password.
    """
    login_details = load_cache(CACHE_FILES["login_details"], timedelta(days=365))
    if not login_details:
        print("Login details not found. Please provide them.")
        username = questionary.text("Username:").ask()
        user_id = questionary.text("ID:").ask()
        password = questionary.password("Password:").ask()
        login_details = (username, user_id, password)
        save_cache(login_details, CACHE_FILES["login_details"])
    return login_details


def clear_console():
    """Clears the terminal console."""
    terminal.flush()
    terminal.write("\033c")
    terminal.flush()


def get_filtered_assignments(assignments):
    """Filters assignments based on due date.

    Args:
        assignments (DataFrame): List of assignments.

    Returns:
        DataFrame: Filtered assignments as a DataFrame.
    """
    return assignments[assignments["due_date"] > pd.Timestamp.now()]


@loading_animation(running_text="Loading assignments", finished_text="Assignments loaded!")
def load_assignments(moodle) -> list[AssignmentInfo]:
    """Loads assignments from Moodle.

    Args:
        moodle (Moodle): Moodle API instance.

    Returns:
        list: List of assignments.
    """
    return moodle.get_assignments()


@loading_animation(running_text="Loading courses", finished_text="Courses loaded!")
def load_courses(moodle) -> list[CourseInfo]:
    """Loads courses from Moodle.

    Args:
        moodle (Moodle): Moodle API instance.

    Returns:
        list: List of courses.
    """
    return moodle.get_courses()


@loading_animation(running_text="Loading recordings", finished_text="Recordings loaded!")
def load_recordings(moodle, course_id) -> list[RecordingInfo]:
    """Loads recordings for a specific course from Moodle.

    Args:
        moodle (Moodle): Moodle API instance.
        course_id (int): Course ID.

    Returns:
        list: List of recordings.
    """
    return moodle.get_recordings(course_id=course_id)


@loading_animation(running_text="Loading grades", finished_text="Grades loaded!")
def load_grades(ims) -> list[GradeInfo]:
    """Loads grades from IMS.

    Args:
        ims (IMS): IMS API instance.

    Returns:
        list: List of grades.
    """
    current_year = datetime.now().year
    return ims.get_all_grades(list(range(current_year - 3, current_year + 4)))


@loading_animation(running_text="Connecting to IMS", finished_text="Connected!")
def connect_to_ims() -> IMS:
    """Connects to IMS API.

    Returns:
        IMS: IMS API instance.
    """
    ims = IMS(*LOGIN_DETAILS)
    return ims


@loading_animation(running_text="Loading additional information", finished_text="Loaded!")
def load_additional_info(moodle, assignment_id) -> AdditionalAssignmentInfo:
    """Loads additional information for an assignment from Moodle.

    Args:
        moodle (Moodle): Moodle API instance.
        assignment_id (int): Assignment ID.

    Returns:
        dict: Additional assignment information.
    """
    return moodle.get_additional_info(assignment_id)


def interactive_mode(moodle):
    """Starts the interactive mode for user interaction.

    Args:
        moodle (Moodle): Moodle API instance.
    """
    while True:
        print("")
        clear_console()
        main_choice = questionary.select(
            "What would you like to do?",
            choices=[
                {"name": "🏫 View Courses (Moodle)", "value": "View Courses"},
                {"name": "📝 View Grades (IMS)", "value": "View Grades"},
                {"name": "🚪 Exit", "value": "Exit"},
            ]
        ).ask()

        if not main_choice:
            break

        if main_choice == "View Grades":
            grades = load_cache(CACHE_FILES["grades"])
            if not grades:
                ims = connect_to_ims()
                grades = load_grades(ims)
                save_cache(grades, CACHE_FILES["grades"])

            if len(grades) == 0:
                print("No grades found.")
                continue

            grades_df = pd.DataFrame(grades).sort_values(by=["semester", "course_id", "grade"])
            for _, row in grades_df.iterrows():
                if math.isnan(float(row["grade"])):
                    continue
                print(f"- {row['semester']} - {row['course_id']} - {int(row['grade'])}")

            print("")
            questionary.press_any_key_to_continue().ask()

        elif main_choice == "View Courses":
            courses = load_cache(CACHE_FILES["courses"]) or load_courses(moodle)
            save_cache(courses, CACHE_FILES["courses"])

            clear_console()

            course_choice = questionary.select(
                "Select a course:",
                choices=[
                    {"name": reverse_hebrew_substrings(course.name), "value": course.id}
                    for course in courses
                ]
            ).ask()

            if not course_choice:
                continue
            clear_console()

            course_action = questionary.select(
                f"What do you want to view for course {course_choice}?",
                choices=[
                    {"name": "✏️ Assignments", "value": "View Assignments"},
                    {"name": "🎥 Recordings", "value": "View Recordings"},
                    {"name": "🚪 Back", "value": "Back"},
                ]
            ).ask()

            if not course_action or course_action == "Back":
                continue

            if course_action == "View Assignments":
                assignments = load_cache(CACHE_FILES["assignments"]) or load_assignments(moodle)
                save_cache(assignments, CACHE_FILES["assignments"])

                if len([assignment for assignment in assignments if assignment.course_id == course_choice]) == 0:
                    print("No assignments found.")
                    continue

                assignments_df = pd.DataFrame(
                    [a for a in assignments if a.course_id == course_choice]).drop_duplicates()

                filtered_assignments = get_filtered_assignments(assignments_df)
                print(f"You have {len(filtered_assignments)} assignments for course {str(course_choice)}:")
                modified_assignments = []
                for _, row in filtered_assignments.iterrows():
                    days_left = (row["due_date"] - pd.Timestamp.now()).days
                    modified_assignments.append(
                        {
                            "id": row["id"],
                            "title": f"{reverse_hebrew_substrings(row['name'])} - {row['due_date']}, {days_left} days left"
                        }
                    )
                clear_console()

                assignment_choice = questionary.select(
                    "Select an assignment:",
                    choices=[{"name": reverse_hebrew_substrings(assignment["title"]), "value": assignment["id"]}
                             for assignment in modified_assignments
                             ]
                ).ask()

                if not assignment_choice:
                    continue

                additional_info = load_additional_info(moodle, assignment_choice)
                clear_console()

                attachment_choice = questionary.select(
                    "Select an attachment:",
                    choices=[{"name": reverse_hebrew_substrings(attachment.filename), "value": attachment.url}
                             for attachment in additional_info.attachments
                             ]
                ).ask()

                if not attachment_choice:
                    continue

                print(f"\nOpening file...")
                webbrowser.open(attachment_choice.replace("?forcedownload=1", ""))

            elif course_action == "View Recordings":
                recordings = load_cache(CACHE_FILES["recordings"]) or load_recordings(moodle, course_choice)
                save_cache(recordings, CACHE_FILES["recordings"])

                if len(recordings) == 0:
                    print("No recordings found.")
                    continue

                print(f"Found {len(recordings)} recordings for course {course_choice}:")
                clear_console()

                recording_choice = questionary.select(
                    "Select a recording:",
                    choices=[
                        {"name": reverse_hebrew_substrings(recording.name), "value": recording.url}
                        for recording in recordings
                    ], pointer="▶️"
                ).ask()

                if not recording_choice:
                    continue

                print(f"\nPlaying recording...")
                webbrowser.open(recording_choice)

        elif main_choice == "Exit":
            print("Exiting...")
            break


def main():
    """Main entry point for the application."""
    global LOGIN_DETAILS
    LOGIN_DETAILS = get_login_details()

    moodle = Moodle(
        username=LOGIN_DETAILS[0],
        id=LOGIN_DETAILS[1],
        password=LOGIN_DETAILS[2],
        session_file=f"{Path.home()}/tau/session.json",
    )

    print("TAU-CLI")
    interactive_mode(moodle)


if __name__ == '__main__':
    main()
