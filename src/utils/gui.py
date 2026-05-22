"""
GUI automation helpers for QlikView and Power BI Desktop.

Every function in this module drives a desktop application through
pyautogui / pygetwindow / pywinauto so that the migration pipeline can
open files, click menus, export PDFs, etc. without manual intervention.
"""

# Standard library
import json
import os
import re
import shutil
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

# Third-party – GUI automation
import pyautogui
import pygetwindow as gw
from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys

# Third-party – other
import fitz  # PyMuPDF
import psutil
from PIL import Image

# Cross-module helpers (already split into io_helpers)
from src.utils.io_helpers import (
    read_csv_flexible_encoding,
    split_pdf_by_sheets,
    wait_for_pdf_stable_size,
)

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"

UI_TARGETS_DIR = ASSETS_DIR / "gui_targets"


# ====================================================================
# QlikView automation
# ====================================================================

def handle_auth_user_popup():

    # Press First Cancel
    pyautogui.press('esc')
    time.sleep(0.5)

    # Press Enter twice
    pyautogui.press("enter")
    time.sleep(0.5)
    pyautogui.press("enter")
    time.sleep(0.5)

    # Press Second Cancel
    pyautogui.press('esc')


def _find_on_screen(image_name, logger, min_search_time=1.5, confidence=0.8):
    """Locate a UI element on screen by template matching.
    Returns a Point(x, y) at the center of the match, or None if not found.
    Falls back to matching without `confidence` if opencv-python isn't installed.
    """
    image_path = UI_TARGETS_DIR / image_name
    if not image_path.exists():
        logger.warning(f"UI target image not found: {image_path}")
        return None
    try:
        return pyautogui.locateCenterOnScreen(
            str(image_path),
            minSearchTime=min_search_time,
            confidence=confidence,
        )
    except pyautogui.ImageNotFoundException:
        return None
    except TypeError:
        try:
            return pyautogui.locateCenterOnScreen(
                str(image_path), minSearchTime=min_search_time
            )
        except pyautogui.ImageNotFoundException:
            return None


