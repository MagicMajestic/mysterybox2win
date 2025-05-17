import json
import os
import logging

logger = logging.getLogger(__name__)

# Define constants for file paths
DATA_DIR = "data"
IMAGES_DIR = f"{DATA_DIR}/images"
PRIZE_LISTS_DIR = f"{DATA_DIR}/prize_lists"
GIVEAWAYS_FILE = f"{DATA_DIR}/giveaways.json"
PRIZES_FILE = f"{DATA_DIR}/prizes.json"
GIFS_FILE = f"{DATA_DIR}/gifs.json"
PRIZE_LISTS_FILE = f"{DATA_DIR}/prize_lists.json"

def ensure_data_directory():
    """Ensure the data directory exists"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        logger.info(f"Created data directory: {DATA_DIR}")
    
    # Create images directory if it doesn't exist
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
        logger.info(f"Created images directory: {IMAGES_DIR}")
        
    # Create prize lists directory if it doesn't exist
    if not os.path.exists(PRIZE_LISTS_DIR):
        os.makedirs(PRIZE_LISTS_DIR)
        logger.info(f"Created prize lists directory: {PRIZE_LISTS_DIR}")

def load_giveaways():
    """Load giveaways from json file"""
    ensure_data_directory()
    try:
        if os.path.exists(GIVEAWAYS_FILE):
            with open(GIVEAWAYS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {}
    except Exception as e:
        logger.error(f"Error loading giveaways: {e}")
        return {}

def save_giveaways(giveaways):
    """Save giveaways to json file"""
    ensure_data_directory()
    try:
        with open(GIVEAWAYS_FILE, 'w', encoding='utf-8') as f:
            json.dump(giveaways, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving giveaways: {e}")

def load_prizes():
    """Load prizes from json file"""
    ensure_data_directory()
    try:
        if os.path.exists(PRIZES_FILE):
            with open(PRIZES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {}
    except Exception as e:
        logger.error(f"Error loading prizes: {e}")
        return {}

def save_prizes(prizes):
    """Save prizes to json file"""
    ensure_data_directory()
    try:
        with open(PRIZES_FILE, 'w', encoding='utf-8') as f:
            json.dump(prizes, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving prizes: {e}")

def load_gifs():
    """Load celebration GIFs from json file"""
    ensure_data_directory()
    try:
        if os.path.exists(GIFS_FILE):
            with open(GIFS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {}
    except Exception as e:
        logger.error(f"Error loading GIFs: {e}")
        return {}

def save_gifs(gifs):
    """Save celebration GIFs to json file"""
    ensure_data_directory()
    try:
        with open(GIFS_FILE, 'w', encoding='utf-8') as f:
            json.dump(gifs, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving GIFs: {e}")
        
def save_gif_file(gif_id, gif_data):
    """Save GIF binary data to file"""
    ensure_data_directory()
    try:
        gif_path = f"{IMAGES_DIR}/{gif_id}.gif"
        with open(gif_path, 'wb') as f:
            f.write(gif_data)
        return gif_path
    except Exception as e:
        logger.error(f"Error saving GIF file: {e}")
        return None

def get_gif_path(gif_id):
    """Get path to a GIF file by ID"""
    gif_path = f"{IMAGES_DIR}/{gif_id}.gif"
    if os.path.exists(gif_path):
        return gif_path
    return None

def load_prize_lists():
    """Load prize lists metadata from json file"""
    ensure_data_directory()
    try:
        if os.path.exists(PRIZE_LISTS_FILE):
            with open(PRIZE_LISTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            return {}
    except Exception as e:
        logger.error(f"Error loading prize lists: {e}")
        return {}

def save_prize_lists(prize_lists):
    """Save prize lists metadata to json file"""
    ensure_data_directory()
    try:
        with open(PRIZE_LISTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(prize_lists, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving prize lists: {e}")

def save_prize_list_file(list_id, prize_data):
    """Save a prize list to a text file"""
    ensure_data_directory()
    try:
        file_path = f"{PRIZE_LISTS_DIR}/{list_id}.txt"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(prize_data)
        return file_path
    except Exception as e:
        logger.error(f"Error saving prize list file: {e}")
        return None

def load_prize_list_file(list_id):
    """Load a prize list from a text file"""
    try:
        file_path = f"{PRIZE_LISTS_DIR}/{list_id}.txt"
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            logger.error(f"Prize list file not found: {file_path}")
            return None
    except Exception as e:
        logger.error(f"Error loading prize list file: {e}")
        return None

def parse_prize_ids(prize_ids_str, prizes):
    """Parse prize IDs, including ranges like '1-3'"""
    result = {}
    missing = []
    
    # Split by comma
    parts = [part.strip() for part in prize_ids_str.split(',')]
    
    for part in parts:
        # Check if it's a range (e.g., "1-3")
        if '-' in part:
            try:
                start, end = map(str.strip, part.split('-'))
                # Convert to int only for comparison, then back to string
                start_int, end_int = int(start), int(end)
                
                # Process each ID in the range
                for i in range(start_int, end_int + 1):
                    prize_id = str(i)
                    if prize_id in prizes:
                        result[prize_id] = prizes[prize_id]
                    else:
                        missing.append(prize_id)
            except ValueError:
                # If not valid integers, treat as a regular ID
                if part in prizes:
                    result[part] = prizes[part]
                else:
                    missing.append(part)
        else:
            # Regular ID
            if part in prizes:
                result[part] = prizes[part]
            else:
                missing.append(part)
    
    return result, missing