def automate_qlikview(document_analyzer_path, analysis_path, logger, multiplier=1):
    try:
        qlikview_file = document_analyzer_path
        window_title_part = "QlikView x64 Personal Edition"

        current_width, current_height = pyautogui.size()
        logger.info(f"Resolution: {current_width}x{current_height}")

        # Fallback hardcoded coordinates (1920x1080 baseline) — only used
        # when image recognition can't find the UI element.
        path_input_coords = {'x': 162, 'y': 198}
        extract_button_coords = {'x': 122, 'y': 525}
        open_log_button_coords = {'x': 319, 'y': 515}

        # If QlikView is already open, reuse the window — saves the 10s launch
        # wait on every file after the first.
        existing_windows = gw.getWindowsWithTitle(window_title_part)
        if existing_windows:
            logger.info("QlikView already open, reusing existing window")
            qlikview_window = existing_windows[0]
        else:
            logger.info(f"Opening QlikView file: {qlikview_file}")
            if not os.path.exists(qlikview_file):
                raise FileNotFoundError(f"QlikView file not found: {qlikview_file}")
            subprocess.Popen(qlikview_file, shell=True)
            # Poll for the window — allow up to ~30s for QlikView to open
            qlikview_window = None
            for i in range(60):  # 60 × 0.5s = 30s max
                time.sleep(0.5)
                found = gw.getWindowsWithTitle(window_title_part)
                if found:
                    qlikview_window = found[0]
                    print(f"  QlikView window found after ~{(i+1)*0.5:.1f}s")
                    break
                if (i + 1) % 10 == 0:
                    print(f"   Still waiting for QlikView to open... ({(i+1)*0.5:.0f}s)")
            if qlikview_window is None:
                raise Exception(f"Could not find QlikView window after 30s — title containing '{window_title_part}'")
            time.sleep(1.5)  # small buffer for the document UI to render

        qlikview_window.maximize()
        time.sleep(2 * multiplier)
        qlikview_window.moveTo(0, 0)
        qlikview_window.resizeTo(current_width, current_height)
        time.sleep(3 * multiplier)
        qlikview_window.activate()
        time.sleep(3 * multiplier)

        # --- Click the path input field ---
        anchor = _find_on_screen("path_input_anchor.png", logger)
        if anchor is not None:
            input_x, input_y = int(anchor.x), int(anchor.y) + 40
            print("found")
        else:
            input_x, input_y = path_input_coords['x'], path_input_coords['y']
            print("not found")

            logger.warning(f"Falling back to hardcoded path input coords: ({input_x},{input_y})")

        pyautogui.click(input_x, input_y)
        time.sleep(1 * multiplier)
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.5 * multiplier)
        pyautogui.press('delete')
        time.sleep(0.5 * multiplier)
        pyautogui.write(analysis_path, interval=0.02)
        time.sleep(1 * multiplier)
        pyautogui.press('enter')
        logger.info(f"Entered analysis path: {analysis_path}")

        # --- Click the "Extract Metadata" button ---
        extract_loc = _find_on_screen("extract_button.png", logger)
        if extract_loc is not None:
            extract_x, extract_y = int(extract_loc.x), int(extract_loc.y)
        else:
            extract_x, extract_y = extract_button_coords['x'], extract_button_coords['y']
            logger.warning(f"Falling back to hardcoded Extract Metadata coords: ({extract_x},{extract_y})")

        pyautogui.click(extract_x, extract_y)
        logger.info("Clicked Extract Metadata button — waiting for DocumentAnalyzer to process")
        time.sleep(15 * multiplier)

        try:
            auth_user_popup = pyautogui.locateOnScreen(
                str(UI_TARGETS_DIR / "user_id.png"), minSearchTime=2
            )
        except pyautogui.ImageNotFoundException:
            auth_user_popup = None

        if auth_user_popup:
            logger.warning(f"User authentication popup detected for {analysis_path}. Handling...")
            handle_auth_user_popup()
        else:
            pyautogui.press('enter')
            time.sleep(8 * multiplier)

            # Wait for reload/script execution to finish
            time.sleep(5 * multiplier)

            # --- Click the "Open doc log" button ---
            log_loc = _find_on_screen("open_log_button.png", logger)
            if log_loc is not None:
                open_log_x, open_log_y = int(log_loc.x), int(log_loc.y)
            else:
                open_log_x, open_log_y = open_log_button_coords['x'], open_log_button_coords['y']
                logger.warning(f"Falling back to hardcoded Open doc log coords: ({open_log_x},{open_log_y})")

            pyautogui.click(open_log_x, open_log_y)
            time.sleep(3 * multiplier)
            logger.info("Clicked Open doc log button")

    except Exception as e:
        logger.error("Automation failed with an exception:", exc_info=True)
        print("Automation failed.")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {str(e)}")
        raise


def close_qv_window(logger):
    """
    Closes the QlikView window without saving by sending keypresses:
    Right arrow key to select 'No', then Enter.
    """
    try:
        window_title_part = "QlikView x64 Personal Edition"
        windows = gw.getWindowsWithTitle(window_title_part)
        if not windows:
            logger.info("No QlikView window found to close — already closed.")
            return

        qlikview_window = windows[0]
        qlikview_window.activate()
        time.sleep(2)

        qlikview_window.close()
        time.sleep(3)

        pyautogui.press('right')
        time.sleep(1)
        pyautogui.press('enter')
        time.sleep(2)

        # Verify it actually closed
        remaining = gw.getWindowsWithTitle(window_title_part)
        if remaining:
            logger.warning("QlikView window still open after close attempt, force-closing with Alt+F4")
            remaining[0].activate()
            time.sleep(1)
            pyautogui.hotkey('alt', 'F4')
            time.sleep(2)
            pyautogui.press('right')
            time.sleep(1)
            pyautogui.press('enter')
            time.sleep(2)

        logger.info("QlikView window closed successfully")
    except Exception as e:
        logger.error(f"Failed to close QlikView window: {e}", exc_info=True)


def automate_qlikview_report_to_pdf(qvw_path, output_pdf_path, logger, multiplier=1):

    try:
        report_name = os.path.splitext(os.path.basename(qvw_path))[0]
        pdf_dir = os.path.dirname(output_pdf_path)
        os.makedirs(pdf_dir, exist_ok=True)

        print(f"     PDF output dir: {pdf_dir}")
        print(f"     Expected PDF: {output_pdf_path}")

        logger.info(f"Opening QlikView file: {qvw_path}")
        if not os.path.exists(qvw_path):
            raise FileNotFoundError(f"QlikView file not found: {qvw_path}")

        print(f"     Launching QlikView with: {qvw_path}")
        subprocess.Popen(str(qvw_path), shell=True)

        # Poll for the window — allow up to ~30s for QlikView to open
        print(f"     Polling for QlikView window (up to 30s)...")
        qv_windows = []
        for i in range(60):  # 60 × 0.5s = 30s max
            time.sleep(0.5)
            all_windows = gw.getAllWindows()
            qv_windows = [w for w in all_windows
                         if w.title and ('qlikview' in w.title.lower() or
                                       w.title.endswith('.qvw') or
                                       'qv' in w.title.lower())]
            if qv_windows:
                print(f"     QlikView window found after ~{(i+1)*0.5:.1f}s: '{qv_windows[0].title}'")
                break
            if (i + 1) % 10 == 0:
                visible_titles = [w.title for w in all_windows if w.title.strip()][:10]
                print(f"     Still waiting... ({(i+1)*0.5:.0f}s) — visible windows: {visible_titles}")

        if not qv_windows:
            all_titles = [w.title for w in gw.getAllWindows() if w.title.strip()]
            print(f"     No QlikView window found after 30s")
            print(f"     All visible windows: {all_titles}")
            raise Exception(f"No QlikView window found after 30s. Visible windows: {all_titles}")

        # Use the first QlikView window found
        qv_window = qv_windows[0]
        logger.info(f"Found QlikView window: {qv_window.title}")

        # Focus the window
        print(f"     Activating window: '{qv_window.title}'")
        qv_window.activate()
        time.sleep(3)

        # Proceed with automation
        print(f"      Starting menu automation (Alt  File  Print to PDF)...")

        # 1. Alt → File menu
        print(f"      [1/7] Pressing Alt to open menu bar")
        pyautogui.press('alt')
        time.sleep(2)

        # 2. Tab 9 times to select "Object"
        print(f"      [2/7] Tab×9  navigating to File menu")
        pyautogui.press('tab', presses=9, interval=1)
        pyautogui.press('enter')
        time.sleep(2 * multiplier)

        # 3. Tab 6 times to "Print as PDF"
        print(f"      [3/7] Tab×6  navigating to 'Print to PDF'")
        pyautogui.press('tab', presses=6, interval=1)
        pyautogui.press('enter')
        time.sleep(2 * multiplier)

        # 4. Tab 5 times, then Down arrow to "All pages"
        print(f"      [4/7] Tab×5 + Down  selecting 'All pages'")
        pyautogui.press('tab', presses=5, interval=1)
        time.sleep(1 * multiplier)
        pyautogui.press('down')
        time.sleep(1 * multiplier)
        pyautogui.press('enter')
        time.sleep(2 * multiplier)

        # 5. filename input
        print(f"      [5/7] Typing filename: Pages_{report_name}")
        time.sleep(2)
        pyautogui.write(f"Pages_{report_name}")

        # 6. Tab 6 times to folder path input, then Enter
        print(f"      [6/7] Tab×6  navigating to folder path input")
        pyautogui.press('tab', presses=6, interval=1)
        pyautogui.press('enter')
        time.sleep(2)

        # 7. Type folder path and confirm
        print(f"      [7/7] Typing output path: {pdf_dir}")
        pyautogui.write(pdf_dir)
        time.sleep(2)
        pyautogui.press('enter')
        pyautogui.press('tab', presses=8, interval=1)
        pyautogui.press('enter')

        # Wait for PDF to finish saving
        print(f"     Waiting for PDF to finish saving...")
        logger.info("Waiting for PDF to finish saving and become stable...")
        wait_for_pdf_stable_size(output_pdf_path, logger=logger)
        print(f"     PDF saved: {output_pdf_path}")

    except Exception as e:
        logger.error(f"PDF export failed for {qvw_path}", exc_info=True)
        print(f"     PDF export failed: {type(e).__name__}: {e}")
        raise


# ====================================================================
# Power BI automation
# ====================================================================

def ensure_output_directory(output_path: Path):
    """Ensure output directory exists"""
    output_path.mkdir(parents=True, exist_ok=True)


def get_pbi_files(input_path: Path, logger) -> List[Path]:
    """Get all Power BI files from the specified input directory"""
    try:
        pbi_files = []
        if input_path.exists():
            pbi_files.extend(input_path.glob("*.pbix"))
            pbi_files.extend(input_path.glob("*.pbit"))

        logger.info(f"Found {len(pbi_files)} Power BI files in {input_path}")
        return pbi_files
    except Exception as e:
        logger.error(f"Error getting PBI files from {input_path}: {e}")
        return []


def open_powerbi_file(file_path: Path, logger) -> bool:
    """Open a Power BI file"""
    try:
        logger.info(f"Opening Power BI file: {file_path.name}")
        subprocess.Popen([str(file_path)], shell=True)
        time.sleep(15)  # Wait for Power BI to fully load
        return True
    except Exception as e:
        logger.error(f"Error opening Power BI file {file_path}: {e}")
        return False


def get_powerbi_window(logger, timeout=30):
    """Return the main Power BI Desktop window (UIA) or None after timeout."""

    desktop = Desktop(backend="uia")
    title_patterns = (re.compile(r".*Power BI Desktop.*"), re.compile(r".*Microsoft Power BI.*"))
    deadline = time.time() + timeout
    last_err = None

    while time.time() < deadline:
        # Try by window title (fast)
        for pat in title_patterns:
            try:
                w = desktop.window(title_re=pat.pattern, control_type="Window")
                if w.exists(timeout=0.3):
                    try:
                        w.wait("ready", timeout=5)
                    except Exception:
                        continue
                    try:
                        if hasattr(w, "is_minimized") and w.is_minimized():
                            w.restore()
                        w.set_focus()
                    except Exception:
                        pass
                    logger.info(f"Found Power BI window by title: {w.window_text()}")
                    return w
            except Exception as e:
                last_err = e

        # Fallback: connect by PID (robust)
        try:
            pid = next((p.info["pid"] for p in psutil.process_iter(["name", "pid"])
                        if (p.info["name"] or "").lower() in {"pbidesktop.exe", "pbidesktopstore.exe"}), None)
            if pid:
                app = Application(backend="uia").connect(process=pid, timeout=5)
                w = app.top_window()
                if w.exists(timeout=0.3):
                    try:
                        w.wait("ready", timeout=5)
                    except Exception:
                        pass
                    try:
                        if hasattr(w, "is_minimized") and w.is_minimized():
                            w.restore()
                        w.set_focus()
                    except Exception:
                        pass
                    logger.info(f"Found Power BI window by PID {pid}: {w.window_text()}")
                    return w
        except Exception as e:
            last_err = e

        time.sleep(1)

    logger.error(f"Power BI window not found within {timeout}s. Last error: {last_err!r}")
    return None


def get_save_dialog_window(report_name, logger, timeout=10):
    """
    Find the save dialog window that contains part of the report name.
    """
    desktop = Desktop(backend="uia")
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            # Look for windows containing part of the report name
            for window in desktop.windows():
                title = window.window_text()
                if title and report_name[:10] in title:  # First 10 characters of report
                    logger.info(f"Found window")
                    window.set_focus()
                    return window
        except:
            pass
        time.sleep(1)

    logger.error("Save dialog window not found")
    return None


def execute_complete_export_sequence(folder_path: Path, report_name: str, logger) -> bool:
    """Execute the complete export sequence automatically"""
    try:
        logger.info("Starting automated export sequence...")

        # Get Power BI window
        pbi_window = get_powerbi_window(logger)
        if not pbi_window:
            logger.error("Could not find Power BI window")
            return False

        pbi_window.set_focus()
        time.sleep(2)

        # Execute the exact sequence you specified
        logger.info("Executing print sequence...")

        # Step 1: Ctrl+P (open save dialog)
        send_keys("^p")
        time.sleep(3)

        # Step 2.A: Find and focus the save dialog
        save_dialog = get_save_dialog_window(report_name, logger)
        if save_dialog:
            logger.info(f"Found save dialog")
            # Continue with your save sequence here...
        else:
            logger.error("Could not find save dialog window")

        time.sleep(2)

        # Step 2: Ctrl+P again (open save dialog 2 )
        send_keys("^p")
        time.sleep(3)


        # Step 3: Tab 2 times
        send_keys("{TAB 2}")
        time.sleep(2)

        # Step 4: Enter, then up arrow 4 times to select type of PDF generation
        send_keys("{ENTER}")
        time.sleep(2)
        send_keys("{UP 4}")
        time.sleep(2)

        # Step 5: Enter to select PDF type
        send_keys("{ENTER}")
        time.sleep(2)

        # Step 6: Tab 5 times to select Save button
        send_keys("{TAB 5}")
        time.sleep(2)

        # Step 7: Enter to press Save button
        send_keys("{ENTER}")
        time.sleep(2)
        """
        # Step 8: Tab 6 times
        send_keys("{TAB 6}")
        time.sleep(3)

        # Step 9: Enter
        send_keys("{ENTER}")
        time.sleep(3)
        """
        # Step 10: Set the save location
        logger.info(f"Setting save location to: {folder_path}")

        # Focus address bar and set path
        send_keys("^l")  # Ctrl+L to focus address bar
        time.sleep(2)
        send_keys("^a")  # Select all
        time.sleep(2)
        send_keys(str(folder_path), with_spaces=True)
        time.sleep(2)
        send_keys("{ENTER}")
        time.sleep(2)

        # Step 11: Tab 6 times to filename field and set name
        logger.info(f"Setting filename to: {report_name}")

        send_keys("{TAB 7}")
        time.sleep(3)
        """
        send_keys("^+f")  # Ctrl+Shift+F to focus filename
        time.sleep(1)
        """
        #send_keys("^a")  # Select all existing text
        #time.sleep(3)
        send_keys(str(report_name), with_spaces=True)
        time.sleep(3)

        # Step 12: Enter to save
        send_keys("{ENTER}")
        time.sleep(3)

        logger.info("Export sequence completed")
        return True

    except Exception as e:
        logger.error(f"Error in export sequence: {e}")
        return False


def close_powerbi(logger) -> bool:
    """Close Power BI application"""
    try:
        logger.info("Closing Power BI...")

        pbi_window = get_powerbi_window(logger)
        if pbi_window:
            pbi_window.set_focus()
            time.sleep(0.5)

        # Alt+F4 to close
        send_keys("%{F4}")
        time.sleep(2)

        # Handle potential save dialog
        try:
            # Press N for "No" if save dialog appears
            send_keys("n")
            time.sleep(1)
        except:
            pass

        return True
    except Exception as e:
        logger.error(f"Error closing Power BI: {e}")
        return False


def wait_for_powerbi_load(logger, timeout: int = 60) -> bool:
    """Wait for Power BI to fully load"""
    try:
        start_time = time.time()

        while time.time() - start_time < timeout:
            if get_powerbi_window(logger):
                logger.info("Power BI loaded successfully")
                time.sleep(5)  # Additional wait for full initialization
                return True
            time.sleep(10)

        logger.warning("Power BI load timeout")
        return False

    except Exception as e:
        logger.error(f"Error waiting for Power BI: {e}")
        return False


def validate_pdf_created(folder_path: Path, report_name: str, logger) -> bool:
    """Validate that the PDF was created successfully"""
    try:
        pdf_file = folder_path / f"{report_name}.pdf"
        if pdf_file.exists() and pdf_file.stat().st_size > 0:
            logger.info(f"PDF successfully created: {pdf_file}")
            return True
        else:
            logger.warning(f"PDF not found or empty: {pdf_file}")
            return False
    except Exception as e:
        logger.error(f"Error validating PDF: {e}")
        return False


def convert_pdf_to_images(pdf_path: Path, output_folder: Path, logger) -> bool:
    """Convert PDF pages to individual PNG images - simple extraction"""
    try:
        logger.info(f"Converting PDF to images: {pdf_path}")

        if not pdf_path.exists():
            logger.error(f"PDF file not found: {pdf_path}")
            return False

        # Open PDF document
        doc = fitz.open(str(pdf_path))

        # Process each page
        for page_num in range(len(doc)):
            page = doc[page_num]

            # Simple consecutive numbering
            output_png = output_folder / f"page_{page_num + 1:02d}.png"

            try:
                # Render PDF page to PNG at 300 DPI
                pix = page.get_pixmap(dpi=300)
                pix.save(str(output_png))

                logger.info(f"Saved: {output_png}")

            except Exception as e:
                logger.error(f"Failed to process page {page_num + 1}: {e}")
                continue

        #doc.close()
        logger.info(f"Successfully converted {len(doc)} pages to images")
        return True

    except ImportError as e:
        logger.error("PyMuPDF not installed. Please install: pip install PyMuPDF")
        return False
    except Exception as e:
        logger.error(f"Error converting PDF to images: {e}")
        return False


def convert_all_pdfs_to_images(output_path: Path, logger) -> bool:

    """Convert all PDFs in output folder subfolders to images"""

    try:
        logger.info(f"Starting PDF to images conversion in: {output_path}")

        if not output_path.exists():
            logger.error(f"Output path does not exist: {output_path}")
            return False

        # Find all subfolders (each represents a report)
        report_folders = [f for f in output_path.iterdir() if f.is_dir()]

        if not report_folders:
            logger.warning(f"No report folders found in {output_path}")
            return False

        logger.info(f"Found {len(report_folders)} report folders to process")

        successful_conversions = 0

        for folder in report_folders:
            folder_name = folder.name
            expected_pdf = folder / f"{folder_name}.pdf"

            logger.info(f"Processing folder: {folder_name}")

            if expected_pdf.exists():
                success = convert_pdf_to_images(expected_pdf, folder, logger)
                if success:
                    successful_conversions += 1
                    logger.info(f"Successfully converted {folder_name}")
                else:
                    logger.warning(f"Failed to convert {folder_name}")
            else:
                logger.warning(f"PDF not found: {expected_pdf}")

        logger.info(f"Conversion summary: {successful_conversions}/{len(report_folders)} successful")
        return successful_conversions > 0

    except Exception as e:
        logger.error(f"Error in PDF to images conversion: {e}")
        return False


def kill_powerbi_processes(logger) -> bool:
    """Force kill any remaining Power BI processes"""
    try:
        logger.info("Killing Power BI process...")

        killed = False
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'].lower() in ['pbidesktop.exe', 'pbidesktopstore.exe']:
                    proc.kill()
                    logger.info(f"Killed {proc.info['name']} (PID: {proc.info['pid']})")
                    killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if killed:
            time.sleep(2)  # Give it time to close
            logger.info("Power BI process killed successfully")
            return True
        else:
            logger.warning("No Power BI process found to kill")
            return False

    except Exception as e:
        logger.error(f"Error killing Power BI: {e}")


def process_single_report(pbi_file: Path, output_path: Path, logger, overwrite_existing = False) -> Dict[str, Any]:

    """Process a single Power BI report"""

    failed_reports = []
    successful_reports = []

    result = {
        'file_name': pbi_file.name,
        'file_path': str(pbi_file),
        'status': 'pending',
        'error_message': None,
        'processing_time': 0,
        'pdf_created': False,
        'output_folder': None
    }

    process_start_time = time.time()

    try:

        logger.info(f"Processing report: {pbi_file.name}")

        # Step 1: Create output folder
        report_name = pbi_file.stem  # filename without extension
        clean_name = "".join(c for c in report_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        output_folder = output_path / clean_name
        should_process = False

        # Case: Overwrite is enabled
        if overwrite_existing:
            if os.path.exists(output_folder):
                shutil.rmtree(output_folder)
            logger.info(f"[OVERWRITE] Image output missing for {pbi_file}.")
            print(f"[OVERWRITE] Image output missing for {pbi_file}.")
            should_process = True

        # Case: Folder doesn't exist or is empty (first-time run)
        elif not os.path.exists(output_folder) or not os.listdir(output_folder):
            logger.info(f"[NEW] Image output missing for {pbi_file}. Will extract.")
            print(f"[NEW] Extracting Image info for: {pbi_file}")
            should_process = True

        # Case: Folder already exists and is not empty and overwrite is False → skip
        elif os.path.exists(output_folder) and os.listdir(output_folder):
            logger.info(f"[SKIP] Image output already exists for {pbi_file}.")
            print(f"[SKIP] Image output already exists for {pbi_file}")

        if should_process:
            output_folder.mkdir(parents=True, exist_ok=True)

            # Step 2: Open Power BI file
            if not open_powerbi_file(pbi_file,logger):
                raise Exception("Failed to open Power BI file")

            # Step 3: Wait for Power BI to fully load
            logger.info("Waiting for Power BI to load...")
            if not wait_for_powerbi_load(logger,timeout=60):
                logger.warning("Power BI load timeout, proceeding anyway...")

            # Step 4: Execute the complete export sequence
            if not execute_complete_export_sequence(output_folder, report_name, logger):
                raise Exception("Failed to execute export sequence")

            # Step 5: Wait for PDF generation to complete
            logger.info("Waiting for PDF generation...")
            time.sleep(5)

            # Step 6: Validate PDF was created
            pdf_created = validate_pdf_created(output_folder, report_name, logger)
            result['pdf_created'] = pdf_created
            time.sleep(3)

            # Step 7: Close Power BI
            kill_powerbi_processes(logger)
            time.sleep(3)

            result['status'] = 'success' if pdf_created else 'warning'
            result['processing_time'] = time.time() - process_start_time

            if pdf_created:
                successful_reports.append(pbi_file.name)
                logger.info(f"Successfully processed: {pbi_file.name}")
            else:
                failed_reports.append(pbi_file.name)
                logger.warning(f"Processed with warnings: {pbi_file.name}")

    except Exception as e:
        result['status'] = 'failed'
        result['error_message'] = str(e)
        result['processing_time'] = time.time() - process_start_time
        failed_reports.append(pbi_file.name)

        logger.error(f"Failed to process {pbi_file.name}: {e}")

        # Force close Power BI in case of error
        try:
            close_powerbi(logger)
            time.sleep(2)
            kill_powerbi_processes(logger)  # Force kill if needed
        except:
            pass

    return result


def analyze_powerbi_reports(settings, client, logger, overwrite_existing=False):
    """
    Process all Power BI report pages (images) in each report folder and generate structured JSON analysis.
        Args:
            settings: Dictionary containing configuration paths
            client: OpenAI client instance
            logger: Logger instance
            overwrite_existing: Boolean to overwrite existing results
    """
    from src.utils.llm import obtain_prompt_for_image_analysis, process_report_image, save_analysis_result

    instruction = obtain_prompt_for_image_analysis()

    # Get paths from settingsoutput_path
    local_folder_path = Path(settings["local_folder_path"])

    # This should be the parameter path to PBI reports
    # Define output structure: C:\Users\CatherineVaras\Documents\DataMigrationTool\Fabric Migration\output\qlik_pbi_validation\pbi\json_reports_analysis
    output_folder_path = os.path.join(local_folder_path, "output")
    validation_folder_path = os.path.join(output_folder_path, "qlik_pbi_validation")
    pbi_validation_folder_path = os.path.join(validation_folder_path, "pbi")

    # Define output structure: C:\Users\CatherineVaras\Documents\DataMigrationTool\Fabric Migration\output\qlik_pbi_validation\pbi\json_reports_analysis
    source_path = os.path.join(pbi_validation_folder_path, "extracted_reports_images")

    # Define output structure: C:\Users\CatherineVaras\Documents\DataMigrationTool\Fabric Migration\output\qlik_pbi_validation\pbi\json_reports_analysis
    json_reports_analysis_path = os.path.join(pbi_validation_folder_path, "json_reports_analysis")

    model_name = "gpt-4o"

    # Create base directories if they don't exist
    os.makedirs(json_reports_analysis_path, exist_ok=True)

    # Check if source_path exists and contains report folders
    if not os.path.exists(source_path):
        logger.error(f"Source path does not exist: {source_path}")
        print(f"Error: Source path does not exist: {source_path}")
        return

    # Walk through each Power BI report directory
    for report_name in os.listdir(source_path):
        report_path = os.path.join(source_path, report_name)

        # Skip if not a directory
        if not os.path.isdir(report_path):
            continue

        # Create output folder for this report's JSON analysis
        output_report_folder = os.path.join(json_reports_analysis_path, report_name)

        # Check overwrite conditions
        if overwrite_existing:
            if os.path.exists(output_report_folder):
                shutil.rmtree(output_report_folder)
            logger.info(f"[OVERWRITE] Analysis output will be regenerated for {report_name}.")
            print(f"[OVERWRITE] Analysis output will be regenerated for {report_name}.")
        elif not os.path.exists(output_report_folder) or not os.listdir(output_report_folder):
            logger.info(f"[NEW] Analysis output missing for {report_name}. Will analyze.")
            print(f"[NEW] Analyzing Power BI report: {report_name}")
        elif os.path.exists(output_report_folder) and os.listdir(output_report_folder):
            logger.info(f"[SKIP] Analysis output already exists for {report_name}.")
            print(f"[SKIP] Analysis output already exists for {report_name}")
            continue

        print(f"Processing Power BI report: {report_name}")
        os.makedirs(output_report_folder, exist_ok=True)

        # Get all image files in the report folder (skip PDF files)
        image_files = []
        for filename in os.listdir(report_path):
            if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
                image_files.append(filename)

        # Sort image files to ensure consistent page numbering
        image_files.sort()

        # Process each image file
        for page_number, filename in enumerate(image_files, 1):
            image_path = os.path.join(report_path, filename)
            print(f"  Analyzing page {page_number}: {filename}")

            try:
                # Process the image with AI
                result = process_report_image(image_path, instruction, client, model_name)

                # Save the result with proper naming convention
                save_analysis_result(result, image_path, output_report_folder)

            except Exception as e:
                logger.error(f"Error processing {image_path}: {e}")
                print(f"Error processing {image_path}: {e}")

        print(f"Completed analysis for report: {report_name}")

    print("Power BI report analysis completed.")
